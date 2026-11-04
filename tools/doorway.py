"""Build a soft amber threshold light shared by Fancy and Slim."""
from functools import lru_cache
from pathlib import Path

WIDTH, HEIGHT, TOP = 320, 128, 580
FRAMES, IDLE = 8, 3


def geometry(width, height):
    return round(width * WIDTH / 1672), round(height * HEIGHT / 941), round(height * TOP / 941)


@lru_cache(maxsize=1)
def mask():
    limit = WIDTH * WIDTH * HEIGHT * HEIGHT
    result = bytearray()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            distance = (2 * x + 1 - WIDTH) ** 2 * HEIGHT ** 2
            distance += (2 * y + 1 - HEIGHT) ** 2 * WIDTH ** 2
            falloff = max(0, limit - distance)
            result.append(round(44 * falloff * falloff / (limit * limit)))
    return bytes(result)


def frame(index=IDLE):
    from PIL import Image

    if not 0 <= index < FRAMES:
        raise ValueError('Doorway frame must be between 0 and 7')
    image = Image.new('RGBA', (WIDTH, HEIGHT), (255, 177, 70, 0))
    image.putalpha(Image.frombytes('L', image.size,
                                  bytes(alpha * (index + 1) // 4 for alpha in mask())))
    return image


def atlas(target):
    from PIL import Image

    image = Image.new('RGBA', (WIDTH * FRAMES, HEIGHT))
    for index in range(FRAMES):
        image.paste(frame(index), (index * WIDTH, 0))
    image.save(Path(target) / 'doorway.png')
