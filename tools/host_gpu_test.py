import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import host_gpu
from host_checks import HostSetupError


class HostGPUTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.sysfs = Path(self.directory.name)
        (self.sysfs / 'bus/pci/devices').mkdir(parents=True)

    def device(self, pci, vendor, identifier, device_class='0x030000', boot=None, driver=None):
        device = self.sysfs / 'bus/pci/devices' / pci
        device.mkdir()
        for name, value in (('vendor', vendor), ('device', identifier), ('class', device_class)):
            (device / name).write_text(value)
        if boot is not None:
            (device / 'boot_vga').write_text(str(int(boot)))
        if driver:
            target = self.sysfs / 'bus/pci/drivers' / driver
            target.mkdir(parents=True, exist_ok=True)
            (device / 'driver').symlink_to(target)
        return device

    def connector(self, device, card, name, status, modes=''):
        drm = self.sysfs / 'class/drm'
        (drm / card).mkdir(parents=True, exist_ok=True)
        if not (drm / card / 'device').exists():
            (drm / card / 'device').symlink_to(device)
        connector = drm / f'{card}-{name}'
        connector.mkdir()
        (connector / 'status').write_text(status)
        (connector / 'modes').write_text(modes)

    def inventory(self):
        intel = self.device('0001:00:02.0', '0x8086', '0x1111', '0x038000', driver='i915')
        nvidia = self.device('0001:03:00.0', '0x10de', '0x2222', boot=True, driver='nvidia')
        self.connector(intel, 'card1', 'HDMI-A-1', 'disconnected')
        self.connector(nvidia, 'card2', 'DP-1', 'connected', '1920x1080\n2560x1440\n2560x1440\nbad\n')
        return host_gpu.discover(self.sysfs, names={intel.name: 'Intel UHD Graphics (fixture)',
                                                   nvidia.name: 'NVIDIA GeForce RTX (fixture)'})

    def test_both_controllers_and_monitor_routing_are_detected(self):
        gpus, notes = self.inventory()
        self.assertEqual([gpu['kind'] for gpu in gpus], ['integrated', 'discrete'])
        self.assertEqual([gpu['driver'] for gpu in gpus], ['i915', 'nvidia'])
        self.assertIsNone(gpus[0]['boot_vga'])
        self.assertTrue(gpus[1]['boot_vga'])
        self.assertEqual(gpus[1]['connectors'], [{'name': 'DP-1', 'status': 'connected',
                                                'linux_modes': ['1920x1080', '2560x1440']}])
        self.assertEqual(notes, [])

    def test_recommendation_uses_boot_and_connected_output_evidence(self):
        gpus, _ = self.inventory()
        selected, reason = host_gpu.recommend(gpus)
        self.assertEqual(selected['pci'], '0001:03:00.0')
        self.assertIn('firmware boot VGA', reason)
        self.assertIn('DP-1', reason)
        self.assertIn('current UEFI', host_gpu.guidance(selected))

    def test_select_integrated_gives_firmware_guidance_without_writes(self):
        gpus, _ = self.inventory()
        selected = host_gpu.select(gpus, 'integrated')
        text = host_gpu.guidance(selected)
        self.assertIn('motherboard display output', text)
        self.assertIn('Integrated/IGD', text)
        self.assertIn('guidance only', text)
        self.assertIn('do not establish', text)
        for value in ('1', selected['pci']):
            self.assertEqual(host_gpu.select(gpus, value), selected)

    def test_ambiguous_evidence_does_not_guess_a_gpu(self):
        gpus, _ = self.inventory()
        for gpu in gpus:
            gpu['boot_vga'], gpu['connectors'] = None, []
        self.assertIsNone(host_gpu.recommend(gpus)[0])
        with self.assertRaisesRegex(HostSetupError, 'does not identify'):
            host_gpu.select(gpus, 'auto')

    def test_duplicate_gpu_types_require_an_explicit_pci_choice(self):
        gpus, _ = self.inventory()
        gpus[0]['kind'] = 'discrete'
        with self.assertRaisesRegex(HostSetupError, 'ambiguous'):
            host_gpu.select(gpus, 'discrete')
        with self.assertRaisesRegex(HostSetupError, 'missing'):
            host_gpu.select(gpus, '9')

    def test_vendor_alone_does_not_classify_integrated_or_discrete(self):
        for vendor in ('1002', '10de', '8086'):
            self.assertIn('unknown', host_gpu.kind('0000:05:00.0', vendor, 'unknown GPU'))
        self.assertIn('likely integrated', host_gpu.kind('0001:00:02.0', '8086', 'Intel [8086:4680]'))
        self.assertIn('unknown', host_gpu.kind('0000:05:00.0', '8086', 'Intel Iris Xe MAX'))

    def test_missing_drm_and_driver_are_reported_without_hiding_gpu(self):
        self.device('0001:03:00.0', '0x1002', '0x1234')
        gpus, notes = host_gpu.discover(self.sysfs)
        self.assertEqual(len(gpus), 1)
        self.assertIs(host_gpu.recommend(gpus)[0], gpus[0])
        self.assertIn('DRM connector information is unavailable', '\n'.join(notes))
        self.assertIn('no bound Linux driver', '\n'.join(notes))

    def test_missing_sysfs_or_graphics_has_an_actionable_error(self):
        with self.assertRaisesRegex(HostSetupError, '/sys mounted'):
            host_gpu.discover(self.sysfs / 'missing')
        self.device('0000:00:01.0', '0x8086', '0x1234', '0x020000')
        with self.assertRaisesRegex(HostSetupError, 'No readable PCI graphics'):
            host_gpu.discover(self.sysfs)

    def test_missing_lspci_is_optional_with_a_package_hint(self):
        names, notes = host_gpu.model_names(which=lambda name: None)
        self.assertEqual(names, {})
        self.assertIn('sudo apt install pciutils', notes[0])
        self.device('0001:03:00.0', '0x10de', '0x2222')
        self.assertIn('10de:2222', host_gpu.discover(self.sysfs, names=names)[0][0]['name'])

    def test_lspci_machine_readable_names_and_failures(self):
        result = SimpleNamespace(returncode=0, stdout='0001:03:00.0 "VGA controller" "NVIDIA Corporation" "GeForce RTX (fixture)" -ra1\n')
        names, notes = host_gpu.model_names(which=lambda name: '/bin/lspci', run=lambda *a, **kw: result)
        self.assertEqual(names, {'0001:03:00.0': 'NVIDIA Corporation GeForce RTX (fixture)'})
        self.assertEqual(notes, [])
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired('lspci', 5)
        names, notes = host_gpu.model_names(which=lambda name: '/bin/lspci', run=timeout)
        self.assertEqual(names, {})
        self.assertIn('could not read', notes[0])

    def test_json_can_report_ambiguous_inventory(self):
        gpus, _ = self.inventory()
        for gpu in gpus:
            gpu['boot_vga'], gpu['connectors'] = None, []
        output = io.StringIO()
        with patch('sys.argv', ['host_gpu.py', '--json']), patch.object(host_gpu, 'model_names', return_value=({}, [])), \
                patch.object(host_gpu, 'discover', return_value=(gpus, [])), contextlib.redirect_stdout(output):
            self.assertEqual(host_gpu.main(), 0)
        self.assertIsNone(json.loads(output.getvalue())['recommended_pci'])

    def test_noninteractive_selection_explains_the_explicit_option(self):
        gpus, _ = self.inventory()
        error = io.StringIO()
        with patch('sys.argv', ['host_gpu.py', '--select']), patch.object(host_gpu, 'model_names', return_value=({}, [])), \
                patch.object(host_gpu, 'discover', return_value=(gpus, [])), patch('sys.stdin.isatty', return_value=False), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(error):
            self.assertEqual(host_gpu.main(), 1)
        self.assertIn('Use --gpu', error.getvalue())


if __name__ == '__main__':
    unittest.main()
