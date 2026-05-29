import tempfile
import unittest
from pathlib import Path

from uplaysync.downloader import DirectYtdlpDownloader


class ExistingPathYoutubeDL:
    last_path = None

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def extract_info(self, url, download=True):
        return {'requested_downloads': [{'filepath': str(self.last_path)}]}


class DownloaderCollisionTests(unittest.TestCase):
    def test_preexisting_reported_path_is_marked_as_preexisting_success(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            existing = folder / 'Same Title.m4a'
            existing.write_text('old audio', encoding='utf-8')
            ExistingPathYoutubeDL.last_path = existing
            result = DirectYtdlpDownloader(youtubedl_cls=ExistingPathYoutubeDL).download(
                url='https://youtu.be/new1',
                video_id='new1',
                title='Same Title',
                folder=folder,
            )
            self.assertTrue(result.ok)
            self.assertTrue(result.preexisting)
            self.assertEqual(result.filename, 'Same Title.m4a')
