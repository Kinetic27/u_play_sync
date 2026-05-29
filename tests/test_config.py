import unittest

from uplaysync.config import merge_config_preserving_unknown, strip_legacy_metube_fields


class ConfigTests(unittest.TestCase):
    def test_strip_legacy_metube_fields_removes_top_level_and_playlist_keys(self):
        cleaned = strip_legacy_metube_fields({
            'metube_url': 'http://old',
            'schedule_interval': 2,
            'playlists': [
                {'name': 'A', 'url': 'u', 'folder': 'f', 'metube_folder': 'old/path', 'keep': 'yes'},
            ],
        })

        self.assertNotIn('metube_url', cleaned)
        self.assertNotIn('metube_folder', cleaned['playlists'][0])
        self.assertEqual(cleaned['playlists'][0]['keep'], 'yes')

    def test_merge_config_preserves_unknown_but_drops_legacy_metube_fields(self):
        merged = merge_config_preserving_unknown(
            {
                'metube_url': 'http://old',
                'unknown': True,
                'playlists': [{'name': 'Old', 'metube_folder': 'old'}],
            },
            {
                'schedule_interval': 3,
                'playlists': [{'name': 'New', 'url': 'u', 'folder': 'f'}],
            },
        )

        self.assertTrue(merged['unknown'])
        self.assertEqual(merged['schedule_interval'], 3)
        self.assertNotIn('metube_url', merged)
        self.assertNotIn('metube_folder', merged['playlists'][0])

