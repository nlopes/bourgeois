"""Preserve distribution boot commands when generating the Fancy host menu."""
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

from grub_config import blocks, entry_id, hook

MEM = '(memdisk)/boot/grub/bourgeois'
LIVE_CONFIG = Path('boot/grub/bourgeois-fancy.cfg')


CLEAN_HOOK = '''### BEGIN /etc/grub.d/99_clean_menu ###
if [ -f $prefix/clean-menu.cfg ]; then
  configfile $prefix/clean-menu.cfg
fi
set theme=$prefix/themes/clean/recovery.txt
### END /etc/grub.d/99_clean_menu ###'''


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


def refresh(source, root=Path('/'), run=None):
    """Publish the current kernel menu atomically; never retain a stale menu."""
    if root != Path('/') and run is None:
        raise ValueError('An isolated root requires an isolated command runner')
    run = run or (lambda args: subprocess.run(args, check=True))
    destination = root / LIVE_CONFIG
    temporary = None
    try:
        content, _ = configuration(source, (root / 'boot/grub/clean-menu.cfg').read_text())
        fd, name = tempfile.mkstemp(prefix='.bourgeois-fancy-', dir=destination.parent)
        temporary = Path(name)
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), 0o600)
        run(['grub-script-check', str(temporary)])
        os.replace(temporary, destination)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    try:
        if not stat.S_ISREG(os.fstat(1).st_mode):
            raise ValueError('generation output must be a regular configuration file')
        refresh(Path('/proc/self/fd/1').read_text())
    except Exception as error:
        (Path('/') / LIVE_CONFIG).unlink(missing_ok=True)
        print(f'Fancy menu unavailable; using the distribution menu: {error}', file=sys.stderr)


if __name__ == '__main__':
    main()
