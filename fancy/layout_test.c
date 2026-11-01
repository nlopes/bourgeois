/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <assert.h>
#include "layout.h"

int
main (void)
{
  unsigned modes[][2] = {{800, 600}, {1024, 768}, {1280, 720},
                         {1920, 1080}, {2560, 1440}, {3840, 2160},
                         {7680, 4320}, {800, 4320}};
  unsigned i;
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
    }
  return 0;
}
