import tempfile
import unittest
from pathlib import Path

from uplaysync.downloader import DirectYtdlpDownloader


class FakeYoutubeDL:
    last_opts = None

    def __init__(self, opts):
        FakeYoutubeDL.last_opts = opts
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def extract_info(self, url, download=True):
        outtmpl = self.opts['outtmpl']
        folder = Path(outtmpl).parent
        path = folder / 'Fake Title.m4a'
        path.write_text('audio', encoding='utf-8')
        return {'requested_downloads': [{'filepath': str(path)}]}


class DownloaderTests(unittest.TestCase):
    def test_build_options_are_title_compatible_m4a(self):
        with tempfile.TemporaryDirectory() as td:
            downloader = DirectYtdlpDownloader(youtubedl_cls=FakeYoutubeDL)
            result = downloader.download(url='https://youtu.be/abc', video_id='abc', title='Fake Title', folder=td)
            self.assertTrue(result.ok)
            self.assertEqual(result.filename, 'Fake Title.m4a')
            opts = FakeYoutubeDL.last_opts
            self.assertTrue(opts['outtmpl'].endswith('%(title)s.%(ext)s'))
            self.assertTrue(opts['noplaylist'])
            self.assertIn('m4a', opts['format'])
            self.assertEqual(opts['postprocessors'][0]['preferredcodec'], 'm4a')
