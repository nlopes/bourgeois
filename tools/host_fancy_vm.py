"""Check the exact host EFI image in disposable Secure Boot firmware.

Only files are attached as virtual disks. No physical disks or host EFI variables
are exposed. This checks rendering, Esc, and image trust, not native OS booting.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from PIL import Image

import lab
from host_fancy_trial import verify_files
from grub_config import blocks, entry_id

CODE = Path('/usr/share/OVMF/OVMF_CODE_4M.secboot.fd')
VARS = Path('/usr/share/OVMF/OVMF_VARS_4M.ms.fd')
OWNER = '605dab50-e046-4300-abb6-3dd810dd8b23'


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def disk_file(file, size):
    with file.open('wb') as stream:
        stream.truncate(size)


def prepare_root(base, manifest):
    fake = base / 'root/boot/grub'
    fake.mkdir(parents=True, exist_ok=True)
    (fake / 'fancy-input.cfg').write_text('''# Disposable routing fixture; no host OS paths.
serial --unit=0 --speed=115200
set gfxmode=2560x1440,auto
set bourgeois_trace=1
menuentry 'Linux fixture' --id input-linux {
  terminal_output serial
  echo BOURGEOIS_INPUT_LINUX_OK
}
menuentry 'Windows fixture' --id input-windows {
  terminal_output serial
  echo BOURGEOIS_INPUT_WINDOWS_OK
}
set timeout=-1
bourgeois input-linux input-windows (memdisk)/boot/grub/bourgeois/courtyard-nameplates.png (memdisk)/boot/grub/bourgeois/traveler.png (memdisk)/boot/grub/bourgeois/traveler-gates.png (memdisk)/boot/grub/bourgeois/doorway.png
''')
    (fake / 'fancy-demo.cfg').write_text('''# Disposable recording fixture; no OS boot commands.
serial --unit=0 --speed=115200
set gfxmode=2560x1440,auto
set bourgeois_trace=1
menuentry 'Linux' --id demo-linux {
  terminal_output gfxterm serial
  echo 'Linux selected'
  sleep 6
}
menuentry 'Windows' --id demo-windows {
  terminal_output serial
  echo 'Windows selected'
}
set timeout=-1
bourgeois demo-linux demo-windows (memdisk)/boot/grub/bourgeois/courtyard-nameplates.png (memdisk)/boot/grub/bourgeois/traveler.png (memdisk)/boot/grub/bourgeois/traveler-gates.png (memdisk)/boot/grub/bourgeois/doorway.png
''')
    disk_file(base / 'root.btrfs', 512 * 1024**2)
    run('mkfs.btrfs', '-q', '-f', '-U', manifest['root_uuid'], '--rootdir', base / 'root',
        base / 'root.btrfs', stdout=subprocess.DEVNULL)


def prepare_esp(directory, stage, mode):
    esp = directory / 'esp/EFI/BOOT'
    esp.mkdir(parents=True, exist_ok=True)
    for source, target in [('shimx64.efi', 'BOOTX64.EFI'), ('mmx64.efi', 'mmx64.efi'),
                           ('grubx64.efi', 'grubx64.efi')]:
        shutil.copyfile(stage / source, esp / target)
    if mode == 'tampered':
        file = esp / 'grubx64.efi'
        image = bytearray(file.read_bytes())
        offset = image.find(b'BOURGEOIS_HOST_SHIM_LOCK_OK')
        if offset < 0:
            raise ValueError('Cannot locate embedded bootstrap marker for tampering test')
        image[offset] = ord('X')
        file.write_bytes(image)
    partition = directory / 'esp.img'
    disk_file(partition, 256 * 1024**2)
    run('mkfs.fat', '-F', '32', partition, stdout=subprocess.DEVNULL)
    run('mcopy', '-s', '-i', partition, directory / 'esp/EFI', '::/')
    disk = directory / 'esp-disk.img'
    disk_file(disk, 258 * 1024**2)
    run('sgdisk', '-n', '1:2048:+256M', '-t', '1:ef00', disk, stdout=subprocess.DEVNULL)
    with disk.open('r+b') as output, partition.open('rb') as source:
        output.seek(1024**2)
        shutil.copyfileobj(source, output)
    return disk


def screen(monitor, directory, name):
    file = directory / (name + '.ppm')
    monitor.command('screendump', {'filename': str(file)})
    with Image.open(file) as image:
        result = image.copy()
        image.save(directory / (name + '.png'))
    return result


def record_demo(monitor, directory, manifest):
    """Record actual GRUB frames; Linux selection ends in a routing fixture."""
    debug = directory / 'debug.log'
    serial = directory / 'serial.log'
    offset, serial_offset = debug.stat().st_size, serial.stat().st_size
    def press(name):
        monitor.command('send-key', {'keys': [{'type': 'qcode', 'data': name}]})
    lab.type_keys(monitor, 'configfile $prefix/fancy-demo.cfg\n')
    deadline = time.monotonic() + 15
    while 'BOURGEOIS_SCENE_READY' not in debug.read_text()[offset:]:
        if time.monotonic() >= deadline:
            raise RuntimeError('Recording scene did not start; inspect debug.log')
        time.sleep(0.05)
    press('left')
    time.sleep(1.8)
    frames, times, events = [], [], []
    actions = [(0.8, 'right'), (4.2, 'left'), (7.6, 'spc')]
    started = time.monotonic()
    capture = directory / 'demo-frame.ppm'
    while time.monotonic() - started < 10:
        tick = time.monotonic()
        elapsed = tick - started
        while actions and elapsed >= actions[0][0]:
            _, name = actions.pop(0)
            press(name)
            events.append({'key': name, 'at_ms': round(elapsed * 1000)})
        monitor.command('screendump', {'filename': str(capture)})
        with Image.open(capture) as shot:
            if shot.size != (2560, 1440):
                raise RuntimeError(f'Unexpected recording dimensions: {shot.size}')
            frames.append(shot.resize((1280, 720), Image.Resampling.NEAREST).convert('RGB'))
        times.append(time.monotonic() - started)
        time.sleep(max(0, 1 / 16 - (time.monotonic() - tick)))
    finished = time.monotonic()
    trace = debug.read_text()[offset:]
    if ('BOURGEOIS_SELECT_LINUX' not in trace or 'BOURGEOIS_SELECT_WINDOWS' in trace
            or 'Linux selected' not in serial.read_text(errors='replace')[serial_offset:]):
        raise RuntimeError('Recording did not finish by selecting the Linux fixture')
    # One shared palette prevents the static courtyard changing color each frame.
    palette = frames[0].quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    encoded = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    boundaries = [round((t - times[0]) * 100) * 10 for t in times]
    boundaries.append(round((finished - started - times[0]) * 100) * 10)
    durations = [max(10, b - a) for a, b in zip(boundaries, boundaries[1:])]
    gif = directory / 'fancy-demo.gif'
    encoded[0].save(gif, save_all=True, append_images=encoded[1:], duration=durations,
                    loop=0, disposal=1, optimize=False)
    # Extract the requested still from the encoded GIF, just before Space.
    poster_ms = (next(e['at_ms'] for e in events if e['key'] == 'spc')
                 - round(times[0] * 1000) - 300)
    with Image.open(gif) as animation:
        elapsed = 0
        for frame_number in range(animation.n_frames):
            animation.seek(frame_number)
            elapsed += animation.info.get('duration', 0)
            if elapsed >= poster_ms:
                animation.convert('RGB').save(directory / 'fancy-demo.png')
                break
        else:
            raise RuntimeError('Could not extract the Linux-gate still from the GIF')
        encoded_frames = animation.n_frames
    result = {'authenticode_sha256': manifest['authenticode_sha256'],
              'efi_sha256': manifest['files']['grubx64.efi'],
              'source_size': [2560, 1440], 'output_size': [1280, 720],
              'sampled_frames': len(frames), 'gif_frames': encoded_frames,
              'duration_ms': sum(durations), 'events': events,
              'poster_at_ms': poster_ms, 'linux_selected': True,
              'linux_boot': 'routing fixture; no kernel boot', 'secure_boot': True}
    (directory / 'demo.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f'Recorded {gif} and extracted fancy-demo.png ({encoded_frames} frames)', flush=True)


def check_gate(monitor, directory, direction, name, repeat=True):
    """A repeated arrow must leave the standing pose and gate hint unchanged."""
    arrow = {'keys': [{'type': 'qcode', 'data': direction}]}
    monitor.command('send-key', arrow)
    for sample in range(3):
        time.sleep(0.2)
        screen(monitor, directory, f'{name}-walk-{sample + 1}')
    # A complete walk across the courtyard takes under three seconds.
    time.sleep(3)
    previous = screen(monitor, directory, name)
    for _ in range(10):
        time.sleep(1)
        image = screen(monitor, directory, name)
        if image.tobytes() == previous.tobytes():
            break
        previous = image
    else:
        raise RuntimeError(f'Traveler did not settle at the {name} gate')
    if repeat:
        monitor.command('send-key', arrow)
        time.sleep(1)
        repeated = screen(monitor, directory, name + '-repeat')
        if repeated.tobytes() != image.tobytes():
            raise RuntimeError(f'Repeating {direction} changed the standing pose at {name}')
    return image


def benchmark_scene(monitor, directory, stage):
    """Measure the exact trusted image; enable port-E9 tracing only in the VM."""
    source = (stage / 'host.cfg').read_text()
    parsed = blocks(source)
    menus = [b for b in parsed if b.kind in ('menuentry', 'submenu')]
    top = [b for b in menus if b.kind == 'menuentry'
           and not any(p.start < b.start < p.end for p in menus)]
    ids = [entry_id(next(b for b in top if '--class ' + kind in b.header))
           for kind in ('gnu-linux', 'windows')]
    def press(name):
        monitor.command('send-key', {'keys': [{'type': 'qcode', 'data': name}]})
    press('c')
    time.sleep(1)
    lab.type_keys(monitor, 'set bourgeois_trace=1\n')
    lab.type_keys(monitor, 'set bourgeois_fps=60\n')
    command = ('bourgeois ' + ' '.join(ids)
               + ' (memdisk)/boot/grub/bourgeois/courtyard-nameplates.png'
               + ' (memdisk)/boot/grub/bourgeois/traveler.png'
               + ' (memdisk)/boot/grub/bourgeois/traveler-gates.png'
               + ' (memdisk)/boot/grub/bourgeois/doorway.png\n')
    debug = directory / 'debug.log'
    results = {}
    for profile in ('countdown', 'walking', 'manual'):
        offset = debug.stat().st_size
        if results:
            press('up')
            press('ret')
        else:
            lab.type_keys(monitor, command)
        for _ in range(150):
            if 'BOURGEOIS_SCENE_READY' in debug.read_text()[offset:]:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError('Benchmark scene did not start; inspect debug.log')
        started = time.monotonic()
        events = ([(0, 'right'), (1.3, 'left'), (2.6, 'right'), (4, 'left'), (5.5, 'right')]
                  if profile == 'walking' else [(0, 'spc')] if profile == 'manual' else [])
        while time.monotonic() - started < 8:
            elapsed = time.monotonic() - started
            while events and elapsed >= events[0][0]:
                press(events.pop(0)[1])
            time.sleep(0.02)
        press('esc')
        for _ in range(100):
            text = debug.read_text()[offset:]
            match = re.search(r'BOURGEOIS_RENDER ([^\n]+)', text)
            if match:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError('Benchmark render statistics did not appear')
        values = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', match[1])}
        if 'scene_ms' not in values:
            raise RuntimeError('This image uses original timing counters; use '
                               '--original-renderer or --original-timing instead')
        values['fps'] = round(values['frames'] * 1000 / values['scene_ms'], 1)
        results[profile] = values
        print(f'benchmark {profile}: {values}', flush=True)
        time.sleep(2)
    (directory / 'benchmark.json').write_text(json.dumps(results, indent=2) + '\n')


def check_controls(monitor, directory, original_timing=False):
    """Use native routing fixtures to check input timing and the full timer."""
    debug = directory / 'debug.log'
    serial = directory / 'serial.log'
    def press(name):
        monitor.command('send-key', {'keys': [{'type': 'qcode', 'data': name}]})
    def wait_for(file, marker, offset, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = file.read_text(errors='replace')[offset:]
            if marker in value:
                return value
            time.sleep(0.05)
        screen(monitor, directory, 'input-failure')
        raise RuntimeError(f'Input fixture did not produce {marker}')
    def start():
        offset, serial_offset = debug.stat().st_size, serial.stat().st_size
        lab.type_keys(monitor, 'configfile $prefix/fancy-input.cfg\n')
        wait_for(debug, 'BOURGEOIS_SCENE_READY', offset)
        return offset, serial_offset
    def leave(returned_entry=False):
        time.sleep(1)
        if returned_entry:
            press('spc')
            time.sleep(1)
        press('esc')
        time.sleep(1)
    results = {}
    offset, _ = start()
    press('spc')
    time.sleep(31)
    if 'BOURGEOIS_SELECT_' in debug.read_text()[offset:]:
        raise RuntimeError('Cancelled countdown booted a fixture')
    press('esc')
    wait_for(debug, 'BOURGEOIS_TECHNICAL', offset)
    leave()
    results['cancel_beyond_30_seconds'] = True
    print('input: cancellation beyond 30 seconds PASS', flush=True)

    offset, serial_offset = start()
    press('right')
    time.sleep(0.1)
    press('spc')
    time.sleep(2.5)
    if 'BOURGEOIS_SELECT_' in debug.read_text()[offset:]:
        raise RuntimeError('Space activated before arrival')
    press('spc')
    wait_for(debug, 'BOURGEOIS_SELECT_WINDOWS', offset)
    wait_for(serial, 'BOURGEOIS_INPUT_WINDOWS_OK', serial_offset)
    leave(True)
    results['space_only_at_gate'] = True
    print('input: Space only at Windows gate PASS', flush=True)

    for key_name, os_name in [('l', 'LINUX'), ('w', 'WINDOWS')]:
        offset, serial_offset = start()
        press(key_name)
        wait_for(debug, 'BOURGEOIS_SELECT_' + os_name, offset)
        wait_for(serial, 'BOURGEOIS_INPUT_' + os_name + '_OK', serial_offset)
        leave(True)
        results[key_name + '_immediate'] = True
    print('input: immediate L/W routing PASS', flush=True)

    offset, serial_offset = start()
    started = time.monotonic()
    wait_for(debug, 'BOURGEOIS_SELECT_LINUX', offset, timeout=40)
    value = wait_for(debug, 'BOURGEOIS_RENDER', offset)
    if original_timing:
        elapsed = round((time.monotonic() - started) * 1000)
        if not 29000 <= elapsed < 32000:
            raise RuntimeError(f'Unexpected observed automatic boot time: {elapsed} ms')
        frames = int(re.search(r'frames=(\d+)', value)[1])
        results['untouched_timer_observed_ms'] = elapsed
        results['untouched_timer_frames'] = frames
        results['untouched_timer_observed_fps'] = round(frames * 1000 / elapsed, 1)
    else:
        elapsed = int(re.search(r'scene_ms=(\d+)', value)[1])
        if not 30000 <= elapsed < 30100:
            raise RuntimeError(f'Unexpected automatic boot time: {elapsed} ms')
        results['untouched_timer_ms'] = elapsed
    wait_for(serial, 'BOURGEOIS_INPUT_LINUX_OK', serial_offset)
    leave(True)
    print(f'input: untouched timer PASS ({elapsed} ms)', flush=True)
    if original_timing:
        # The working renderer predates the FPS variable and profiling fields.
        (directory / 'input-checks.json').write_text(json.dumps(results, indent=2) + '\n')
        return

    # Keep the recovery cadence available in the same trusted image.
    offset, _ = start()
    time.sleep(1)
    press('esc')
    value = wait_for(debug, 'BOURGEOIS_RENDER', offset)
    if 'refresh_hz=25' not in value:
        raise RuntimeError('Default renderer did not select the recovery cadence')
    leave()
    print('input: default 25 FPS recovery cadence PASS', flush=True)
    results['default_refresh_hz'] = 25
    (directory / 'input-checks.json').write_text(json.dumps(results, indent=2) + '\n')


def check_case(base, stage, manifest, mode, benchmark=False, original_renderer=False,
               original_timing=False, demo=False):
    directory = base / mode
    directory.mkdir(exist_ok=True)
    esp = prepare_esp(directory, stage, mode)
    # Provision only a private OVMF variable-store file. --sb leaves Microsoft
    # firmware verification on; the host's MOK/SBAT state is never written.
    args = [sys.executable, '-m', 'virt.firmware.vars', '--input', VARS,
            '--output', directory / 'vars.fd', '--sb',
            '--set-sbat-level', base / 'sbat-level.csv']
    if mode != 'untrusted':
        args += ['--add-mok-hash', OWNER, manifest['authenticode_sha256']]
    run(*args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    socket = directory / 'qmp.sock'
    if len(str(socket).encode()) >= 108:
        raise ValueError('QMP socket path is too long; use --output /tmp/bourgeois-fancy-vm')
    args = ['qemu-system-x86_64', '-name', 'bourgeois-host-' + mode,
            '-machine', 'q35,smm=on', '-accel', 'tcg,thread=multi', '-global',
            'driver=cfi.pflash01,property=secure,value=on', '-m', '2048', '-nodefaults',
            '-drive', f'if=pflash,format=raw,unit=0,readonly=on,file={CODE}',
            '-drive', f'if=pflash,format=raw,unit=1,file={directory}/vars.fd',
            '-device', 'VGA,vgamem_mb=64,xres=2560,yres=1440',
            '-device', 'qemu-xhci', '-device', 'usb-kbd',
            '-drive', f'file={esp},format=raw,if=virtio,snapshot=on',
            '-drive', f'file={base}/root.btrfs,format=raw,if=virtio,snapshot=on',
            '-net', 'none', '-display', 'none', '-serial', f'file:{directory}/serial.log',
            '-qmp', f'unix:{socket},server=on,wait=off']
    if benchmark or original_renderer or original_timing or demo:
        args += ['-debugcon', f'file:{directory}/debug.log', '-global', 'isa-debugcon.iobase=0xe9']
    with (directory / 'qemu.log').open('w') as log:
        process = subprocess.Popen([str(a) for a in args], stdout=log, stderr=log)
        monitor = None
        old_vm = lab.VM
        try:
            lab.VM = directory
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError(f'QEMU failed; see {directory}/qemu.log')
                try:
                    monitor = lab.QMP()
                    break
                except (OSError, ConnectionError):
                    time.sleep(0.1)
            if monitor is None:
                raise RuntimeError('QEMU monitor did not appear')
            for _ in range(100):
                serial = (directory / 'serial.log').read_text(errors='replace')
                if 'BOURGEOIS_HOST_SHIM_LOCK_OK' in serial or 'Verification failed' in serial:
                    break
                time.sleep(0.4)
            if mode == 'trusted':
                if 'BOURGEOIS_HOST_SHIM_LOCK_OK' not in serial:
                    raise RuntimeError('Trusted image did not enter GRUB with shim_lock=y')
                for _ in range(45):
                    monitor.command('send-key', {'keys': [{'type': 'qcode', 'data': 'right'}]})
                    image = screen(monitor, directory, 'screen')
                    if image.getcolors(maxcolors=1024) is None:
                        break
                    time.sleep(1)
                if image.size != (2560, 1440) or image.getcolors(maxcolors=1024) is not None:
                    raise RuntimeError('Fancy did not render its 1440p courtyard')
                linux = check_gate(monitor, directory, 'left', 'linux-gate',
                                   repeat=benchmark or original_timing)
                windows = check_gate(monitor, directory, 'right', 'windows-gate',
                                     repeat=benchmark or original_timing)
                w, h = image.size
                actor_height = h // 7
                actor_width = actor_height * 5 // 8
                # The walking path between both standing poses must return
                # to the identical courtyard, with no trails from old frames.
                band = (w * 326 // 1672 + actor_width // 2 + 3,
                        h * 73 // 100 - actor_height,
                        w * 1358 // 1672 - actor_width // 2 - 3, h * 73 // 100)
                if linux.crop(band).tobytes() != windows.crop(band).tobytes():
                    raise RuntimeError('Walking left trails in the courtyard')
                monitor.command('send-key', {'keys': [{'type': 'qcode', 'data': 'esc'}]})
                time.sleep(5)
                screen(monitor, directory, 'technical')
                if 'prohibited' in (directory / 'serial.log').read_text(errors='replace'):
                    raise RuntimeError('Secure Boot blocked a dependency; inspect serial.log')
                if benchmark:
                    benchmark_scene(monitor, directory, stage)
                    check_controls(monitor, directory)
                elif original_renderer or original_timing:
                    monitor.command('send-key', {'keys': [{'type': 'qcode', 'data': 'c'}]})
                    time.sleep(1)
                    check_controls(monitor, directory, original_timing=True)
                elif demo:
                    monitor.command('send-key', {'keys': [{'type': 'qcode', 'data': 'c'}]})
                    time.sleep(1)
                    record_demo(monitor, directory, manifest)
            else:
                screen(monitor, directory, 'screen')
                if ('BOURGEOIS_HOST_SHIM_LOCK_OK' in serial
                        or not ('Verification failed' in serial or 'Security Violation' in serial)):
                    raise RuntimeError(f'{mode} image was not rejected by shim')
            print(f'{mode}: PASS ({directory})', flush=True)
        finally:
            if monitor is not None:
                try:
                    monitor.command('quit')
                except (OSError, ConnectionError):
                    pass
                finally:
                    monitor.close()
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
            lab.VM = old_vm


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, default=Path('build/fancy-controller'))
    parser.add_argument('--output', type=Path, default=Path('build/fancy-sb-check'))
    parser.add_argument('--benchmark', action='store_true',
                        help='measure rendering and test shortcuts, gate activation, and the full timer')
    parser.add_argument('--original-renderer', action='store_true',
                        help='check original controls and timer without later facing/FPS expectations')
    parser.add_argument('--original-timing', action='store_true',
                        help='use original timing counters while checking repeated-arrow facing')
    parser.add_argument('--record-demo', action='store_true',
                        help='record left/right/left walking and Linux fixture selection as a GIF and still')
    args = parser.parse_args()
    if (args.original_renderer or args.original_timing) and args.benchmark:
        parser.error('Original timing modes cannot use the newer --benchmark profiling format')
    if args.original_renderer and args.original_timing:
        parser.error('Select --original-timing to require repeated-arrow facing checks')
    if args.record_demo and (args.benchmark or args.original_renderer or args.original_timing):
        parser.error('--record-demo uses its own input sequence; select one recording/check mode')
    try:
        for name in ('qemu-system-x86_64', 'mkfs.btrfs', 'mkfs.fat', 'mcopy', 'sgdisk', 'mokutil'):
            if shutil.which(name) is None:
                raise ValueError(f'Missing {name}; see docs/research/host-fancy.adoc for prerequisites')
        if not CODE.is_file() or not VARS.is_file():
            raise ValueError('Microsoft-keyed Secure Boot OVMF firmware is missing; install ovmf')
        base, stage = args.output.resolve(), args.stage.resolve()
        if base.exists():
            raise ValueError('Use a new output directory to preserve previous evidence')
        manifest = json.loads((stage / 'manifest.json').read_text())
        verify_files(stage, manifest)
        base.mkdir(parents=True)
        (base / 'sbat-level.csv').write_text(subprocess.check_output(
            ['mokutil', '--list-sbat-revocations'], text=True))
        prepare_root(base, manifest)
        for mode in (('trusted',) if args.record_demo else ('trusted', 'untrusted', 'tampered')):
            check_case(base, stage, manifest, mode, args.benchmark and mode == 'trusted',
                       args.original_renderer and mode == 'trusted',
                       args.original_timing and mode == 'trusted', args.record_demo)
        print('Inspect trusted/screen.png and trusted/technical.png before a host trial.')
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f'bourgeois: {error}')


if __name__ == '__main__':
    main()
