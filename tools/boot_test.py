"""QMP boot regression checks against the configured lab edition."""
import argparse
import fcntl
import json
from pathlib import Path
import time
import struct
import zlib

import lab


def read(path):
    return path.read_text(errors='replace') if path.exists() else ''


def wait_for(path, marker, offset=0, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker in read(path)[offset:]:
            return time.monotonic()
        time.sleep(0.1)
    raise TimeoutError(f'Missing {marker} in {path}')


def reboot_scene(edition):
    log = lab.VM / ('debug.log' if edition == 'fancy' else 'serial.log')
    offset = 0
    lab.reset()
    ready = wait_for(log, f'BOURGEOIS_{"SCENE" if edition == "fancy" else "SLIM"}_READY', offset)
    return log, offset, ready


def screen_has_content(data):
    width, height, depth, color = struct.unpack('>IIBB', data[16:26])
    if depth != 8 or color not in (2, 6):
        raise ValueError('Expected a truecolor QEMU screenshot')
    compressed = bytearray()
    position = 8
    while position < len(data):
        length = struct.unpack('>I', data[position:position + 4])[0]
        if data[position + 4:position + 8] == b'IDAT':
            compressed.extend(data[position + 8:position + 8 + length])
        position += length + 12
    raw = zlib.decompress(compressed)
    channels = 3 if color == 2 else 4
    stride = width * channels + 1
    for row in range(height):
        values = raw[row * stride + 1:(row + 1) * stride]
        if channels == 3 and any(values):
            return True
        if channels == 4 and any(value for index, value in enumerate(values) if index % 4 != 3):
            return True
    return False


def capture(name):
    target = lab.BUILD / 'evidence' / f'{name}.png'
    # Software emulation can leave a blank frame while gfxterm changes modes.
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        lab.screenshot(target)
        data = target.read_bytes()
        width, height = struct.unpack('>II', data[16:24])
        if width >= 800 and height >= 600 and screen_has_content(data):
            return
        time.sleep(0.3)
    raise AssertionError(f'{name}: display is blank or too small ({width}x{height})')


def run(edition, case):
    target = lab.BUILD / 'evidence' / f'{edition}-{case}.json'
    target.unlink(missing_ok=True)
    log, offset, ready = reboot_scene(edition)
    serial = lab.VM / 'serial.log'
    serial_offset = len(read(serial))
    if case == 'timeout':
        capture(f'{edition}-countdown')
        time.sleep(15)
        capture(f'{edition}-midcountdown')
        if edition == 'fancy':
            selected = wait_for(log, 'BOURGEOIS_SELECT_LINUX', offset, 45)
            assert 29 <= selected - ready <= 36, selected - ready
            (lab.BUILD / 'evidence' / 'fancy-timeout-render.txt').write_text(read(log)[offset:])
        boot_started = wait_for(serial, 'Linux version', serial_offset, 90)
        assert boot_started - ready >= 29, boot_started - ready
        wait_for(serial, 'BOURGEOIS_LINUX_OK', serial_offset, 180)
        lab.wait_ssh()
        lab.ssh('sudo systemctl start grub-common.service && sync')
        print(f'PASS {edition}: untouched timer booted Linux')
    elif case == 'cancel':
        lab.send_key('spc' if edition == 'fancy' else 'x')
        time.sleep(32)
        assert 'BOURGEOIS_LINUX_OK' not in read(serial)[serial_offset:]
        assert read(log)[offset:].count(f'BOURGEOIS_{"SCENE" if edition == "fancy" else "SLIM"}_READY') == 1
        if edition == 'fancy':
            assert 'BOURGEOIS_SELECT_' not in read(log)[offset:]
            assert 'BOURGEOIS_TIMER_CANCELLED' in read(log)[offset:]
        capture(f'{edition}-cancelled')
        print(f'PASS {edition}: input cancelled timer without booting')
    elif case == 'selection':
        assert edition == 'slim'
        lab.send_key('w')
        time.sleep(32)
        assert 'Linux version' not in read(serial)[serial_offset:]
        assert 'BOURGEOIS_WINDOWS_FIXTURE' not in read(serial)[serial_offset:]
        capture('slim-windows-selected')
        for key in ('l', 'w', 'l', 'l'):
            lab.send_key(key)
            time.sleep(5)
        capture('slim-linux-selected')
        assert 'Linux version' not in read(serial)[serial_offset:]
        assert 'BOURGEOIS_WINDOWS_FIXTURE' not in read(serial)[serial_offset:]
        lab.send_key('esc')
        time.sleep(1)
        capture('slim-selection-technical')
        print('CAPTURED slim: repeated door switching, cancelled timer, and single-Esc recovery (inspect images)')
    elif case == 'windows':
        lab.send_key('w')
        if edition == 'slim':
            time.sleep(5)
            assert 'BOURGEOIS_WINDOWS_FIXTURE' not in read(serial)[serial_offset:]
            assert 'Linux version' not in read(serial)[serial_offset:]
            lab.send_key('spc')
        wait_for(serial, 'BOURGEOIS_WINDOWS_FIXTURE', serial_offset)
        time.sleep(5)
        assert 'BOURGEOIS_LINUX_OK' not in read(serial)[serial_offset:]
        if edition == 'fancy':
            assert read(log)[offset:].count('BOURGEOIS_SCENE_READY') == 1
        # GRUB reports a returned entry as a boot failure. Dismiss its message.
        lab.send_key('spc')
        time.sleep(1)
        assert read(serial)[serial_offset:].count('BOURGEOIS_WINDOWS_FIXTURE') == 1
        expected_ready = f'BOURGEOIS_{"SCENE" if edition == "fancy" else "SLIM"}_READY'
        assert read(log)[offset:].count(expected_ready) == 1
        capture(f'{edition}-returned-entry')
        print(f'PASS {edition}: Windows activation routed fixture and did not restart scene')
    elif case == 'linux':
        lab.send_key('l')
        if edition == 'slim':
            time.sleep(5)
            assert 'Linux version' not in read(serial)[serial_offset:]
            lab.send_key('spc')
        wait_for(serial, 'BOURGEOIS_LINUX_OK', serial_offset, 180)
        lab.wait_ssh()
        lab.ssh('sudo systemctl start grub-common.service && sync')
        print(f'PASS {edition}: Linux activation booted Linux')
    elif case == 'technical':
        lab.send_key('esc')
        time.sleep(1)
        capture(f'{edition}-technical')
        lab.send_key('e')
        time.sleep(1)
        capture(f'{edition}-editor')
        lab.send_key('esc')
        lab.send_key('c')
        time.sleep(1)
        capture(f'{edition}-command-line')
        print(f'CAPTURED {edition}: technical menu, editor, command line (inspect images)')
    elif case == 'fallbacks':
        for name in ('missing-asset', 'missing-module', 'missing-id', 'unsupported-mode', 'recordfail', 'one-shot', '1024x768', '800x600'):
            log, offset, ready = reboot_scene(edition)
            lab.send_key('esc')
            time.sleep(1)
            lab.send_key('c')
            time.sleep(1)
            log_offset = len(read(log))
            fixture_offset = len(read(serial))
            lab.type_text(f'configfile $prefix/bourgeois/test-{name}.cfg\n')
            if name in ('1024x768', '800x600'):
                wait_for(log, 'BOURGEOIS_SCENE_READY', log_offset)
                lab.send_key('spc')
                time.sleep(1)
                capture(f'fancy-{name}')
                lab.send_key('esc')
                time.sleep(1)
                stats = read(log)[log_offset:]
                (lab.BUILD / 'evidence' / f'fancy-{name}.txt').write_text(stats)
            else:
                if name == 'one-shot':
                    wait_for(serial, 'BOURGEOIS_WINDOWS_FIXTURE', fixture_offset)
                time.sleep(3)
                lab.send_key('spc')  # Dismiss GRUB's error delay without selecting an entry.
                time.sleep(2)
                assert 'BOURGEOIS_SCENE_READY' not in read(log)[log_offset:]
                capture(f'fancy-{name}')
        print('CAPTURED fancy: asset/module/ID/mode fallbacks and two display modes (inspect images)')
    elif case == 'walking':
        assert edition == 'fancy'
        lab.send_key('spc')
        lab.send_key('right')
        time.sleep(0.5)
        lab.send_key('left')
        time.sleep(2)
        assert 'BOURGEOIS_SELECT_' not in read(log)[offset:]
        capture('fancy-linux-gate')
        lab.send_key('right')
        time.sleep(2.6)
        capture('fancy-windows-gate')
        assert 'BOURGEOIS_SELECT_' not in read(log)[offset:]
        lab.send_key('spc')
        wait_for(serial, 'BOURGEOIS_WINDOWS_FIXTURE', serial_offset)
        print('PASS fancy: walking and reversal did not boot; Space at Windows routed fixture')
    else:
        raise ValueError(case)
    result = dict(edition=edition, case=case, elapsed_seconds=round(time.monotonic() - ready, 2))
    target = lab.BUILD / 'evidence' / f'{edition}-{case}.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', choices=['all', 'timeout', 'cancel', 'selection', 'windows', 'linux', 'technical', 'walking', 'fallbacks'])
    args = parser.parse_args()
    lock = (lab.VM / 'boot-test.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.error('Another boot test is using this VM')
    edition = json.loads((lab.BUILD / 'preview.json').read_text())['edition']
    cases = (['cancel', 'walking', 'technical', 'windows', 'linux', 'timeout'] if edition == 'fancy'
             else ['cancel', 'selection', 'technical', 'windows', 'linux', 'timeout']) if args.case == 'all' else [args.case]
    for case in cases:
        run(edition, case)
