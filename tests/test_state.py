import errno
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from uplaysync import state


class StateMigrationTests(unittest.TestCase):
    def test_migrates_legacy_files_and_creates_backups(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            id_map = root / 'id_map.json'
            history = root / 'download_history.json'
            sync_state = root / 'sync_state.json'
            id_map.write_text(json.dumps({'abc123': 'Song A.m4a', 'def456': 'ERROR: private video'}, ensure_ascii=False), encoding='utf-8')
            history.write_text(json.dumps(['abc123', 'def456']), encoding='utf-8')

            migrated = state.load_or_migrate_state(sync_state, id_map, history, create_backups=True, mirror_legacy=False)

            self.assertEqual(migrated['schema_version'], 1)
            self.assertEqual(migrated['items']['abc123']['status'], 'downloaded')
            self.assertEqual(migrated['items']['abc123']['filename'], 'Song A.m4a')
            self.assertEqual(migrated['items']['def456']['status'], 'failed')
            self.assertEqual(migrated['items']['def456']['failure_reason'], 'private video')
            self.assertTrue(sync_state.exists())
            self.assertTrue(list(root.glob('id_map.json.bak-sync-state-migration-*')))
            self.assertTrue(list(root.glob('download_history.json.bak-sync-state-migration-*')))

    def test_file_exists_for_entry_uses_fallback_folder(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            (folder / 'Song A.m4a').write_text('audio', encoding='utf-8')
            self.assertTrue(state.file_exists_for_entry({'filename': 'Song A.m4a'}, folder))
            self.assertFalse(state.file_exists_for_entry({'filename': 'Missing.m4a'}, folder))


    def test_load_state_file_normalizes_invalid_shape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sync_state = root / 'sync_state.json'
            sync_state.write_text(json.dumps({'schema_version': 1, 'items': [], 'history': 'bad'}), encoding='utf-8')
            loaded = state.load_state_file(sync_state)
            self.assertEqual(loaded['items'], {})
            self.assertEqual(loaded['history'], [])

    def test_record_failure_mirrors_legacy_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sync_state = state.empty_state()
            state.record_failure(
                sync_state,
                video_id='bad1',
                title='Bad',
                url='https://youtu.be/bad1',
                playlist_name='PL',
                folder=str(root),
                reason='private video',
            )
            state.save_state(sync_state, root / 'sync_state.json', root / 'id_map.json', root / 'download_history.json')
            legacy = json.loads((root / 'id_map.json').read_text(encoding='utf-8'))
            self.assertEqual(legacy['bad1'], 'ERROR: private video')

    def test_atomic_write_falls_back_for_bind_mounted_file_busy(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'id_map.json'
            path.write_text('{}', encoding='utf-8')

            with mock.patch('uplaysync.state.os.replace', side_effect=OSError(errno.EBUSY, 'busy')):
                state._atomic_write_json(path, {'abc': 'Song.m4a'})

            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'abc': 'Song.m4a'})
            self.assertFalse((Path(td) / '.id_map.json.tmp').exists())
