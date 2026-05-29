import tempfile
import unittest
from pathlib import Path

from uplaysync import engine, state
from uplaysync.downloader import DownloadResult


class FakeDownloader:
    def __init__(self, fail=False, preexisting=False):
        self.calls = []
        self.fail = fail
        self.preexisting = preexisting

    def download(self, *, url, video_id, title, folder):
        self.calls.append((url, video_id, title, folder))
        if self.fail:
            return DownloadResult(False, video_id, title, url, error='blocked')
        path = Path(folder) / f'{title}.m4a'
        path.write_text('audio', encoding='utf-8')
        return DownloadResult(True, video_id, title, url, filename=path.name, path=str(path), preexisting=self.preexisting)


class EngineDecisionTests(unittest.TestCase):
    def test_existing_title_file_records_state_and_skips(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            (folder / 'Hot!.m4a').write_text('audio', encoding='utf-8')
            config = {'playlists': [{'name': 'P', 'url': 'playlist', 'folder': str(folder)}]}
            fake = FakeDownloader()
            result = engine.sync_playlists(
                config,
                state_path=folder / 'sync_state.json',
                id_map_path=folder / 'id_map.json',
                history_path=folder / 'download_history.json',
                playlist_provider=lambda _: [{'id': 'hot1', 'title': 'Hot!', 'url': 'hot1'}],
                downloader=fake,
            )
            self.assertEqual(fake.calls, [])
            self.assertEqual(result['state']['items']['hot1']['filename'], 'Hot!.m4a')
            self.assertEqual(result['summary']['downloaded'], 0)


    def test_non_audio_title_match_does_not_skip_download(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            (folder / 'Cover Song.jpg').write_text('image', encoding='utf-8')
            fake = FakeDownloader()
            result = engine.sync_playlists(
                {'playlists': [{'name': 'P', 'url': 'playlist', 'folder': str(folder)}]},
                state_path=folder / 'sync_state.json',
                id_map_path=folder / 'id_map.json',
                history_path=folder / 'download_history.json',
                playlist_provider=lambda _: [{'id': 'cover1', 'title': 'Cover Song', 'url': 'cover1'}],
                downloader=fake,
            )
            self.assertEqual(len(fake.calls), 1)
            self.assertEqual(result['state']['items']['cover1']['filename'], 'Cover Song.m4a')

    def test_state_downloaded_missing_file_queues_redownload(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            st = state.empty_state()
            state.record_downloaded(
                st,
                video_id='x1',
                title='Song X',
                url='https://youtu.be/x1',
                playlist_name='P',
                folder=str(folder),
                filename='Song X.m4a',
            )
            state.save_state(st, folder / 'sync_state.json', folder / 'id_map.json', folder / 'download_history.json')
            fake = FakeDownloader()
            result = engine.sync_playlists(
                {'playlists': [{'name': 'P', 'url': 'playlist', 'folder': str(folder)}]},
                state_path=folder / 'sync_state.json',
                id_map_path=folder / 'id_map.json',
                history_path=folder / 'download_history.json',
                playlist_provider=lambda _: [{'id': 'x1', 'title': 'Song X', 'url': 'x1'}],
                downloader=fake,
            )
            self.assertEqual(len(fake.calls), 1)
            self.assertEqual(result['summary']['downloaded'], 1)

    def test_failure_is_recorded_and_not_retried_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            cfg = {'playlists': [{'name': 'P', 'url': 'playlist', 'folder': str(folder)}]}
            provider = lambda _: [{'id': 'bad1', 'title': 'Bad Song', 'url': 'bad1'}]
            first = engine.sync_playlists(
                cfg,
                state_path=folder / 'sync_state.json',
                id_map_path=folder / 'id_map.json',
                history_path=folder / 'download_history.json',
                playlist_provider=provider,
                downloader=FakeDownloader(fail=True),
            )
            self.assertEqual(first['state']['items']['bad1']['status'], 'failed')
            second_downloader = FakeDownloader()
            second = engine.sync_playlists(
                cfg,
                state_path=folder / 'sync_state.json',
                id_map_path=folder / 'id_map.json',
                history_path=folder / 'download_history.json',
                playlist_provider=provider,
                downloader=second_downloader,
            )
            self.assertEqual(second_downloader.calls, [])
            self.assertEqual(second['summary']['skipped'], 1)

    def test_new_item_downloads_directly_without_metube(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            fake = FakeDownloader()
            result = engine.sync_playlists(
                {'metube_url': 'http://unavailable.invalid', 'playlists': [{'name': 'P', 'url': 'playlist', 'folder': str(folder)}]},
                state_path=folder / 'sync_state.json',
                id_map_path=folder / 'id_map.json',
                history_path=folder / 'download_history.json',
                playlist_provider=lambda _: [{'id': 'new1', 'title': 'New Song', 'url': 'new1'}],
                downloader=fake,
            )
            self.assertEqual(len(fake.calls), 1)
            self.assertTrue((folder / 'New Song.m4a').exists())
            self.assertEqual(result['state']['items']['new1']['filename'], 'New Song.m4a')

    def test_preexisting_ytdlp_output_records_state_without_failure(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            fake = FakeDownloader(preexisting=True)
            result = engine.sync_playlists(
                {'playlists': [{'name': 'P', 'url': 'playlist', 'folder': str(folder)}]},
                state_path=folder / 'sync_state.json',
                id_map_path=folder / 'id_map.json',
                history_path=folder / 'download_history.json',
                playlist_provider=lambda _: [{'id': 'same1', 'title': 'Same Song', 'url': 'same1'}],
                downloader=fake,
            )

            self.assertEqual(result['state']['items']['same1']['status'], 'downloaded')
            self.assertEqual(result['summary']['failed'], 0)
            self.assertEqual(result['summary']['downloaded'], 0)
            self.assertEqual(result['summary']['skipped'], 1)
