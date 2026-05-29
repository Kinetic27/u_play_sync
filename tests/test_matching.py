import unittest
from pathlib import Path

from uplaysync import matching


class ExistingFileMatchingTests(unittest.TestCase):
    def norm(self, title):
        return matching.normalize_title(title)

    def assert_matches(self, title, filename):
        self.assertTrue(
            matching.is_existing_file_match(title, self.norm(Path(filename).stem)),
            msg=f"expected {title!r} to match {filename!r}",
        )

    def assert_not_matches(self, title, filename):
        self.assertFalse(
            matching.is_existing_file_match(title, self.norm(Path(filename).stem)),
            msg=f"expected {title!r} not to match {filename!r}",
        )

    def test_hot_does_not_match_unrelated_not_hot_title(self):
        self.assert_not_matches('Hot!', 'BIG SHAQ - MANS NOT HOT (Sad Meal Dubstep Remix).m4a')

    def test_hot_does_not_match_unrelated_drop_it_like_its_hot_title(self):
        self.assert_not_matches('Hot!', "DROP IT LIKE IT'S HOT! (Prod. Luga).m4a")

    def test_decorated_hot_does_not_match_unrelated_not_hot_title(self):
        self.assert_not_matches(
            'Hot! [Official Audio]',
            'BIG SHAQ - MANS NOT HOT [Official Audio].m4a',
        )

    def test_decorated_hot_does_not_match_unrelated_drop_it_like_its_hot_title(self):
        self.assert_not_matches(
            'Hot! (Official Video)',
            "DROP IT LIKE IT'S HOT! (Official Video).m4a",
        )

    def test_hot_matches_exact_normalized_file_name(self):
        self.assert_matches('Hot!', 'Hot!.m4a')

    def test_short_single_token_def_requires_exact_match(self):
        self.assert_matches('Def.', 'Def..m4a')
        self.assert_not_matches('Def.', 'Artist - Def. Remix.m4a')

    def test_distinctive_single_token_still_matches_artist_prefixed_file(self):
        self.assert_matches('Dopamine', 'WING - Dopamine (SO-SO Remix) [Official Audio].m4a')

    def test_decorated_distinctive_single_token_still_matches_artist_prefixed_file(self):
        self.assert_matches('Dopamine (SO-SO Remix)', 'WING - Dopamine [Official Audio].m4a')

    def test_multi_token_title_still_matches_artist_prefixed_file(self):
        self.assert_matches('Digital Swamp', 'WING - Digital Swamp [Official Audio].m4a')

    def test_find_existing_file_match_returns_none_for_hot_collision(self):
        existing = {
            self.norm("BIG SHAQ - MANS NOT HOT (Sad Meal Dubstep Remix)"): 'BIG SHAQ - MANS NOT HOT (Sad Meal Dubstep Remix).m4a',
            self.norm("DROP IT LIKE IT'S HOT! (Prod. Luga)"): "DROP IT LIKE IT'S HOT! (Prod. Luga).m4a",
        }
        self.assertIsNone(matching.find_existing_file_match('Hot!', existing))

    def test_unicode_variant_title_compatible_match(self):
        self.assert_matches('Artemas - BRAINS | Animated Video', 'Artemas - BRAINS ｜ Animated Video.m4a')
