"""Build an isolated Fancy EFI trial for the inspected Ubuntu 26.04 host.

This command writes only build artifacts. It never enrolls trust or changes EFI.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from grub_config import blocks, entry_id, hook
from host_checks import FONT

ROOT = Path(__file__).resolve().parent.parent
VERSION = '2.14-2ubuntu1'
MEM = '(memdisk)/boot/grub/bourgeois'
CLEAN_HOOK = '''### BEGIN /etc/grub.d/99_clean_menu ###
if [ -f $prefix/clean-menu.cfg ]; then
  configfile $prefix/clean-menu.cfg
fi
set theme=$prefix/themes/clean/recovery.txt
### END /etc/grub.d/99_clean_menu ###'''
# Ubuntu's debian/build-efi-images GRUB_MODULES, plus Fancy dependencies.
MODULES = '''boot btrfs cat chain configfile echo efi_gop efifwsetup efinet ext2
fat font gettext gfxmenu gfxterm gfxterm_background gzio halt help hfsplus
iso9660 jpeg keystatus loadenv loopback linux ls lsefi lsefimmap lsefisystab
lssal memdisk minicmd normal part_apple part_msdos part_gpt password_pbkdf2
peimage png probe reboot regexp search search_fs_uuid search_fs_file search_label
serial sleep smbios squash4 test tpm true video xfs zfs zfscrypt zfsinfo cpuid play
cryptodisk gcry_arcfour gcry_blowfish gcry_camellia gcry_cast5 gcry_crc gcry_des
gcry_dsa gcry_idea gcry_md4 gcry_md5 gcry_rfc2268 gcry_rijndael gcry_rmd160
gcry_rsa gcry_seed gcry_serpent gcry_sha1 gcry_sha256 gcry_sha512 gcry_tiger
gcry_twofish gcry_whirlpool luks lvm mdraid09 mdraid1x raid5rec raid6rec
bitmap bitmap_scale bourgeois all_video'''.split()


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def digest(file):
    with Path(file).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def native_menus(source):
    return [(b.header, source[b.opening:b.end]) for b in blocks(source)
            if b.kind in ('menuentry', 'submenu')]


def configuration(source, clean):
    """Replace only the known scene hook and font paths; keep native menus."""
    entries = [b for b in blocks(clean) if b.kind == 'menuentry']
    if (len(entries) != 2 or '--class gnu-linux' not in entries[0].header
            or '--class windows' not in entries[1].header):
        raise ValueError('Expected the existing Linux-first, two-entry clean menu')
    original = [b for b in blocks(source) if b.kind == 'menuentry']
    for chosen in entries:
        matches = [b for b in original if entry_id(b) == entry_id(chosen)]
        if (entry_id(chosen) is None or len(matches) != 1
                or source[matches[0].opening:matches[0].end] != clean[chosen.opening:chosen.end]):
            raise ValueError('Clean-menu boot commands differ from the full menu')
    if source.count(CLEAN_HOOK) != 1:
        raise ValueError('Unrecognized clean-menu hook; inspect before adapting it')
    scene = hook('fancy', *(entry_id(b) for b in entries))
    scene = scene.replace('$prefix/bourgeois', MEM).replace('set bourgeois_trace=1',
                                                          'set bourgeois_trace=0')
    scene = scene.replace('insmod all_video', 'insmod efi_gop')
    output = source.replace(CLEAN_HOOK, scene)
    # GRUB 2.14 prohibits unverified disk fonts under Secure Boot. The memdisk
    # is inside the EFI executable verified by shim, so its fonts are trusted.
    for old, new in [('loadfont $font', f'loadfont {MEM}/unicode.pf2'),
                     ('loadfont ($root)/boot/grub/themes/bourgeois/menu.pf2',
                      f'loadfont {MEM}/menu-40.pf2')]:
        if output.count(old) != 1:
            raise ValueError(f'Unrecognized host font initialization: {old}')
        output = output.replace(old, new)
    output = output.replace('loadfont unicode', f'loadfont {MEM}/unicode.pf2')
    if native_menus(output) != native_menus(source):
        raise ValueError('Refusing to change native menu definitions')
    uuids = re.findall(r'root=UUID=([0-9a-f-]+)', clean)
    if not uuids or len(set(uuids)) != 1:
        raise ValueError('Expected one native Linux root UUID')
    # This first host trial supports /boot on the Linux root, not a separate
    # /boot partition or an uninspected Btrfs subvolume layout.
    if not re.search(r'\blinux\s+/boot/vmlinuz-', clean):
        raise ValueError('This trial requires the inspected /boot-on-root layout')
    return output, uuids[0]


def bootstrap(uuid):
    return f'''serial --unit=0 --speed=115200
terminal_output console serial
if [ "${{shim_lock}}" != "y" ]; then
  echo 'Fancy trial requires shim Secure Boot verification. Returning to firmware.'
  sleep --interruptible 10
  exit
fi
echo BOURGEOIS_HOST_SHIM_LOCK_OK
if search --no-floppy --fs-uuid --set=root {uuid}; then
  set prefix=($root)/boot/grub
  configfile (memdisk)/boot/grub/host.cfg
else
  echo 'Host boot filesystem missing. Returning to firmware.'
  sleep --interruptible 10
  exit
fi
'''


def compile_module(source, build, module_source):
    """Compile against configured distribution headers without autoreconf."""
    changelog = (source / 'debian/changelog').read_text().splitlines()[0]
    if not changelog.startswith(f'grub2-unsigned ({VERSION})'):
        raise ValueError(f'Requires authenticated Ubuntu grub2-unsigned {VERSION} source')
    build.mkdir(parents=True, exist_ok=True)
    with (build / 'configure.log').open('w') as log:
        run(source / 'configure', '--with-platform=efi', '--target=x86_64',
            '--disable-werror', '--disable-nls', '--disable-efiemu', '--disable-grub-mkfont',
            cwd=build, stdout=log, stderr=subprocess.STDOUT)
    incs = ['-I' + str(p) for p in (build, build / 'include', source, source / 'include')]
    flags = '''-std=gnu99 -fno-common -Os -m64 -Wall -Wextra -Werror -Wformat=2
    -Wstrict-prototypes -ffreestanding
    -fno-PIE -fno-pie -fno-stack-protector -mno-red-zone -mcmodel=large -mno-mmx
    -mno-sse -mno-sse2 -mno-sse3 -mno-3dnow -msoft-float
    -fno-asynchronous-unwind-tables -fno-unwind-tables -fno-ident'''.split()
    run('gcc', *incs, *flags, '-DHAVE_CONFIG_H', '-DGRUB_MACHINE_EFI=1',
        '-DGRUB_MACHINE=X86_64_EFI', '-DGRUB_FILE="bourgeois.c"', '-c',
        module_source, '-o', build / 'bourgeois.o')
    core = build / 'grub-core'
    run('gcc', '-m64', '-nostdlib', '-no-pie', '-Wl,--build-id=none', '-Wl,-r',
        '-o', core / 'bourgeois.module', build / 'bourgeois.o')
    verifier = core / 'build-grub-module-verifier'
    run('gcc', *incs, '-std=gnu99', '-fno-common', '-DGRUB_BUILD=1', '-DGRUB_UTIL=1',
        '-DGRUB_FILE="module-verifier"', '-DGRUB_BUILD_PROGRAM_NAME="build-grub-module-verifier"',
        *(source / p for p in ('util/grub-module-verifier.c', 'util/grub-module-verifier32.c',
                              'util/grub-module-verifier64.c', 'grub-core/kern/emu/misc.c',
                              'util/misc.c')), '-o', verifier)
    run('./config.status', f'--file=grub-core/genmod.sh:{source}/grub-core/genmod.sh.in',
        cwd=build, stdout=subprocess.DEVNULL)
    modules = build / 'modules'
    if modules.exists():
        shutil.rmtree(modules)
    shutil.copytree('/usr/lib/grub/x86_64-efi', modules)
    deps = modules / 'moddep.lst'
    deps.write_text(deps.read_text().rstrip() + '\nbourgeois: bitmap_scale font video normal '
                    'bitmap gfxmenu gfxterm gfxterm_background\n')
    run('sh', 'genmod.sh', deps, 'bourgeois.module', verifier, modules / 'bourgeois.mod', cwd=core)
    return modules


def authenticode(image, pesign):
    # sha256sum hashes different bytes; MOK requires the PE/Authenticode digest.
    result = run(pesign, '--hash', '--in', image, capture_output=True, text=True).stdout
    match = re.fullmatch(r'([0-9a-fA-F]{64})\s+.+\s*', result)
    if not match:
        raise ValueError(f'Unexpected pesign hash output: {result!r}')
    return match[1].lower()


def stage(source, build, snapshot, output, pesign, module_source=None):
    source, build, snapshot, output = [p.resolve() for p in (source, build, snapshot, output)]
    module_source = (module_source or ROOT / 'fancy/bourgeois.c').resolve()
    if not module_source.is_file():
        raise ValueError(f'Native module source is missing: {module_source}')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output must be empty; use a new stage directory to preserve reviewed images')
    for name in ('gcc', 'objcopy', 'strip', 'grub-mkstandalone', 'grub-mkfont',
                 'grub-script-check', 'bison', 'flex', pesign):
        if shutil.which(name) is None:
            raise ValueError(f'Missing {name}. See docs/research/host-fancy.adoc for prerequisites.')
    installed = run('dpkg-query', '-W', '-f=${Version}', 'grub-efi-amd64-bin',
                    capture_output=True, text=True).stdout
    if installed != VERSION:
        raise ValueError(f'This inspected trial targets GRUB {VERSION}; installed {installed}')
    full = (snapshot / 'grub.cfg').read_text()
    clean = (snapshot / 'clean-menu.cfg').read_text()
    config, uuid = configuration(full, clean)
    if 'set gfxmode=2560x1440,auto\n' not in full:
        raise ValueError('Expected the host-verified 2560x1440 setting')
    modules = compile_module(source, build, module_source)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'host.cfg').write_text(config)
    (output / 'bootstrap.cfg').write_text(bootstrap(uuid))
    assets = output / 'bourgeois'
    assets.mkdir()
    for name in ('courtyard-nameplates.png', 'traveler.png', 'traveler-gates.png'):
        shutil.copyfile(ROOT / 'assets' / name, assets / name)
    shutil.copyfile(ROOT / 'assets/DejaVu-font-license.txt', assets / 'font-license.txt')
    shutil.copyfile('/usr/share/grub/unicode.pf2', assets / 'unicode.pf2')
    for size in (20, 40, 60, 80, 100, 120):
        run('grub-mkfont', '--name=Bourgeois UI', f'--size={size}', '--range=0x20-0x7e',
            f'--output={assets}/menu-{size}.pf2', FONT, stdout=subprocess.DEVNULL)
    # Always supply a separate output: objcopy otherwise tries rewriting its input.
    run('objcopy', '--dump-section', f'.sbat={output}/sbat.raw',
        '/usr/lib/grub/x86_64-efi/monolithic/grubx64.efi', output / 'sbat-copy.efi')
    (output / 'sbat-copy.efi').unlink()
    sbat = (output / 'sbat.raw').read_bytes().rstrip(b'\0')
    if not sbat.startswith(b'sbat,') or not sbat.endswith(b'\n'):
        raise ValueError('Missing distribution SBAT revocation metadata')
    (output / 'sbat.csv').write_bytes(sbat + b'bourgeois,1,bourgeois,host-fancy-trial,1,'
                                    b'https://github.com/nlopes/bourgeois\n')
    image = output / 'grubx64.efi'
    grafts = [f'boot/grub/grub.cfg={output}/bootstrap.cfg',
              f'boot/grub/host.cfg={output}/host.cfg']
    grafts += [f'boot/grub/bourgeois/{p.name}={p}' for p in sorted(assets.iterdir())]
    run('grub-mkstandalone', '-O', 'x86_64-efi', '-d', modules, '-o', image,
        '--fonts=', '--locales=', '--themes=', f'--sbat={output}/sbat.csv',
        '--modules=' + ' '.join(MODULES), '--install-modules=' + ' '.join(MODULES), *grafts)
    for name in ('host.cfg', 'bootstrap.cfg'):
        run('grub-script-check', output / name)
    # Package the installed Microsoft-signed shim and its matching MokManager.
    shutil.copyfile('/usr/lib/shim/shimx64.efi.signed', output / 'shimx64.efi')
    shutil.copyfile('/usr/lib/shim/mmx64.efi', output / 'mmx64.efi')
    auth = authenticode(image, pesign)
    (output / 'authenticode-sha256.txt').write_text(auth + '\n')
    manifest = {'format': 1, 'grub_version': VERSION, 'root_uuid': uuid,
                'authenticode_sha256': auth,
                'native_sources': {p.name: digest(p) for p in
                                   [module_source, *sorted(module_source.parent.glob('*.h'))]},
                'snapshots': {name: digest(snapshot / name) for name in ('grub.cfg', 'clean-menu.cfg')},
                'files': {name: digest(output / name) for name in
                          ('grubx64.efi', 'shimx64.efi', 'mmx64.efi')}}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Staged {image}\nMOK Authenticode SHA256: {auth}\nHost boot configuration unchanged.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'build/host-fancy-source/grub2-unsigned-2.14')
    parser.add_argument('--build', type=Path, default=ROOT / 'build/host-fancy-native')
    parser.add_argument('--snapshot', type=Path, default=ROOT / 'build/host-fancy-inspect')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/fancy-controller')
    parser.add_argument('--pesign', default='pesign')
    parser.add_argument('--module-source', type=Path,
                        help='use an isolated native renderer source for a regression trial')
    args = parser.parse_args()
    try:
        stage(args.source, args.build, args.snapshot, args.output, args.pesign, args.module_source)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(f'bourgeois: {error}')


if __name__ == '__main__':
    main()
