/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <assert.h>
#include <string.h>
#include "pixels.h"

int
main (void)
{
  unsigned char background[] = { 0, 0, 255, 255, 0, 0, 255, 255 };
  unsigned char sprite[] = { 255, 0, 0, 128, 0, 255, 0, 255 };
  struct scene_pixels dst = { background, 2, 1, 8, 4 };
  struct scene_pixels src = { sprite, 2, 1, 8, 4 };
  assert (scene_stamp (&dst, &src, 0, 0, 0, 2, 1));
  assert (background[0] == 128 && background[2] == 127 && background[3] == 255);
  assert (background[4] == 0 && background[5] == 255 && background[7] == 255);
  memset (background, 0, sizeof background);
  assert (scene_stamp (&dst, &src, 0, -1, 0, 2, 1));
  assert (background[1] == 255 && background[3] == 255 && background[7] == 0);
  assert (scene_stamp (&dst, &src, 1, 1, 0, 1, 1));
  assert (background[5] == 255 && background[7] == 255);
  assert (!scene_stamp (&dst, &src, 2, 0, 0, 1, 1));
  assert (!scene_stamp (&dst, &src, 0, 0, 0, 2, 2));
  dst.pitch = 1;
  assert (!scene_stamp (&dst, &src, 0, 0, 0, 1, 1));
  dst.pitch = 8;
  dst.channels = 3;
  assert (scene_stamp (&dst, &src, 0, 0, -1, 2, 1));
  return 0;
}
