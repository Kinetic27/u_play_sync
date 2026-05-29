import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

from uplaysync import state


def install_fake_flask():
    fake = types.ModuleType('flask')

    class FakeFlask:
        def __init__(self, name):
            self.name = name
        def route(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator
        def run(self, *args, **kwargs):
            return None

    fake.Flask = FakeFlask
    fake.Response = lambda *args, **kwargs: ('response', args, kwargs)
    fake.jsonify = lambda value=None, *args, **kwargs: value if value is not None else kwargs
    fake.request = types.SimpleNamespace(json=None)
    fake.render_template = lambda name: name
    sys.modules.setdefault('flask', fake)


def install_fake_apscheduler():
    apscheduler = types.ModuleType('apscheduler')
    schedulers = types.ModuleType('apscheduler.schedulers')
    background = types.ModuleType('apscheduler.schedulers.background')

    class FakeJob:
        next_run_time = None
        def remove(self):
            return None

    class FakeScheduler:
        def start(self):
            return None
        def shutdown(self):
            return None
        def get_job(self, job_id):
            return None
        def add_job(self, *args, **kwargs):
            return FakeJob()

    background.BackgroundScheduler = FakeScheduler
    sys.modules.setdefault('apscheduler', apscheduler)
    sys.modules.setdefault('apscheduler.schedulers', schedulers)
    sys.modules.setdefault('apscheduler.schedulers.background', background)


def import_web_app_with_fake_flask():
    install_fake_flask()
    install_fake_apscheduler()
    sys.modules.pop('web.app', None)
    return importlib.import_module('web.app')


class WebHistoryApiTests(unittest.TestCase):
    def test_get_history_reads_canonical_state_route_function(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            app_mod = import_web_app_with_fake_flask()
            app_mod.STATE_FILE_PATH = str(root / 'sync_state.json')
            app_mod.ID_MAP_PATH = str(root / 'id_map.json')
            app_mod.HISTORY_PATH = str(root / 'download_history.json')
            st = state.empty_state()
            state.record_downloaded(
                st,
                video_id='ok1',
                title='OK Song',
                url='https://youtu.be/ok1',
                playlist_name='P',
                folder=str(root),
                filename='OK Song.m4a',
            )
            state.record_failure(
                st,
                video_id='bad1',
                title='Bad Song',
                url='https://youtu.be/bad1',
                playlist_name='P',
                folder=str(root),
                reason='private video',
            )
            state.save_state(st, root / 'sync_state.json', root / 'id_map.json', root / 'download_history.json')

            result = app_mod.get_history()

            self.assertEqual(result[0]['id'], 'bad1')
            self.assertEqual(result[0]['status'], 'failed')
            self.assertEqual(result[0]['failure_reason'], 'private video')
            self.assertEqual(result[1]['filename'], 'OK Song.m4a')


    def test_get_history_falls_back_to_legacy_when_canonical_empty(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            app_mod = import_web_app_with_fake_flask()
            app_mod.STATE_FILE_PATH = str(root / 'sync_state.json')
            app_mod.ID_MAP_PATH = str(root / 'id_map.json')
            app_mod.HISTORY_PATH = str(root / 'download_history.json')
            (root / 'sync_state.json').write_text(json.dumps({'schema_version': 1, 'items': {}, 'history': []}), encoding='utf-8')
            (root / 'id_map.json').write_text(json.dumps({'ok1': 'OK Song.m4a'}), encoding='utf-8')
            (root / 'download_history.json').write_text(json.dumps(['ok1']), encoding='utf-8')

            result = app_mod.get_history()

            self.assertEqual(result[0]['id'], 'ok1')
            self.assertEqual(result[0]['filename'], 'OK Song.m4a')

    def test_get_history_falls_back_to_legacy_route_function(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            app_mod = import_web_app_with_fake_flask()
            app_mod.STATE_FILE_PATH = str(root / 'missing-sync-state.json')
            app_mod.ID_MAP_PATH = str(root / 'id_map.json')
            app_mod.HISTORY_PATH = str(root / 'download_history.json')
            (root / 'id_map.json').write_text(json.dumps({'bad1': 'ERROR: blocked', 'ok1': 'OK Song.m4a'}), encoding='utf-8')
            (root / 'download_history.json').write_text(json.dumps(['ok1', 'bad1']), encoding='utf-8')

            result = app_mod.get_history()

            self.assertEqual(result[0]['id'], 'bad1')
            self.assertEqual(result[0]['status'], 'failed')
            self.assertEqual(result[0]['failure_reason'], 'blocked')
            self.assertEqual(result[1]['filename'], 'OK Song.m4a')
