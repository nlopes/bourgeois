import struct
import unittest
import zlib

from boot_test import screen_has_content


def screenshot(color, pixels):
    header = struct.pack('>IIBBBBB', 2, 1, 8, color, 0, 0, 0)
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(b'\0' + pixels)) + chunk(b'IEND', b'')


class ScreenshotTests(unittest.TestCase):
    def test_black_rgb_display_is_rejected(self):
        self.assertFalse(screen_has_content(screenshot(2, bytes(6))))

    def test_alpha_does_not_make_a_black_display_count_as_visible(self):
        self.assertFalse(screen_has_content(screenshot(6, bytes([0, 0, 0, 255]) * 2)))

    def test_visible_pixel_is_detected(self):
        self.assertTrue(screen_has_content(screenshot(2, bytes([255, 255, 255, 0, 0, 0]))))
