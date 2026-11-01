"""Build the GPLv3+ GRUB module in the pinned Ubuntu guest."""
from pathlib import Path
import argparse
import subprocess
import sys

import lab
from preview import upload, put_text
from host_checks import HostSetupError, require_tools

SOURCE_ARCHIVES = ('grub2-unsigned_2.12.orig.tar.xz', 'grub2-unsigned_2.12-1ubuntu7.3.debian.tar.xz',
                   'grub2-unsigned_2.12-1ubuntu7.3.dsc')

SOURCE = '/home/bourgeois/grub-source/grub2-unsigned-2.12'
FONT_SIZES = (20, 40, 60, 80, 100, 120)


def require_guest():
    require_tools('lab')
    if not (lab.VM / 'id_ed25519').is_file():
        raise HostSetupError('The disposable lab is not initialized. Run make vm first, '
                             'then python3 tools/lab.py wait.')
    try:
        with lab.QMP() as monitor:
            monitor.command('query-status')
    except (OSError, ConnectionError) as error:
        raise HostSetupError('The disposable lab is stopped. Run make vm first. '
                             'If it fails, inspect build/vm/qemu.log.') from error
    lab.wait_ssh()


def build():
    require_guest()
    versions = lab.ssh("dpkg-query -W -f='${Version}\\n' grub-common grub-efi-amd64-bin",
                       capture_output=True, text=True).stdout.splitlines()
    if versions != ['2.12-1ubuntu7.3', '2.12-1ubuntu7.3']:
        raise RuntimeError(f'Native preview requires GRUB 2.12-1ubuntu7.3; got {versions}')
    upload(lab.ROOT / 'fancy', '/home/bourgeois/fancy')
    put_text('/home/bourgeois/build-native.sh', '''#!/bin/sh
set -eu
sudo sed -i 's/^Types: deb$/Types: deb deb-src/' /etc/apt/sources.list.d/ubuntu.sources
sudo apt-get update -qq
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq build-essential bison flex autoconf automake autopoint gettext libtool pkg-config libfreetype-dev libdevmapper-dev liblzma-dev efibootmgr fonts-dejavu-core
command -v grub-mkfont >/dev/null || { echo 'grub-mkfont is missing in the guest; install grub2-common there.' >&2; exit 1; }
mkdir -p /home/bourgeois/native-fonts
for size in 20 40 60 80 100 120; do
  grub-mkfont --name='Bourgeois UI' --size="$size" --range=0x20-0x7e --output="/home/bourgeois/native-fonts/menu-$size.pf2" /usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf
done
mkdir -p /home/bourgeois/grub-source
cd /home/bourgeois/grub-source
if [ ! -d grub2-unsigned-2.12 ]; then
  apt-get source grub2-unsigned=2.12-1ubuntu7.3
fi
cd grub2-unsigned-2.12
cp /home/bourgeois/fancy/bourgeois.c grub-core/commands/
cp /home/bourgeois/fancy/state.h grub-core/commands/
cp /home/bourgeois/fancy/layout.h grub-core/commands/
if ! grep -q 'name = bourgeois;' grub-core/Makefile.core.def; then
  cat >> grub-core/Makefile.core.def <<'EOF'
module = {
  name = bourgeois;
  common = commands/bourgeois.c;
  enable = x86_64_efi;
};
EOF
  ./autogen.sh
fi
if [ ! -f Makefile ]; then
./configure --with-platform=efi --target=x86_64 --disable-werror --disable-nls --disable-efiemu --disable-grub-mkfont
fi
make -C grub-core -j2 bourgeois.module build-grub-module-verifier genmod.sh
rm -rf /home/bourgeois/native-modules
cp -a /usr/lib/grub/x86_64-efi /home/bourgeois/native-modules
printf 'bourgeois: bitmap_scale font video normal bitmap gfxmenu gfxterm gfxterm_background\n' >> /home/bourgeois/native-modules/moddep.lst
cd grub-core
sh genmod.sh /home/bourgeois/native-modules/moddep.lst bourgeois.module build-grub-module-verifier /home/bourgeois/native-modules/bourgeois.mod
''', '755')
    try:
        lab.ssh('sh /home/bourgeois/build-native.sh > /tmp/bourgeois-native.log 2>&1')
    except subprocess.CalledProcessError as error:
        lab.ssh('tail -n 50 /tmp/bourgeois-native.log')
        raise HostSetupError('Native build failed inside the disposable guest. '
                             'See the log above; the full log is /tmp/bourgeois-native.log in the guest.') from error
    cache = lab.BUILD / 'native' / 'upstream-source'
    cache.mkdir(parents=True, exist_ok=True)
    for name in SOURCE_ARCHIVES:
        with (cache / name).open('wb') as stream:
            lab.ssh(f'cat /home/bourgeois/grub-source/{name}', stdout=stream)
    fonts = lab.BUILD / 'native' / 'fonts'
    fonts.mkdir(parents=True, exist_ok=True)
    for size in FONT_SIZES:
        with (fonts / f'menu-{size}.pf2').open('wb') as stream:
            lab.ssh(f'cat /home/bourgeois/native-fonts/menu-{size}.pf2', stdout=stream)
    print('Native GRUB build complete')


