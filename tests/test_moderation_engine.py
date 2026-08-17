import unittest

from ai.moderation import moderation_engine


class ModerationDetectorTests(unittest.TestCase):
    def test_link_detector(self):
        self.assertTrue(moderation_engine.contains_link("visit https://example.com"))
        self.assertTrue(moderation_engine.contains_link("t.me/example"))

    def test_username_detector(self):
        self.assertTrue(moderation_engine.contains_mention("contact @example_user"))
        self.assertFalse(moderation_engine.contains_mention("email@example.com"))

    def test_hashtag_detector(self):
        self.assertTrue(moderation_engine.contains_hashtag("#crypto"))
        self.assertTrue(moderation_engine.contains_hashtag("#تبلیغ"))

    def test_phone_detector(self):
        self.assertTrue(moderation_engine.contains_phone("+989121234567"))

    def test_spaced_terms_are_normalized(self):
        self.assertTrue(moderation_engine.contains_profanity("ک س ک ش"))


if __name__ == "__main__":
    unittest.main()
