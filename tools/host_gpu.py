"""Read-only GPU recommendations and firmware setup guidance for the host."""
import argparse
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

from host_checks import HostSetupError

VENDORS = {'8086': 'Intel', '10de': 'NVIDIA', '1002': 'AMD', '1a03': 'ASPEED'}


def read(file, default=None):
    try:
        return file.read_text().strip()
    except OSError:
        return default


def model_names(which=None, run=None):
    which, run = which or shutil.which, run or subprocess.run
    executable = which('lspci')
    if not executable:
        return {}, ['Optional lspci is missing; PCI IDs still identify the GPUs. '
                    'For model names on Ubuntu: sudo apt install pciutils.']
    try:
        result = run([executable, '-Dmm', '-d', '::03xx'], check=False,
                     capture_output=True, text=True, timeout=5)
        if result.returncode:
            raise HostSetupError('lspci returned an error')
        names = {}
        for line in result.stdout.splitlines():
            fields = shlex.split(line)
            if len(fields) >= 4:
                names[fields[0]] = fields[2] + ' ' + fields[3]
        return names, []
    except (OSError, ValueError, subprocess.TimeoutExpired, HostSetupError):
        return {}, ['lspci could not read model names; using kernel PCI IDs. '
                    'Check the pciutils installation and permissions.']


def kind(address, vendor, name):
    # Vendor alone is insufficient: Intel and AMD sell both kinds of GPU.
    if vendor == '8086' and any(word in name for word in ('UHD Graphics', 'HD Graphics', 'Iris')):
        if 'MAX' not in name:
            return 'integrated'
    if vendor == '10de' and any(word in name for word in ('GeForce RTX', 'GeForce GTX', 'Quadro', 'Tesla')):
        return 'discrete'
    if vendor == '8086' and any(word in name for word in ('DG1', 'DG2')):
        return 'discrete'
    if vendor == '8086' and address.endswith(':00:02.0'):
        return 'likely integrated (PCI topology)'
    return 'unknown; vendor alone does not establish GPU type'


def discover(sysfs=Path('/sys'), *, names=None):
    sysfs = Path(sysfs)
    directory = sysfs / 'bus/pci/devices'
    try:
        devices = sorted(directory.iterdir())
    except OSError as error:
        raise HostSetupError(f'Cannot read Linux PCI hardware at {directory}: {error.strerror}. '
                             'Run this command on the Linux host with /sys mounted; '
                             'containers may hide the hardware.') from error
    names = names or {}
    gpus, notes = [], []
    for device in devices:
        try:
            device_class = int((device / 'class').read_text().strip(), 16)
        except (OSError, ValueError):
            notes.append(f'Could not read the PCI class for {device.name}; that device was skipped.')
            continue
        if device_class >> 16 != 3:
            continue
        vendor = read(device / 'vendor', 'unknown').removeprefix('0x')
        identifier = read(device / 'device', 'unknown').removeprefix('0x')
        name = names.get(device.name, f'{VENDORS.get(vendor, "GPU")} [{vendor}:{identifier}]')
        flag = read(device / 'boot_vga')
        gpus.append({'pci': device.name, 'name': name, 'vendor': vendor, 'device': identifier,
                     'kind': kind(device.name, vendor, name),
                     'driver': (device / 'driver').resolve().name if (device / 'driver').exists() else None,
                     'boot_vga': True if flag == '1' else False if flag == '0' else None,
                     'connectors': []})
    if not gpus:
        raise HostSetupError('No readable PCI graphics controllers were found. '
                             'Run on the host instead of a restricted container. '
                             'A GPU disabled in firmware will not appear in this list.')
    by_pci = {gpu['pci']: gpu for gpu in gpus}
    drm = sysfs / 'class/drm'
    if not drm.is_dir():
        notes.append('Linux DRM connector information is unavailable; monitor routing is unknown. '
                     'Check that /sys is mounted and a Linux graphics driver is loaded.')
    for card in sorted(drm.glob('card*')):
        if not re.fullmatch(r'card\d+', card.name):
            continue
        gpu = by_pci.get((card / 'device').resolve().name)
        if gpu is None:
            continue
        for connector in sorted(drm.glob(card.name + '-*')):
            status = read(connector / 'status', 'unknown')
            modes = list(dict.fromkeys(value for value in read(connector / 'modes', '').splitlines()
                                       if re.fullmatch(r'\d+x\d+', value)))
            gpu['connectors'].append({'name': connector.name[len(card.name) + 1:],
                                      'status': status, 'linux_modes': modes})
    for gpu in gpus:
        if gpu['driver'] is None:
            notes.append(f'{gpu["pci"]} has no bound Linux driver. Connected-output information may be missing; '
                         'check the distribution graphics driver setup. Firmware graphics can still work.')
    return gpus, notes


def connected(gpu):
    return [connector for connector in gpu['connectors'] if connector['status'] == 'connected']


