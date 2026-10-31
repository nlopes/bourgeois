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
    png(target / 'panel.png', 1, 1, lambda x, y: (22, 30, 39, 245))
    png(target / 'tick.png', 3, 3, lambda x, y: gold)
    png(target / 'selected_c.png', 8, 8, lambda x, y: (53, 69, 44, 240))
    (target / 'theme.txt').write_text('''# bourgeois slim: all interaction belongs to stock GRUB.
title-text: ""
desktop-image: "courtyard.png"
desktop-image-scale-method: "stretch"
terminal-font: "Unifont Regular 16"
+ label { left = 25% top = 5% width = 50% height = 30 text = "CHOOSE YOUR KINGDOM" align = center color = "#f4dfb5" }
+ label { left = 12% top = 29% width = 16% height = 26 text = "LINUX  [L]" align = center color = "#f4dfb5" }
+ label { left = 72% top = 29% width = 16% height = 26 text = "WINDOWS  [W]" align = center color = "#f4dfb5" }
+ circular_progress { id = "__timeout__" left = 88% top = 5% width = 76 height = 90 center_bitmap = "hourglass.png" tick_bitmap = "tick.png" num_ticks = 30 ticks_disappear = true start_angle = -90 }
+ label { id = "__timeout__" left = 86% top = 19% width = 10% height = 24 align = center color = "#f4dfb5" }
+ boot_menu { left = 40% top = 78% width = 20% height = 76 item_height = 30 item_spacing = 4 item_padding = 10 item_color = "#d4c7b2" selected_item_color = "#ffe1a1" selected_item_pixmap_style = "selected_*.png" item_font = "Unifont Regular 16" icon_width = 0 icon_height = 0 scrollbar = false }
+ label { left = 10% top = 92% width = 80% height = 24 text = "Up/Down: choose   Enter: boot   L/W: boot now   Esc: technical menu" align = center color = "#f4dfb5" }
+ label { left = 30% top = 13% width = 40% height = 24 text = "Default: Linux  |  Any key cancels auto-boot" align = center color = "#d4c7b2" }
# Canvas paints the last declared components first.
+ image { left = 32% top = 3% width = 36% height = 7% file = "panel.png" }
+ image { left = 38% top = 77% width = 24% height = 13% file = "panel.png" }
+ image { left = 8% top = 91% width = 84% height = 6% file = "panel.png" }
+ image { left = 12% top = 28% width = 16% height = 5% file = "panel.png" }
+ image { left = 72% top = 28% width = 16% height = 5% file = "panel.png" }
''')
