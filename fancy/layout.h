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

#endif
