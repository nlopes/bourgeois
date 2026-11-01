"""Stage Slim artwork for an existing two-entry menu; never install host files.

Requires Pillow. Build for the resolution actually used by GRUB, for example:
    python3 tools/host_theme.py build/host-theme-review --size 1280x720
"""
import argparse
from pathlib import Path
import shutil

import theme

ROOT = Path(__file__).resolve().parent.parent


BACKGROUND_HOOK = '''#!/bin/sh
# Runs after Ubuntu initializes gfxterm, before any menu is shown.
cat <<'EOF'
if [ -f $prefix/themes/bourgeois/courtyard-nameplates.png ]; then
  insmod gfxterm_background
  background_image --mode=stretch $prefix/themes/bourgeois/courtyard-nameplates.png
fi
EOF
'''


def stage(target, width=1280, height=720):
    if not (800 <= width <= 7680 and 600 <= height <= 4320):
        raise ValueError('Choose a GRUB resolution between 800x600 and 7680x4320')
    from PIL import Image, ImageOps

    target = Path(target)
    # The text lists share these class icons. A 1-pixel size avoids GRUB trying
    # to scale a found icon to zero dimensions; transparent padding hides it.
    theme.build(target, icon_size=1, hotkeys=False)
    shutil.copyfile(ROOT / 'assets/courtyard-nameplates.png',
                    target / 'courtyard-nameplates.png')
    icons = target / 'icons'
    icons.mkdir(exist_ok=True)
    hero_height = height // 7
    with Image.open(ROOT / 'assets/traveler.png') as sheet:
        # The first of four logical cells is the existing standing pose.
        actor = sheet.crop((0, 0, sheet.width // 4, sheet.height))
        actor = actor.crop(actor.getbbox())
        actor = actor.resize((round(actor.width * hero_height / actor.height),
                              hero_height), Image.Resampling.NEAREST)
        for classes, center, face_left in (
                (('ubuntu', 'gnu-linux', 'linux'), 326 / 1672, True),
                (('windows',), 1358 / 1672, False)):
            sprite = ImageOps.mirror(actor) if face_left else actor
            canvas = Image.new('RGBA', (width, hero_height))
            canvas.paste(sprite, (round(center * width) - sprite.width // 2, 0))
            for name in classes:
                canvas.save(icons / f'{name}.png')

    # GRUB invalidates nested-list bounds as screen coordinates. A transparent
    # full-screen list makes it repaint the courtyard and the nested hero view
    # on every selection change, erasing the old hero as it draws the new one.
    views = f'''
+ boot_menu {{ left = 0 top = 0 width = 100% height = 100%
  item_height = 1 item_spacing = 0 item_padding = 0
  icon_width = 1 icon_height = 1 item_icon_space = 0
  item_color = "#00000000" selected_item_color = "#00000000"
  scrollbar = false scrollbar_left_pad = 0 scrollbar_right_pad = 0
}}
# The clipped one-row view scrolls to the selected entry's class icon.
+ canvas {{ left = 0 top = 73%-{hero_height} width = 100% height = {hero_height}
  + boot_menu {{ left = 0 top = 0 width = 100% height = 100%
    item_height = {hero_height} item_spacing = 0 item_padding = 0
    icon_width = {width} icon_height = {hero_height} item_icon_space = 0
    item_color = "#00000000" selected_item_color = "#00000000"
    scrollbar = false scrollbar_left_pad = 0 scrollbar_right_pad = 0
  }}
}}
'''
    file = target / 'theme.txt'
    file.write_text(file.read_text() + views)
    (target / '06_bourgeois_background').write_text(BACKGROUND_HOOK)
    (target / 'preview.cfg').write_text(f'''# Temporary preview for the existing host menu. No persistent state writes.
set gfxmode={width}x{height}
terminal_output console
terminal_output gfxterm
insmod gfxterm_background
background_image --mode=stretch $prefix/themes/bourgeois/courtyard-nameplates.png
set theme=$prefix/themes/bourgeois/theme.txt
export theme
source $prefix/clean-menu.cfg
''')


def resolution(value):
    try:
        width, height = map(int, value.split('x'))
    except ValueError as error:
        raise argparse.ArgumentTypeError('Use WIDTHxHEIGHT, such as 1280x720') from error
    return width, height


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--size', type=resolution, default=(1280, 720))
    args = parser.parse_args()
    stage(args.output, *args.size)
    print(f'Staged {args.size[0]}x{args.size[1]} artwork in {args.output}; host boot files unchanged.')
