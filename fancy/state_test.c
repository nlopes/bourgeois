/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <assert.h>
#include "state.h"

int main (void)
{
  struct scene_state s;
  scene_init (&s, 100);
  assert (scene_step (&s, 30099, SCENE_NONE) == SCENE_WAIT);
  assert (scene_step (&s, 30100, SCENE_NONE) == SCENE_BOOT_LINUX);
  scene_init (&s, 0);
  assert (scene_step (&s, 30000, SCENE_OTHER) == SCENE_WAIT);
  assert (scene_step (&s, 60000, SCENE_NONE) == SCENE_WAIT);
  scene_init (&s, 0);
  assert (scene_step (&s, 0, SCENE_SPACE) == SCENE_WAIT);
  scene_step (&s, 0, SCENE_RIGHT);
  assert (scene_step (&s, 1199, SCENE_SPACE) == SCENE_WAIT);
  assert (scene_step (&s, 1200, SCENE_SPACE) == SCENE_BOOT_WINDOWS);
  scene_init (&s, 0);
  scene_step (&s, 0, SCENE_LEFT);
  scene_step (&s, 600, SCENE_RIGHT);
  assert (s.x == 840);
  scene_step (&s, 1200, SCENE_NONE);
  assert (s.x == 1200);
  assert (scene_step (&s, 2400, SCENE_SPACE) == SCENE_BOOT_WINDOWS);
  assert (scene_step (&s, 2400, SCENE_ESCAPE) == SCENE_TECHNICAL);
  scene_init (&s, 0);
  assert (scene_step (&s, 1, SCENE_WINDOWS) == SCENE_BOOT_WINDOWS);
  assert (scene_step (&s, 1, SCENE_LINUX) == SCENE_BOOT_LINUX);
  scene_step (&s, 1, SCENE_LEFT);
  assert (scene_step (&s, 100000, SCENE_SPACE) == SCENE_BOOT_LINUX);
  return 0;
}