def recommend(gpus):
    def score(gpu):
        return (4 if gpu['boot_vga'] is True else 0) + (2 if connected(gpu) else 0)
    maximum = max(map(score, gpus))
    candidates = [gpu for gpu in gpus if score(gpu) == maximum]
    if len(candidates) == 1 and (maximum or len(gpus) == 1):
        gpu = candidates[0]
        reasons = []
        if gpu['boot_vga'] is True:
            reasons.append('marked as the firmware boot VGA device')
        if connected(gpu):
            reasons.append('has connected display output ' + ', '.join(c['name'] for c in connected(gpu)))
        return gpu, '; '.join(reasons) or 'the only detected graphics controller'
    return None, 'The available boot/display evidence does not identify one GPU; choose a PCI address to inspect.'


def select(gpus, value):
    if value == 'auto':
        selected, reason = recommend(gpus)
        if selected is None:
            raise HostSetupError(reason)
        return selected
    matches = [gpu for index, gpu in enumerate(gpus, 1)
               if value in (str(index), gpu['pci'])
               or (value in ('integrated', 'discrete') and value in gpu['kind'])]
    if len(matches) != 1:
        raise HostSetupError(f'GPU choice {value!r} is missing or ambiguous. '
                             'Use one PCI address from the detected list.')
    return matches[0]


def guidance(gpu):
    outputs = ', '.join(c['name'] for c in connected(gpu)) or 'no connected Linux output reported'
    lines = [f'Setup guidance for {gpu["name"]} ({gpu["pci"]}):', f'Display: {outputs}.']
    if gpu['boot_vga'] is True and connected(gpu):
        lines.append('Keep the monitor on this card and retain the current UEFI primary-display setting.')
    else:
        port = 'a motherboard display output' if 'integrated' in gpu['kind'] else 'a display output on this GPU'
        setting = 'Integrated/IGD' if 'integrated' in gpu['kind'] else 'PCIe/PEG' if gpu['kind'] == 'discrete' else 'this adapter'
        lines += [f'To use it before Linux starts, connect the monitor to {port}.',
                  f'In UEFI setup, enable the adapter and choose {setting} as the primary display, if supported.',
                  'Reboot and check that the firmware screen and GRUB appear on that output.']
    lines += ['This selection shows guidance only. Stock GRUB uses firmware-provided graphics; '
              'this tool does not switch GPUs, change Linux drivers, or write firmware settings.',
              'Linux connector modes do not establish which resolutions GRUB can use. '
              'Keep the display mode already verified in GRUB until testing another one.']
    return '\n'.join(lines)


def print_inventory(gpus, notes):
    print('Graphics adapters (read-only inspection):')
    for index, gpu in enumerate(gpus, 1):
        outputs = ', '.join(c['name'] for c in connected(gpu)) or 'none reported'
        flag = 'yes' if gpu['boot_vga'] is True else 'no' if gpu['boot_vga'] is False else 'not reported'
        print(f'  {index}. {gpu["name"]} [{gpu["pci"]}]')
        print(f'     Type: {gpu["kind"]}; Linux driver: {gpu["driver"] or "unbound"}; '
              f'boot VGA: {flag}; connected: {outputs}')
    for note in notes:
        print(f'Note: {note}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gpu', default='auto', help='auto, a PCI address, integrated, discrete, or list number')
    parser.add_argument('--select', action='store_true', help='interactively choose a GPU for setup guidance')
    parser.add_argument('--json', action='store_true', help='print the inventory and recommendation as JSON')
    args = parser.parse_args()
    try:
        names, notes = model_names()
        gpus, detection_notes = discover(names=names)
        notes += detection_notes
        recommended, reason = recommend(gpus)
        if args.json:
            if args.select:
                parser.error('--json cannot be combined with --select')
            chosen = select(gpus, args.gpu) if args.gpu != 'auto' else recommended
            print(json.dumps({'gpus': gpus, 'recommended_pci': recommended['pci'] if recommended else None,
                              'selected_pci': chosen['pci'] if chosen else None,
                              'reason': reason, 'notes': notes}, indent=2))
            return 0
        print_inventory(gpus, notes)
        print(f'\nRecommendation: {recommended["name"] if recommended else "no automatic choice"}. {reason}.')
        value = args.gpu
        if args.select:
            if not sys.stdin.isatty():
                raise HostSetupError('Interactive selection needs a terminal. Use --gpu with a listed PCI address.')
            default = recommended['pci'] if recommended else None
            prompt = f'\nGPU to inspect (number or PCI address{", Enter for " + default if default else ""}): '
            value = input(prompt).strip() or default
            if value is None:
                raise HostSetupError('Choose a listed GPU number or PCI address.')
        if value != 'auto' or recommended is not None:
            print('\n' + guidance(select(gpus, value)))
    except (HostSetupError, OSError, EOFError) as error:
        print(f'bourgeois: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
