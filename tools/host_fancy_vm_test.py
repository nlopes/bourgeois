"""Keep sky animations separate from the VM's standing-pose comparisons."""
import unittest

from PIL import Image

from host_fancy_vm import stable_pixels


class StablePoseTests(unittest.TestCase):
    def test_comet_changes_do_not_count_as_traveler_movement(self):
        original = Image.new('RGB', (1672, 941))
        comet = original.copy()
        comet.putpixel((800, 170), (255, 249, 225))
        self.assertEqual(stable_pixels(original), stable_pixels(comet))

    def test_title_changes_are_not_hidden_by_the_comet_mask(self):
        original = Image.new('RGB', (1672, 941))
        changed = original.copy()
        changed.putpixel((835, 60), (255, 255, 255))
        self.assertNotEqual(stable_pixels(original), stable_pixels(changed))

    def test_twinkle_changes_do_not_count_as_traveler_movement(self):
        original = Image.new('RGB', (1672, 941))
        twinkling = original.copy()
        twinkling.putpixel((265, 45), (200, 200, 200))
        self.assertEqual(stable_pixels(original), stable_pixels(twinkling))
        self.assertEqual(twinkling.getpixel((265, 45)), (200, 200, 200))

    def test_changes_at_the_traveler_are_still_detected(self):
        original = Image.new('RGB', (1672, 941))
        moved = original.copy()
        moved.putpixel((326, 650), (200, 150, 100))
        self.assertNotEqual(stable_pixels(original), stable_pixels(moved))


if __name__ == '__main__':
    unittest.main()
