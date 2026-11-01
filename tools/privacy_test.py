"""Keep local host details and personal image metadata out of public evidence."""
import json
from pathlib import Path
import re
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


class PublicEvidenceTests(unittest.TestCase):
    def test_published_metrics_omit_private_manifest_fields(self):
        forbidden = {'authenticode_sha256', 'efi_sha256', 'installed_sha256',
                     'root_uuid', 'boot_current', 'boot_order', 'default_boot_order',
                     'current_boot_current', 'native_sources'}
        def inspect(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden.intersection(value))
                for item in value.values():
                    inspect(item)
            elif isinstance(value, list):
                for item in value:
                    inspect(item)
        for file in (ROOT / 'docs/research').glob('*.json'):
            with self.subTest(file=file.name):
                inspect(json.loads(file.read_text()))

    def test_host_guides_omit_local_hashes_and_home_paths(self):
        for name in ('host-fancy.adoc', 'fancy-performance.adoc'):
            text = (ROOT / 'docs/research' / name).read_text()
            with self.subTest(file=name):
                self.assertIsNone(re.search(r'\b[0-9a-f]{64}\b', text))
                self.assertIsNone(re.search(r'/home/(?!bourgeois\b)[\w.-]+', text))
                self.assertIsNone(re.search(r'Boot(?:Current|Order|Next):\s*[0-9A-Fa-f]{4}', text))

    def test_public_images_have_no_exif_or_xmp(self):
        for folder in ('assets', 'docs/research/mockups'):
            for file in (ROOT / folder).iterdir():
                if file.suffix.lower() not in {'.png', '.gif'}:
                    continue
                with self.subTest(file=file.name), Image.open(file) as image:
                    self.assertFalse({'exif', 'xmp', 'XML:com.adobe.xmp'}.intersection(image.info))


if __name__ == '__main__':
    unittest.main()
