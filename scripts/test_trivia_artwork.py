import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("trivia_artwork.py")
SPEC = importlib.util.spec_from_file_location("trivia_artwork", MODULE_PATH)
artwork = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(artwork)

ROOT = MODULE_PATH.parent.parent
ASSETS = ROOT / "content" / "static" / "trivia" / "assets"
GENERATED = ROOT / "content" / "static" / "trivia" / "artwork.css"

try:
    import PIL  # noqa: F401
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


class ZoomTests(unittest.TestCase):
    '''The background-position that crops an image to its content box.'''

    def test_centred_content_stays_centred(self):
        # Equal margins on both sides have nothing to slide against.
        self.assertAlmostEqual(artwork._zoom(0.10, 0.80), 50.0)

    def test_flush_content_needs_no_offset(self):
        self.assertAlmostEqual(artwork._zoom(0.0, 0.5), 0.0)

    def test_content_against_the_far_edge(self):
        self.assertAlmostEqual(artwork._zoom(0.5, 0.5), 100.0)

    def test_untrimmed_axis_does_not_divide_by_zero(self):
        self.assertAlmostEqual(artwork._zoom(0.0, 1.0), 50.0)


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class GeneratedStylesheetTests(unittest.TestCase):
    '''artwork.css is committed, so it can fall behind the art it describes.'''

    def test_committed_css_matches_the_artwork(self):
        expected = artwork.generate(str(ASSETS))
        actual = GENERATED.read_text()
        self.assertEqual(
            expected, actual,
            "artwork.css is stale; regenerate with "
            "`python3 scripts/trivia_artwork.py`")

    def test_every_frame_declares_a_usable_interior(self):
        for name, selector, trim in artwork.FRAMES:
            with self.subTest(asset=name):
                area = artwork.safe_area(str(ASSETS / name), trim)
                width = 100 - area["left"] - area["right"]
                height = 100 - area["top"] - area["bottom"]
                self.assertGreater(width, 25, "interior too narrow for text")
                self.assertGreater(height, 15, "interior too short for text")

    def test_every_asset_shares_the_page_colour(self):
        # The page is painted --page so the category tiles meet edge to
        # edge as one field; any asset drawn on a different cream shows a
        # rectangle around itself.  scripts/trivia_normalize_art.py fixes
        # a mismatch here.
        target = artwork.page_color(str(ASSETS / artwork.PAGE_SOURCE))
        for name, _, _ in artwork.FRAMES + artwork.ICONS:
            with self.subTest(asset=name):
                found = artwork.page_color(str(ASSETS / name))
                drift = max(abs(found[i] - target[i]) for i in range(3))
                self.assertLessEqual(
                    drift, 1,
                    "{} is drawn on rgb{}, not rgb{}".format(
                        name, found, target))

    def test_categories_are_square_so_they_tile(self):
        # Untrimmed squares are what let the grid close up without ragged
        # rows; trimming them would give each a different aspect ratio.
        for name, selector, trim in artwork.FRAMES:
            if not selector.startswith(".category-label"):
                continue
            with self.subTest(asset=name):
                self.assertFalse(trim, "category tiles must not be trimmed")
                area = artwork.safe_area(str(ASSETS / name), trim)
                self.assertAlmostEqual(area["ratio"], 1.0, places=2)

    def test_referenced_assets_exist(self):
        # Overlays included: they are transparent line art, so they carry
        # no page colour and are excluded from that check, but a missing
        # file would still break the screen that uses them.
        for name, _, _ in artwork.FRAMES + artwork.ICONS + artwork.OVERLAYS:
            with self.subTest(asset=name):
                self.assertTrue((ASSETS / name).is_file())

    def test_overlays_are_transparent(self):
        from PIL import Image
        for name, _, _ in artwork.OVERLAYS:
            with self.subTest(asset=name):
                with Image.open(str(ASSETS / name)) as opened:
                    image = opened.convert("RGBA")
                    width, height = image.size
                    # A wedge midpoint must let the gradient through.
                    self.assertEqual(image.getpixel(
                        (int(width * 0.66), int(height * 0.28)))[3], 0)


if __name__ == "__main__":
    unittest.main()
