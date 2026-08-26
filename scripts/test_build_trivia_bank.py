import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_trivia_bank.py")
SPEC = importlib.util.spec_from_file_location("build_trivia_bank", MODULE_PATH)
bank = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bank)


def question(qid, category, difficulty="easy", text=None, answer="right"):
    return {
        "id": qid,
        "category": category,
        "difficulty": difficulty,
        "question": {"text": text or "prompt for {}".format(qid)},
        "correctAnswer": answer,
        "incorrectAnswers": ["a", "b", "c"],
        # Fields the game never reads; they must not reach the browser.
        "tags": ["ignored"],
        "regions": [],
        "isNiche": False,
        "type": "text_choice",
    }


class BuildTests(unittest.TestCase):
    def test_fields_are_renamed_to_what_the_game_reads(self):
        built, _ = bank.build([question("1", "geography")])
        self.assertEqual(built, [{
            "id": "1",
            "prompt": "prompt for 1",
            "answer": "right",
            "incorrectAnswers": ["a", "b", "c"],
            "sourceCategory": "geography",
            "sourceDifficulty": "easy",
        }])

    def test_unused_fields_are_dropped(self):
        built, _ = bank.build([question("1", "science")])
        for gone in ("tags", "regions", "isNiche", "type",
                     "category", "difficulty", "correctAnswer"):
            self.assertNotIn(gone, built[0])

    def test_music_and_film_merge_into_entertainment(self):
        built, _ = bank.build([question("1", "music"),
                               question("2", "film_and_tv")])
        self.assertEqual({q["sourceCategory"] for q in built},
                         {"entertainment"})

    def test_society_and_culture_merges_into_history(self):
        built, _ = bank.build([question("1", "society_and_culture")])
        self.assertEqual(built[0]["sourceCategory"], "history")

    def test_food_and_drink_merges_into_sport_and_leisure(self):
        built, _ = bank.build([question("1", "food_and_drink")])
        self.assertEqual(built[0]["sourceCategory"], "sport_and_leisure")

    def test_general_knowledge_is_not_served(self):
        built, _ = bank.build([question("1", "general_knowledge"),
                               question("2", "geography")])
        self.assertEqual([q["id"] for q in built], ["2"])

    def test_an_undecided_category_is_an_error_not_a_silent_drop(self):
        with self.assertRaises(ValueError) as caught:
            bank.build([question("1", "underwater_basket_weaving")])
        self.assertIn("underwater_basket_weaving", str(caught.exception))

    def test_duplicate_ids_are_collapsed(self):
        built, _ = bank.build([question("1", "geography"),
                               question("1", "geography")])
        self.assertEqual(len(built), 1)

    def test_unknown_difficulty_is_an_error(self):
        with self.assertRaises(ValueError):
            bank.build([question("1", "geography", difficulty="fiendish")])

    def test_categories_are_the_six_the_game_plays(self):
        _, categories = bank.build([])
        self.assertEqual([label for _, label in categories], [
            "Geography", "Entertainment", "History",
            "Arts and Literature", "Science", "Sports and Leisure"])

    def test_no_api_category_feeds_two_game_categories(self):
        seen = set()
        for _, _, sources in bank.CATEGORIES:
            for source in sources:
                self.assertNotIn(source, seen)
                seen.add(source)

    def test_rendered_bank_declares_both_globals(self):
        built, categories = bank.build([question("1", "geography")])
        text = bank.render(built, categories)
        self.assertIn("window.TRIVIA_CATEGORIES =", text)
        self.assertIn("window.TRIVIA_QUESTIONS =", text)


if __name__ == "__main__":
    unittest.main()
