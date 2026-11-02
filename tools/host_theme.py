"""Stage Slim artwork for an existing two-entry menu; never install host files.

Requires Pillow, grub-mkfont, and DejaVu Sans Mono. For example:
    python3 tools/host_theme.py build/host-theme-review --size 2560x1440
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

import theme
import hero
from host_checks import FONT, HostSetupError, require_tools

ROOT = Path(__file__).resolve().parent.parent
STAGED_FILES = (
    'theme.txt', 'preview.cfg', '06_bourgeois_background',
    'courtyard-nameplates.png', 'hourglass.png', 'tick.png',
    'ornament.png', 'menu-ornament.png', 'footer.png', 'menu.pf2', 'menu-font-license.txt',
    *theme.MENU_ASSETS,
    'icons/ubuntu.png', 'icons/gnu-linux.png', 'icons/linux.png', 'icons/windows.png',
)


BACKGROUND_HOOK = '''#!/bin/sh
# Runs after Ubuntu initializes gfxterm, before any menu is shown.
cat <<'EOF'
if [ -f $prefix/themes/bourgeois/courtyard-nameplates.png ]; then
  insmod gfxterm_background
  background_image --mode=stretch $prefix/themes/bourgeois/courtyard-nameplates.png
fi
EOF
'''


def stage(target, width=2560, height=1440):
    if not (800 <= width <= 7680 and 600 <= height <= 4320):
        raise ValueError('Choose a GRUB resolution between 800x600 and 7680x4320')
    require_tools('stage')
    from PIL import ImageFont

    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    scale = max(1, height // 720)
    font = target / 'menu.pf2'
    subprocess.run(['grub-mkfont', '--name=Bourgeois UI', f'--size={20 * scale}',
                    '--range=0x20-0x7e', f'--output={font}', str(FONT)], check=True,
                   capture_output=True)
    menu_font = f'Bourgeois UI Regular {20 * scale}'
    metrics = ImageFont.truetype(str(FONT), 20 * scale)
    menu_text_width = math.ceil(max(metrics.getlength(title) for title in ('Linux', 'Windows')))
    # The text lists share these class icons. A 1-pixel size avoids GRUB trying
    # to scale a found icon to zero dimensions; transparent padding hides it.
    theme.build(target, icon_size=1, hotkeys=False, scale=scale, menu_font=menu_font,
                menu_text_width=menu_text_width)
    shutil.copyfile(ROOT / 'assets/DejaVu-font-license.txt', target / 'menu-font-license.txt')
    shutil.copyfile(ROOT / 'assets/courtyard-nameplates.png',
                    target / 'courtyard-nameplates.png')
    hero.icons(target, width, height)
    file = target / 'theme.txt'
    file.write_text(file.read_text() + hero.view(width, height))
    (target / '06_bourgeois_background').write_text(BACKGROUND_HOOK)
    (target / 'preview.cfg').write_text(f'''# Temporary preview for the existing host menu. No persistent state writes.
set gfxmode={width}x{height}
terminal_output console
terminal_output gfxterm
loadfont $prefix/themes/bourgeois/menu.pf2
insmod gfxterm_background
background_image --mode=stretch $prefix/themes/bourgeois/courtyard-nameplates.png
set theme=$prefix/themes/bourgeois/theme.txt
export theme
source $prefix/clean-menu.cfg
''')
    manifest = {'format': 1, 'size': [width, height], 'files': {
        name: hashlib.sha256((target / name).read_bytes()).hexdigest()
        for name in STAGED_FILES}}
    (target / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


def resolution(value):
    try:
        width, height = map(int, value.split('x'))
    except ValueError as error:
        raise argparse.ArgumentTypeError('Use WIDTHxHEIGHT, such as 1280x720') from error
    return width, height


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--size', type=resolution, default=(2560, 1440))
    args = parser.parse_args()
    try:
        stage(args.output, *args.size)
    except (HostSetupError, ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'bourgeois: {error}', file=sys.stderr)
        sys.exit(1)
    print(f'Staged {args.size[0]}x{args.size[1]} artwork in {args.output}; host boot files unchanged.')
