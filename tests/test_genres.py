import unittest

from ymd.genres import GENRE_NAMES, genre_title


class GenreTests(unittest.TestCase):
    def test_russian_rap(self):
        self.assertEqual(genre_title("rusrap"), "Русский рэп")

    def test_catalog_and_unknown_names(self):
        self.assertGreater(len(GENRE_NAMES), 150)
        self.assertEqual(genre_title("ROCK"), GENRE_NAMES["rock"])
        self.assertEqual(genre_title("Мой жанр"), "Мой жанр")
        self.assertEqual(genre_title("future-new-genre"), "future-new-genre")
