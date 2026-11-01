"""Prepare preview files and install them only in the disposable lab guest."""
import argparse
import io
import json
from pathlib import Path
import re
import shutil
import tarfile

import lab
from grub_config import generate, hook, blocks, entry_id
import theme

STAGE = lab.BUILD / 'preview'


def put_text(path, text, mode=None):
    lab.ssh(f'cat > {path}', input=text, text=True)
    if mode:
        lab.ssh(f'chmod {mode} {path}')


def upload(source, destination):
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w:gz') as tar:
        for file in Path(source).iterdir():
            tar.add(file, arcname=file.name)
    lab.ssh(f'mkdir -p {destination} && tar -xzf - -C {destination}', input=archive.getvalue())


def prepare(edition):
    lab.wait_ssh()
    # Regenerate the base before extraction. Never make the scene its own input.
    lab.ssh('sudo rm -f /etc/grub.d/99_bourgeois')
    put_text('/tmp/41_windows_fixture', '''#!/bin/sh
cat <<'EOF'
menuentry 'Windows routing fixture' --id bourgeois-windows-fixture {
  serial --unit=0 --speed=115200
  terminal_output --append serial
  echo BOURGEOIS_WINDOWS_FIXTURE
  terminal_output --remove serial
  terminal_output gfxterm
  sleep 3
}
EOF
''', '755')
    lab.ssh('sudo cp /tmp/41_windows_fixture /etc/grub.d/41_windows_fixture && sudo update-grub')
    source = lab.ssh('sudo cat /boot/grub/grub.cfg', capture_output=True, text=True).stdout
    STAGE.mkdir(parents=True, exist_ok=True)
    (lab.BUILD / 'base.cfg').write_text(source)
    candidates = [entry_id(b) for b in blocks(source) if b.kind == 'menuentry'
                  and entry_id(b) and entry_id(b).startswith('gnulinux-simple-')]
    if len(candidates) != 1:
        raise RuntimeError('Expected exactly one Ubuntu Linux entry')
    linux = candidates[0]
    windows = 'bourgeois-windows-fixture'
    (STAGE / 'scene.cfg').write_text(generate(source, linux, windows))
    for name, modified in (
        ('recordfail', 'set recordfail=1\n' + hook('fancy', linux, windows)),
        ('one-shot', f'set boot_once=true\nset default={windows}\nset timeout=0\n' + hook('fancy', linux, windows)),
        ('missing-asset', hook('fancy', linux, windows).replace('courtyard-nameplates.png', 'missing.png')),
        ('missing-module', 'set feature_bourgeois=0\n' + hook('fancy', linux, windows).replace('insmod bourgeois', 'insmod no_such_module')),
        ('missing-id', hook('fancy', 'missing-linux-id', windows)),
        ('1024x768', hook('fancy', linux, windows).replace('  insmod bourgeois', '  set bourgeois_gfxmode=1024x768\n  insmod bourgeois')),
        ('800x600', hook('fancy', linux, windows).replace('  insmod bourgeois', '  set bourgeois_gfxmode=800x600\n  insmod bourgeois')),
        ('unsupported-mode', hook('fancy', linux, windows).replace('  insmod bourgeois', '  set bourgeois_gfxmode=640x480\n  insmod bourgeois')),
    ):
        (STAGE / f'test-{name}.cfg').write_text(source + modified)
    theme.build(STAGE)
    for asset in ('courtyard.png', 'courtyard-nameplates.png', 'traveler.png'):
        shutil.copyfile(lab.ROOT / 'assets' / asset, STAGE / asset)
    upload(STAGE, '/home/bourgeois/preview')
    lab.ssh('sudo grub-script-check /home/bourgeois/preview/scene.cfg && sudo mkdir -p /boot/grub/bourgeois && sudo cp /home/bourgeois/preview/* /boot/grub/bourgeois/')
    library = lab.BUILD / 'hook-library'
    library.mkdir(parents=True, exist_ok=True)
    for name in ('grub_config.py', 'refresh.py'):
        shutil.copyfile(lab.ROOT / 'tools' / name, library / name)
    upload(library, '/home/bourgeois/hook-library')
    settings = {'edition': edition, 'linux_id': linux, 'windows_id': windows}
    put_text('/tmp/bourgeois.json', json.dumps(settings))
    put_text('/tmp/99_bourgeois', '#!/bin/sh\nexec python3 /usr/local/lib/bourgeois/refresh.py\n', '755')
    lab.ssh('sudo mkdir -p /usr/local/lib/bourgeois && sudo cp /home/bourgeois/hook-library/* /usr/local/lib/bourgeois/ && sudo cp /tmp/bourgeois.json /etc/bourgeois.json && sudo cp /tmp/99_bourgeois /etc/grub.d/99_bourgeois && sudo update-grub && sudo grub-script-check /boot/grub/grub.cfg')
    (lab.BUILD / 'preview.json').write_text(json.dumps({'edition': edition, 'linux_id': linux, 'windows_id': windows}, indent=2) + '\n')
    if edition == 'slim':
        from native import select_boot
        select_boot('slim')
    lab.ssh('sync')
    print(f'{edition} preview ready. Reset the VM to enter GRUB.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('edition', choices=['slim', 'fancy'])
    prepare(parser.parse_args().edition)
