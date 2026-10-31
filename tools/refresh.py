"""Ubuntu 24.04 grub-mkconfig hook. Run after the normal entries are emitted."""
import json
from pathlib import Path
import subprocess
import sys

from grub_config import generate, hook


def refresh(settings, source_path, target):
    source = Path(source_path).read_text()
    target = Path(target)
    scene = generate(source, settings['linux_id'], settings['windows_id'])
    temporary = target.with_suffix('.cfg.new')
    temporary.write_text(scene)
    try:
        subprocess.run(['grub-script-check', str(temporary)], check=True, capture_output=True)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return hook(settings['edition'], settings['linux_id'], settings['windows_id'])


def main():
    try:
        settings = json.loads(Path('/etc/bourgeois.json').read_text())
        print(refresh(settings, '/boot/grub/grub.cfg.new', '/boot/grub/bourgeois/scene.cfg'))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'bourgeois: refresh failed; keeping the technical menu: {error}', file=sys.stderr)
        print('set timeout=-1\nset timeout_style=menu')


if __name__ == '__main__':
    main()
