import json
import tempfile
import unittest
from pathlib import Path

from uplaysync import management, state


class ManagementStateTests(unittest.TestCase):
    def test_snapshot_view_reports_download_statuses_and_queue(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            st = state.empty_state()
            management.record_playlist_snapshot(
                st,
                {'name': 'P', 'url': 'playlist-url', 'folder': str(root)},
                [
                    {'id': 'ok1', 'title': 'OK Song', 'url': 'ok1'},
                    {'id': 'new1', 'title': 'New Song', 'url': 'new1'},
                ],
                index=0,
            )
            (root / 'OK Song.m4a').write_text('audio', encoding='utf-8')
            state.record_downloaded(
                st,
                video_id='ok1',
                title='OK Song',
                url='https://youtu.be/ok1',
                playlist_name='P',
                folder=str(root),
                filename='OK Song.m4a',
            )
            job, created = management.enqueue_item(st, 'new1')

            view = management.build_management_view({'playlists': [{'name': 'P', 'url': 'playlist-url', 'folder': str(root)}]}, st)

            self.assertTrue(created)
            self.assertEqual(view['playlists'][0]['items'][0]['status'], 'downloaded')
            self.assertEqual(view['playlists'][0]['items'][1]['status'], 'queued')
            self.assertEqual(view['summary']['queue_active'], 1)
            self.assertEqual(job['video_id'], 'new1')

    def test_trash_and_restore_moves_file_without_hard_delete(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            media = root / 'Song.m4a'
            media.write_text('audio', encoding='utf-8')
            st = state.empty_state()
            state.record_downloaded(
                st,
                video_id='song1',
                title='Song',
                url='https://youtu.be/song1',
                playlist_name='P',
                folder=str(root),
                filename='Song.m4a',
            )

            trashed = management.move_entry_to_trash(st, 'song1')

            self.assertEqual(trashed['status'], 'trashed')
            self.assertFalse(media.exists())
            trash_path = Path(trashed['trash_path'])
            self.assertTrue(trash_path.exists())
            restored = management.restore_trashed_entry(st, 'song1')
            self.assertEqual(restored['status'], 'downloaded')
            self.assertTrue(media.exists())
            self.assertFalse(trash_path.exists())

    def test_queue_duplicate_and_interrupted_reset(self):
        st = state.empty_state()
        management.record_playlist_snapshot(
            st,
            {'name': 'P', 'url': 'playlist-url', 'folder': '/tmp'},
            [{'id': 'x1', 'title': 'X', 'url': 'x1'}],
            index=0,
        )
        first, created_first = management.enqueue_item(st, 'x1')
        second, created_second = management.enqueue_item(st, 'x1')
        first['status'] = 'running'

        reset = management.reset_interrupted_jobs(st)

        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(reset, 1)
        self.assertEqual(first['status'], 'queued')

    def test_legacy_mirror_excludes_trashed_entries(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            media = root / 'Song.m4a'
            media.write_text('audio', encoding='utf-8')
            st = state.empty_state()
            state.record_downloaded(
                st,
                video_id='song1',
                title='Song',
                url='https://youtu.be/song1',
                playlist_name='P',
                folder=str(root),
                filename='Song.m4a',
            )
            management.move_entry_to_trash(st, 'song1')
            state.save_state(st, root / 'sync_state.json', root / 'id_map.json', root / 'download_history.json')

            id_map = json.loads((root / 'id_map.json').read_text(encoding='utf-8'))
            self.assertEqual(id_map, {})


if __name__ == '__main__':
    unittest.main()

class ManagementViewFilteringTests(unittest.TestCase):
    def test_items_outside_playlist_snapshots_are_hidden_from_management_view(self):
        st = state.empty_state()
        st['items']['metube1'] = {
            'video_id': 'metube1',
            'title': 'Manual MeTube Download',
            'url': 'https://www.youtube.com/watch?v=metube1',
            'playlist_names': [],
            'folder': '/youtube',
            'filename': 'Manual MeTube Download.m4a',
            'status': 'downloaded',
        }

        view = management.build_management_view({'playlists': []}, st)

        self.assertNotIn('orphan_items', view)
        self.assertNotIn('orphan_items', view['summary'])
        self.assertEqual(view['summary']['items'], 0)