def image():
    require_guest()
    lab.ssh("test -f /home/bourgeois/native-modules/bourgeois.mod || "
            "{ echo 'Native module missing: run make native-build first.' >&2; exit 1; }")
    # A separate EFI image leaves the distribution EFI image intact.
    boot_uuid = lab.ssh('findmnt -n -o UUID /boot', capture_output=True, text=True).stdout.strip()
    bootstrap = f'''search --no-floppy --fs-uuid --set=root {boot_uuid}
set prefix=($root)/grub
configfile $prefix/grub.cfg
'''
    put_text('/home/bourgeois/bootstrap.cfg', bootstrap)
    lab.ssh(f'grub-mkstandalone -O x86_64-efi -d /home/bourgeois/native-modules -o /home/bourgeois/bourgeois.efi --fonts="" --locales="" --modules="part_gpt ext2 normal configfile all_video png font gfxterm gfxterm_background serial sleep test search search_fs_uuid linux bourgeois" "boot/grub/grub.cfg=/home/bourgeois/bootstrap.cfg"')
    output = lab.BUILD / 'native'
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'bourgeois.efi').open('wb') as stream:
        lab.ssh('cat /home/bourgeois/bourgeois.efi', stdout=stream)
    # Keep Ubuntu's image intact and use a separate directory on the lab ESP.
    lab.ssh("sudo mkdir -p /boot/efi/EFI/bourgeois && sudo cp /home/bourgeois/bourgeois.efi /boot/efi/EFI/bourgeois/grubx64.efi")
    lab.ssh("sudo efibootmgr | grep -q 'bourgeois preview' || sudo efibootmgr -c -d /dev/vda -p 15 -L 'bourgeois preview' -l '\\EFI\\bourgeois\\grubx64.efi'")
    select_boot('fancy')
    print(output / 'bourgeois.efi')


def select_boot(edition):
    import re
    entries = lab.ssh('sudo efibootmgr', capture_output=True, text=True).stdout
    label = 'bourgeois preview' if edition == 'fancy' else 'Ubuntu'
    matches = re.findall(r'^Boot([0-9A-Fa-f]{4})\*?\s+' + re.escape(label) + r'(?:\s|$)', entries, re.M)
    if len(matches) != 1:
        raise RuntimeError(f'Expected one EFI entry for {label}: {entries}')
    current = re.search(r'^BootOrder: (.*)$', entries, re.M).group(1).split(',')
    order = [matches[0]] + [entry for entry in current if entry != matches[0]]
    lab.ssh('sudo efibootmgr -o ' + ','.join(order))
    lab.ssh('sync')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'image'])
    args = parser.parse_args()
    try:
        build() if args.command == 'build' else image()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f'bourgeois: {error}')
