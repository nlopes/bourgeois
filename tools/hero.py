"""Build Slim's selected-entry icons from the shared gate-facing poses."""
from pathlib import Path

import doorway

ROOT = Path(__file__).resolve().parent.parent
GATES = ((('ubuntu', 'gnu-linux', 'linux'), 326 / 1672, 1),
         (('windows',), 1358 / 1672, 0))


def icon_height(width, height):
    _, light_height, light_top = doorway.geometry(width, height)
    top = height * 73 // 100 - height // 7
    return max(height * 73 // 100, light_top + light_height) - top


def icons(target, width, height):
    from PIL import Image

    target = Path(target) / 'icons'
    target.mkdir(parents=True, exist_ok=True)
    hero_height = height // 7
    light_width, light_height, light_top = doorway.geometry(width, height)
    light = doorway.frame().resize((light_width, light_height), Image.Resampling.NEAREST)
    top = height * 73 // 100 - hero_height
    with Image.open(ROOT / 'assets/traveler-gates.png') as sheet:
        for classes, center, frame in GATES:
            cell = sheet.crop((frame * sheet.width // 4, 0,
                               (frame + 1) * sheet.width // 4, sheet.height))
            sprite = cell.resize((round(cell.width * hero_height / cell.height), hero_height),
                                 Image.Resampling.NEAREST)
            canvas = Image.new('RGBA', (width, icon_height(width, height)))
            canvas.paste(light, (round(center * width) - light_width // 2, light_top - top))
            canvas.alpha_composite(sprite, (round(center * width) - sprite.width // 2, 0))
            for name in classes:
                canvas.save(target / f'{name}.png')


def view(width, height):
    hero_height = height // 7
    row_height = icon_height(width, height)
    return f'''
# The clipped one-row view follows the selected entry's gate-facing class icon.
+ canvas {{ left = 0 top = 73%-{hero_height} width = 100% height = {row_height}
  + boot_menu {{ left = 0 top = 0 width = 100% height = 100%
    item_height = {row_height} item_spacing = 0 item_padding = 0
    icon_width = {width} icon_height = {row_height} item_icon_space = 0
    item_color = "#00000000" selected_item_color = "#00000000"
    scrollbar = false scrollbar_left_pad = 0 scrollbar_right_pad = 0
  }}
}}
'''
