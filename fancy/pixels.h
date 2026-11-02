/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef BOURGEOIS_PIXELS_H
#define BOURGEOIS_PIXELS_H
#include <stddef.h>

struct scene_pixels
{
  unsigned char *data;
  unsigned width, height, pitch, channels;
};

/* PNG assets use RGB or RGBA byte order. Clip destinations before forming
   offsets, including on tall displays where a gate sprite can cross an edge. */
static int
scene_stamp (struct scene_pixels *dst, const struct scene_pixels *src,
             unsigned source_x, int x, int y, unsigned width, unsigned height)
{
  unsigned row, col;
  if (!dst->data || !src->data
      || (dst->channels != 3 && dst->channels != 4)
      || (src->channels != 3 && src->channels != 4)
      || (size_t) dst->width * dst->channels > dst->pitch
      || (size_t) src->width * src->channels > src->pitch
      || source_x > src->width || width > src->width - source_x
      || height > src->height)
    return 0;
  for (row = 0; row < height; row++)
    for (col = 0; col < width; col++)
      {
        long long dx = (long long) x + col, dy = (long long) y + row;
        unsigned char *d;
        const unsigned char *s;
        unsigned a, da, alpha, channel;
        if (dx < 0 || dy < 0 || dx >= dst->width || dy >= dst->height)
          continue;
        d = dst->data + (size_t) dy * dst->pitch + (size_t) dx * dst->channels;
        s = src->data + (size_t) row * src->pitch + (size_t) (source_x + col) * src->channels;
        a = src->channels == 4 ? s[3] : 255;
        da = dst->channels == 4 ? d[3] : 255;
        alpha = a * 255 + da * (255 - a);
        if (alpha)
          for (channel = 0; channel < 3; channel++)
            d[channel] = (s[channel] * a * 255 + d[channel] * da * (255 - a)
                          + alpha / 2) / alpha;
        if (dst->channels == 4)
          d[3] = (alpha + 127) / 255;
      }
  return 1;
}
#endif
