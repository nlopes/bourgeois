/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef BOURGEOIS_LAYOUT_H
#define BOURGEOIS_LAYOUT_H

/* Keep the original composition while making UI details readable at high DPI.
   Constrain by width as well, so narrow modes retain room for the controls. */
static unsigned
scene_ui_scale (unsigned width, unsigned height)
{
  unsigned scale = height / 720;
  if (scale > width / 800)
    scale = width / 800;
  if (scale < 1)
    scale = 1;
  if (scale > 6)
    scale = 6;
  return scale;
}

static unsigned
scene_star_light (unsigned long long now, unsigned star)
{
  unsigned period = 2200 + star * 173;
  unsigned phase = (now % period + star * 337) % period;
  unsigned half = period / 2;
  return phase <= half ? phase * 255 / half : (period - phase) * 255 / (period - half);
}

enum { SCENE_COMET_WIDTH = 96, SCENE_COMET_HEIGHT = 24,
       SCENE_COMET_HEAD_X = 86, SCENE_COMET_HEAD_Y = 15 };

struct scene_comet
{
  unsigned x, y, opacity;
};

/* Scene-relative time keeps the first pass predictable even after firmware
   delays. The flight stays below the title and above the courtyard gates. */
static struct scene_comet
scene_comet_frame (unsigned long long elapsed)
{
  struct scene_comet frame = { 0, 0, 0 };
  unsigned phase = elapsed % 18000, flight, fade;
  if (phase < 4000 || phase >= 8500)
    return frame;
  flight = phase - 4000;
  fade = flight < 4500 - flight ? flight : 4500 - flight;
  frame.x = 440 + flight * 700 / 4500;
  frame.y = 142 + flight * 50 / 4500;
  frame.opacity = fade < 500 ? fade * 255 / 500 : 255;
  return frame;
}

struct scene_comet_color
{
  unsigned char red, green, blue, alpha;
};

static struct scene_comet_color
scene_comet_pixel (unsigned x, unsigned y, unsigned opacity)
{
  struct scene_comet_color color = { 158, 200, 250, 0 };
  int dx = (int) x - SCENE_COMET_HEAD_X, dy = (int) y - SCENE_COMET_HEAD_Y;
  unsigned radius = dx * dx + dy * dy;
  if (radius < 25)
    {
      color.alpha = radius <= 2 ? 255 : (25 - radius) * 7;
      if (radius <= 2)
        {
          color.red = 255;
          color.green = 249;
          color.blue = 225;
        }
    }
  else if (x < SCENE_COMET_HEAD_X)
    {
      int center = 4 + x * 11 / SCENE_COMET_HEAD_X;
      unsigned distance = y > (unsigned) center ? y - center : center - y;
      unsigned spread = 1 + x / 22;
      if (distance < spread)
        color.alpha = 160 * x * x / (SCENE_COMET_HEAD_X * SCENE_COMET_HEAD_X)
          * (spread - distance) / spread;
    }
  color.alpha = color.alpha * opacity / 255;
  return color;
}

#endif
