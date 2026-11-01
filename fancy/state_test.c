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
  assert (scene_step (&s, 1200, SCENE_SPACE) == SCENE_WAIT);
  assert (scene_step (&s, 1248, SCENE_SPACE) == SCENE_WAIT);
  assert (scene_step (&s, 1249, SCENE_SPACE) == SCENE_BOOT_WINDOWS);
  scene_init (&s, 0);
  scene_step (&s, 0, SCENE_LEFT);
  scene_step (&s, 600, SCENE_RIGHT);
  assert (s.x == 840);
  scene_step (&s, 1200, SCENE_NONE);
  assert (s.x == 1200);
  assert (scene_step (&s, 2400, SCENE_SPACE) == SCENE_WAIT);
  assert (scene_step (&s, 2449, SCENE_SPACE) == SCENE_BOOT_WINDOWS);
  assert (scene_step (&s, 2449, SCENE_ESCAPE) == SCENE_TECHNICAL);
  scene_init (&s, 0);
  assert (scene_step (&s, 1, SCENE_WINDOWS) == SCENE_BOOT_WINDOWS);
  assert (scene_step (&s, 1, SCENE_LINUX) == SCENE_BOOT_LINUX);
  scene_step (&s, 1, SCENE_LEFT);
  assert (scene_step (&s, 1222, SCENE_SPACE) == SCENE_WAIT);
  assert (scene_step (&s, 1223, SCENE_SPACE) == SCENE_BOOT_LINUX);
  assert (scene_step (&s, 100000, SCENE_SPACE) == SCENE_BOOT_LINUX);
  /* Repeating the same arrow at a gate must not turn the standing traveler
     away from that gate or restart movement. */
  scene_init (&s, 0);
  assert (!s.facing_left);
  scene_step (&s, 0, SCENE_LEFT);
  scene_step (&s, 2000, SCENE_NONE);
  assert (s.x == SCENE_LINUX_GATE_X && s.facing_left);
  scene_step (&s, 2001, SCENE_LEFT);
  scene_step (&s, 2002, SCENE_OTHER);
  assert (s.x == SCENE_LINUX_GATE_X && s.facing_left);
  scene_step (&s, 2003, SCENE_RIGHT);
  assert (!s.facing_left);
  scene_step (&s, 5000, SCENE_NONE);
  assert (s.x == SCENE_WINDOWS_GATE_X && !s.facing_left);
  scene_step (&s, 5001, SCENE_RIGHT);
  assert (!s.facing_left);
  scene_step (&s, 5002, SCENE_LEFT);
  assert (s.facing_left);
  /* Cancellation is permanent for this scene visit, including after repeats. */
  assert (scene_step (&s, 100000, SCENE_NONE) == SCENE_WAIT);
  scene_init (&s, 0);
  scene_step (&s, 0, SCENE_LEFT);
  {
    int now;
    for (now = 33; now < 1223; now += 33)
      scene_step (&s, now, SCENE_LEFT);
  }
  assert (s.move_started == 0);
  assert (scene_step (&s, 1223, SCENE_NONE) == SCENE_WAIT);
  assert (s.x == SCENE_LINUX_GATE_X && s.facing_left);
  return 0;
}
