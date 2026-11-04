/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <assert.h>
#include "layout.h"

static void
comet_timing (void)
{
  struct scene_comet first = scene_comet_frame (4500);
  struct scene_comet middle = scene_comet_frame (6250);
  struct scene_comet last = scene_comet_frame (8000);
  struct scene_comet repeat = scene_comet_frame (22500);
  assert (!scene_comet_frame (0).opacity);
  assert (!scene_comet_frame (3999).opacity);
  assert (!scene_comet_frame (4000).opacity);
  assert (!scene_comet_frame (8500).opacity);
  assert (!scene_comet_frame (17999).opacity);
  assert (first.opacity == 255 && middle.opacity == 255 && last.opacity == 255);
  assert (first.x < middle.x && middle.x < last.x);
  assert (first.y < middle.y && middle.y < last.y);
  assert (scene_comet_frame (4100).opacity < first.opacity);
  assert (scene_comet_frame (8400).opacity < last.opacity);
  assert (repeat.x == first.x && repeat.y == first.y && repeat.opacity == first.opacity);
  assert (scene_comet_frame (18000ULL * 1000000000 + 6250).x == middle.x);
}

static void
comet_tail (void)
{
  struct scene_comet_color head = scene_comet_pixel (86, 15, 255);
  struct scene_comet_color near_tail = scene_comet_pixel (66, 12, 255);
  struct scene_comet_color far_tail = scene_comet_pixel (22, 6, 255);
  struct scene_comet_color faded = scene_comet_pixel (86, 15, 100);
  unsigned x, y;
  assert (head.alpha == 255 && head.red > head.blue);
  assert (head.alpha > near_tail.alpha && near_tail.alpha > far_tail.alpha);
  assert (far_tail.alpha > 0 && near_tail.blue > near_tail.red);
  assert (faded.alpha == 100);
  assert (!scene_comet_pixel (0, 0, 255).alpha);
  assert (!scene_comet_pixel (95, 23, 255).alpha);
  for (y = 0; y < SCENE_COMET_HEIGHT; y++)
    for (x = 0; x < SCENE_COMET_WIDTH; x++)
      assert (!scene_comet_pixel (x, y, 0).alpha);
}

int
main (void)
{
  unsigned modes[][2] = {{800, 600}, {1024, 768}, {1280, 720},
                         {1920, 1080}, {2560, 1440}, {3840, 2160},
                         {7680, 4320}, {800, 4320}};
  unsigned i;
  comet_timing ();
  comet_tail ();
  assert (scene_star_light (0, 0) == 0);
  assert (scene_star_light (1100, 0) == 255);
  assert (scene_star_light (2200, 0) == 0);
  assert (scene_star_light (0, 1) != scene_star_light (0, 0));
  for (i = 0; i < 10000; i++)
    assert (scene_star_light (i, 8) <= 255);
  assert (scene_ui_scale (800, 600) == 1);
  assert (scene_ui_scale (1280, 720) == 1);
  assert (scene_ui_scale (2560, 1440) == 2);
  assert (scene_ui_scale (3840, 2160) == 3);
  assert (scene_ui_scale (7680, 4320) == 6);
  assert (scene_ui_scale (800, 4320) == 1);
  assert (scene_ui_scale (16000, 9000) == 6);
  for (i = 0; i < sizeof modes / sizeof modes[0]; i++)
    {
      unsigned scale = scene_ui_scale (modes[i][0], modes[i][1]);
      /* Longest hint at a conservative 13-pixel monospace advance. */
      assert (36 * 13 * scale < modes[i][0]);
      /* The timer stays above the gates, with a margin at the right edge. */
      assert (140 * scale < modes[i][1] / 3);
      assert (66 * scale > 31 * scale);
      {
        unsigned w = modes[i][0], h = modes[i][1], ms;
        unsigned sprite_w = (w * SCENE_COMET_WIDTH + 836) / 1672;
        unsigned sprite_h = (h * SCENE_COMET_HEIGHT + 470) / 941;
        for (ms = 4001; ms < 8500; ms++)
          {
            struct scene_comet comet = scene_comet_frame (ms);
            unsigned left = comet.x * w / 1672 - SCENE_COMET_HEAD_X * sprite_w / SCENE_COMET_WIDTH;
            unsigned top = comet.y * h / 941 - SCENE_COMET_HEAD_Y * sprite_h / SCENE_COMET_HEIGHT;
            assert (left + sprite_w < w && top + sprite_h < h);
            assert (top > 80 * scale);
            assert (left + sprite_w < w - 96 * scale);
            assert (top + sprite_h < h / 4);
          }
      }
    }
  return 0;
}
