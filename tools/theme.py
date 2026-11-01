"""Build the slim theme and small deterministic UI bitmaps."""
import struct
import zlib
from pathlib import Path

BOX_SLICES = ('nw', 'n', 'ne', 'w', 'c', 'e', 'sw', 's', 'se')
MENU_ASSETS = tuple(f'{style}_{part}.png'
                    for style in ('panel', 'item', 'selected') for part in BOX_SLICES)


def png(path, width, height, pixel):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    data = b''.join(b'\0' + bytes(sum((list(pixel(x, y)) for x in range(width)), [])) for y in range(height))
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
                           + chunk(b'IDAT', zlib.compress(data)) + chunk(b'IEND', b''))


def styled_box(target, name, fill, border, scale, side=2, top=2):
    """Generate native nine-slice frames with clipped corners and a fine rim."""
    width, height = side * 2 + 8, top * 2 + 8

    def pixel(x, y):
        corner = min(x + y, width - 1 - x + y,
                     x + height - 1 - y, width + height - 2 - x - y)
        edge = min(x, y, width - 1 - x, height - 1 - y)
        if corner < 2:
            return (0, 0, 0, 0)
        if edge == 0 or corner == 2:
            return border
        if edge == 1:
            return tuple(int(value * 0.55) for value in border[:3]) + (255,)
        return fill

    columns = ((0, side), (side, 8), (side + 8, side))
    rows = ((0, top), (top, 8), (top + 8, top))
    for part, (row, column) in zip(BOX_SLICES,
                                  ((0, 0), (0, 1), (0, 2), (1, 0), (1, 1),
                                   (1, 2), (2, 0), (2, 1), (2, 2))):
        left, w = columns[column]
        upper, h = rows[row]
        png(target / f'{name}_{part}.png', w * scale, h * scale,
            lambda x, y: pixel(left + x // scale, upper + y // scale))


def build(target, *, icon_size=0, hotkeys=True, scale=1,
          menu_font='Unifont Regular 16', menu_text_width=56):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    def bitmap(name, width, height, pixel):
        png(target / name, width * scale, height * scale,
            lambda x, y: pixel(x // scale, y // scale))
    gold = (232, 185, 103, 255)
    def glass(x, y):
        if 8 <= x < 40 and (5 <= y < 10 or 54 <= y < 59):
            return gold
        if 10 <= y < 54:
            half = abs(y - 32) * 14 // 22 + 2
            if abs(x - 24) == half:
                return (164, 196, 204, 255)
            if (13 <= y <= 30 and abs(x - 24) < half - 2) or (48 <= y < 52 and abs(x - 24) < half - 2):
                return gold
        return (0, 0, 0, 0)
    bitmap('hourglass.png', 48, 64, glass)
    bitmap('tick.png', 3, 3, lambda x, y: gold)
    transparent = (0, 0, 0, 0)
    def ornament(x, y):
        dx, dy = abs(x - 8), abs(y - 8)
        if dx + dy in (3, 7) or (min(dx, dy) == 0 and max(dx, dy) <= 7):
            return gold
        return transparent
    bitmap('ornament.png', 17, 17, ornament)
    def menu_ornament(x, y):
        dx, dy = abs(x - 4), abs(y - 4)
        return gold if dx + dy in (2, 4) else transparent
    bitmap('menu-ornament.png', 9, 9, menu_ornament)
    png(target / 'footer.png', 1, 1, lambda x, y: (8, 16, 26, 245))
    frame_side, frame_top = 12, 4
    item_padding, item_height, item_spacing = 2, 26, 6
    row_rim, text_padding = 2, 2
    styled_box(target, 'panel', (9, 18, 29, 250), (211, 161, 75, 255), scale,
               side=frame_side, top=frame_top)
    styled_box(target, 'item', (13, 23, 35, 255), (97, 116, 132, 255), scale)
    styled_box(target, 'selected', (246, 186, 76, 255), (255, 226, 159, 255), scale)

    def label(left, top, width, height, text, color, identifier=None):
        attributes = f'id = "{identifier}" ' if identifier else ''
        if text is not None:
            attributes += f'text = "{text}" '
        # Canvas paints in reverse declaration order. Shadows follow the face.
        return ''.join(
            f'+ label {{ left = {left}{dx * scale:+d} top = {top}{dy * scale:+d} width = {width} height = {height * scale} '
            f'{attributes}font = "{menu_font}" align = center color = "{ink}" }}\n'
            for dx, dy, ink in [(0, 0, color), (-1, -1, '#181316'),
                                (-1, 1, '#181316'), (1, -1, '#181316'), (1, 1, '#181316')])

    output = '''# bourgeois slim: all interaction belongs to stock GRUB.
title-text: ""
desktop-image: "courtyard-nameplates.png"
desktop-image-scale-method: "stretch"
terminal-font: "Unifont Regular 16"
# GRUB clears this terminal before executing a menu entry. Use the whole display
# so the handoff does not leave a black rectangle over the courtyard.
terminal-left: "0"
terminal-top: "0"
terminal-width: "100%"
terminal-height: "100%"
terminal-border: "0"
'''
    output += label('25%', '5%', '50%', 30, 'CHOOSE YOUR KINGDOM', '#f4dfb5')
    output += f'''
+ circular_progress {{ id = "__timeout__" left = 88% top = 5% width = {76 * scale} height = {90 * scale} center_bitmap = "hourglass.png" tick_bitmap = "tick.png" num_ticks = 30 ticks_disappear = true start_angle = -90 }}
'''
    output += label('86%', '19%', '10%', 24, None, '#f4dfb5', '__timeout__')
    # Fit the longest title plus the frame, row rim, and small text insets.
    # The base Unifont's seven ASCII cells are 56 pixels; host fonts are measured.
    panel_width = menu_text_width + 2 * (frame_side + item_padding + row_rim + text_padding) * scale + icon_size
    panel_width += panel_width % 2
    panel_height = (2 * (frame_top + item_padding + item_height + row_rim) + item_spacing) * scale
    ornament_size = 9 * scale
    for side in (-1, 1):
        left = side * (panel_width // 2 - frame_side * scale // 2) - ornament_size // 2
        output += (f'+ image {{ left = 50%{left:+d} top = 90%-{(panel_height + ornament_size) // 2} '
                   f'width = {ornament_size} height = {ornament_size} file = "menu-ornament.png" }}\n')
    # Clip the native list to two rows despite GRUB's three-row minimum size.
    output += f'''+ canvas {{ left = 50%-{panel_width // 2} top = 90%-{panel_height} width = {panel_width} height = {panel_height}
  + boot_menu {{ left = 0 top = 0 width = 100% height = 100%
    menu_pixmap_style = "panel_*.png" item_pixmap_style = "item_*.png"
    selected_item_pixmap_style = "selected_*.png"
    item_height = {item_height * scale} item_spacing = {item_spacing * scale} item_padding = {item_padding * scale}
    item_font = "{menu_font}" item_color = "#e6edf5" selected_item_color = "#17120d"
    icon_width = {icon_size} icon_height = {icon_size} item_icon_space = {text_padding * scale}
    scrollbar = false scrollbar_left_pad = 0 scrollbar_right_pad = 0
  }}
}}
'''
    controls = 'Up/Down: choose   Enter: boot   '
    if hotkeys:
        controls += 'L/W: boot now   '
    output += label('10%', '94%', '80%', 24,
                    controls + 'Esc: technical menu', '#f4dfb5')
    output += label('30%', '13%', '40%', 24,
                    'Default: Linux  |  Any key cancels auto-boot', '#d4c7b2')
    for left in ('2%', '98%'):
        output += (f'+ image {{ left = {left}-{8 * scale} top = 94%+{4 * scale} '
                   f'width = {17 * scale} height = {17 * scale} file = "ornament.png" }}\n')
    output += (f'+ image {{ left = 0 top = 93% width = 100% height = {2 * scale} file = "panel_n.png" }}\n'
               f'+ image {{ left = 0 top = 100%-{2 * scale} width = 100% height = {2 * scale} file = "panel_s.png" }}\n')
    output += '+ image { left = 0 top = 93% width = 100% height = 7% file = "footer.png" }\n'
    # Full-screen invalidation also refreshes the nested panel and hero view.
    output += '''+ boot_menu { left = 0 top = 0 width = 100% height = 100%
  item_height = 1 item_spacing = 0 item_padding = 0
  icon_width = 1 icon_height = 1 item_icon_space = 0
  item_color = "#00000000" selected_item_color = "#00000000"
  scrollbar = false scrollbar_left_pad = 0 scrollbar_right_pad = 0
}
'''
    (target / 'theme.txt').write_text(output)
