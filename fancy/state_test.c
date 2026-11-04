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
  assert (scene_step (&s, 1249, SCENE_SPACE) == SCENE_WAIT);
  assert (scene_gate_frame (&s, 1249) == 2);
  assert (scene_gate_frame (&s, 1369) == 3);
  assert (scene_step (&s, 1488, SCENE_SPACE) == SCENE_WAIT);
  assert (scene_step (&s, 1489, SCENE_NONE) == SCENE_BOOT_WINDOWS);
  scene_init (&s, 0);
  scene_step (&s, 0, SCENE_LEFT);
  scene_step (&s, 600, SCENE_RIGHT);
  assert (s.x == 840);
  scene_step (&s, 1200, SCENE_NONE);
  assert (s.x == 1200);
  assert (scene_step (&s, 2400, SCENE_SPACE) == SCENE_WAIT);
  assert (scene_step (&s, 2449, SCENE_SPACE) == SCENE_WAIT);
  assert (scene_step (&s, 2449, SCENE_ESCAPE) == SCENE_TECHNICAL);
  scene_init (&s, 0);
  assert (scene_step (&s, 1, SCENE_WINDOWS) == SCENE_BOOT_WINDOWS);
  assert (scene_step (&s, 1, SCENE_LINUX) == SCENE_BOOT_LINUX);
  scene_step (&s, 1, SCENE_LEFT);
  assert (scene_step (&s, 1222, SCENE_SPACE) == SCENE_WAIT);
  assert (scene_step (&s, 1223, SCENE_SPACE) == SCENE_WAIT);
  assert (scene_step (&s, 100000, SCENE_SPACE) == SCENE_BOOT_LINUX);
  /* Repeating the same arrow at a gate must not turn the standing traveler
     away from that gate or restart movement. */
  scene_init (&s, 0);
  assert (!s.facing_left);
  scene_step (&s, 0, SCENE_LEFT);
  scene_step (&s, 2000, SCENE_NONE);
  assert (s.x == SCENE_LINUX_GATE_X && s.facing_left);
  assert (scene_gate_frame (&s, 2000) == 1);
  scene_step (&s, 2001, SCENE_LEFT);
  scene_step (&s, 2002, SCENE_OTHER);
  assert (s.x == SCENE_LINUX_GATE_X && s.facing_left);
  scene_step (&s, 2003, SCENE_RIGHT);
  assert (!s.facing_left);
  scene_step (&s, 5000, SCENE_NONE);
  assert (s.x == SCENE_WINDOWS_GATE_X && !s.facing_left);
  assert (scene_gate_frame (&s, 5000) == 0);
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
  scene_step (&s, 1224, SCENE_SPACE);
  assert (scene_step (&s, 1225, SCENE_RIGHT) == SCENE_WAIT);
  assert (s.entering == SCENE_WAIT);
  scene_init (&s, 0);
  assert (scene_gate_frame (&s, 0) == -1);
  assert (scene_doorway_frame (&s, 0) == -1);
  scene_step (&s, 0, SCENE_LEFT);
  scene_step (&s, 1221, SCENE_NONE);
  assert (scene_doorway_frame (&s, 1221) == -1);
  scene_step (&s, 1222, SCENE_NONE);
  assert (scene_doorway_frame (&s, 1222) == 0);
  assert (scene_doorway_frame (&s, 1302) == 1);
  assert (scene_doorway_frame (&s, 1382) == 2);
  assert (scene_doorway_frame (&s, 1462) == 3);
  scene_step (&s, 1463, SCENE_LEFT);
  assert (scene_doorway_frame (&s, 1463) == 3);
  scene_step (&s, 1464, SCENE_SPACE);
  assert (scene_doorway_frame (&s, 1464) == 4);
  assert (scene_doorway_frame (&s, 1524) == 5);
  assert (scene_doorway_frame (&s, 1584) == 6);
  assert (scene_doorway_frame (&s, 1644) == 7);
  scene_step (&s, 1650, SCENE_RIGHT);
  assert (scene_doorway_frame (&s, 1650) == -1);
  return 0;
}
