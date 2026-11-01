"""Build the slim theme and small deterministic UI bitmaps."""
import struct
import zlib
from pathlib import Path


def png(path, width, height, pixel):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    data = b''.join(b'\0' + bytes(sum((list(pixel(x, y)) for x in range(width)), [])) for y in range(height))
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
                           + chunk(b'IDAT', zlib.compress(data)) + chunk(b'IEND', b''))


def build(target):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
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
    png(target / 'hourglass.png', 48, 64, glass)
    png(target / 'tick.png', 3, 3, lambda x, y: gold)
    transparent = (0, 0, 0, 0)
    def pointer(x, y):
        if 3 <= x <= 10 and abs(y - 14) <= 10 - x:
            return gold
        if 2 <= x <= 11 and abs(y - 14) <= 12 - x:
            return (24, 19, 22, 255)
        return transparent
    png(target / 'selected_w.png', 14, 30, pointer)
    png(target / 'selected_c.png', 1, 1, lambda x, y: transparent)
    png(target / 'shadow_w.png', 14, 30, lambda x, y: transparent)
    png(target / 'shadow_c.png', 1, 1, lambda x, y: transparent)

    def label(left, top, width, height, text, color, identifier=None):
        attributes = f'id = "{identifier}" ' if identifier else ''
        if text is not None:
            attributes += f'text = "{text}" '
        # Canvas paints in reverse declaration order. Shadows follow the face.
        return ''.join(
            f'+ label {{ left = {left}{dx:+d} top = {top}{dy:+d} width = {width} height = {height} '
            f'{attributes}align = center color = "{ink}" }}\n'
            for dx, dy, ink in [(0, 0, color), (-1, -1, '#181316'),
                                (-1, 1, '#181316'), (1, -1, '#181316'), (1, 1, '#181316')])

    def menu(offset, color, selected_color, pixmaps):
        return (f'+ boot_menu {{ left = 40%+{offset} top = 78%+{offset} width = 20% height = 76 '
                f'item_height = 30 item_spacing = 4 item_padding = 10 item_color = "{color}" '
                f'selected_item_color = "{selected_color}" selected_item_pixmap_style = "{pixmaps}_*.png" '
                'item_font = "Unifont Regular 16" icon_width = 0 icon_height = 0 scrollbar = false }\n')

    output = '''# bourgeois slim: all interaction belongs to stock GRUB.
title-text: ""
desktop-image: "courtyard-nameplates.png"
desktop-image-scale-method: "stretch"
terminal-font: "Unifont Regular 16"
'''
    output += label('25%', '5%', '50%', 30, 'CHOOSE YOUR KINGDOM', '#f4dfb5')
    output += '''
+ circular_progress { id = "__timeout__" left = 88% top = 5% width = 76 height = 90 center_bitmap = "hourglass.png" tick_bitmap = "tick.png" num_ticks = 30 ticks_disappear = true start_angle = -90 }
'''
    output += label('86%', '19%', '10%', 24, None, '#f4dfb5', '__timeout__')
    # Both lists show the same native menu; the rear list supplies text shadow.
    output += menu(0, '#f4dfb5', '#ffe1a1', 'selected')
    output += menu(1, '#181316', '#181316', 'shadow')
    output += label('10%', '92%', '80%', 24,
                    'Up/Down: choose   Enter: boot   L/W: boot now   Esc: technical menu', '#f4dfb5')
    output += label('30%', '13%', '40%', 24,
                    'Default: Linux  |  Any key cancels auto-boot', '#d4c7b2')
    (target / 'theme.txt').write_text(output)
