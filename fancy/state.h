/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef BOURGEOIS_STATE_H
#define BOURGEOIS_STATE_H

enum scene_key { SCENE_NONE, SCENE_LEFT, SCENE_RIGHT, SCENE_SPACE,
                 SCENE_LINUX, SCENE_WINDOWS, SCENE_ESCAPE, SCENE_OTHER };
enum scene_action { SCENE_WAIT, SCENE_BOOT_LINUX, SCENE_BOOT_WINDOWS,
                    SCENE_TECHNICAL };
/* Door centers in the 1672-pixel courtyard, shared by labels and walking. */
enum { SCENE_WIDTH = 2400,
       SCENE_LINUX_GATE_X = 326 * SCENE_WIDTH / 1672,
       SCENE_WINDOWS_GATE_X = 1358 * SCENE_WIDTH / 1672 };
struct scene_state
{
  unsigned long long started, move_started, enter_started;
  enum scene_action entering;
  int x, origin, target, facing_left, cancelled, remaining;
};

static void
scene_init (struct scene_state *s, unsigned long long now)
{
  s->started = s->move_started = now;
  s->x = s->origin = s->target = SCENE_WIDTH / 2;
  s->facing_left = 0;
  s->cancelled = 0;
  s->remaining = 30000;
  s->enter_started = now;
  s->entering = SCENE_WAIT;
}

static int
scene_gate_frame (const struct scene_state *s, unsigned long long now)
{
  if (s->entering != SCENE_WAIT)
    return now - s->enter_started < 120 ? 2 : 3;
  if (s->x == SCENE_LINUX_GATE_X)
    return 1;
  if (s->x == SCENE_WINDOWS_GATE_X)
    return 0;
  return -1;
}

/* Repeated arrows retain the original arrival time. Leaving a gate removes
   its light immediately, so the next frame cannot leave a lit trail. */
static int
scene_doorway_frame (const struct scene_state *s, unsigned long long now)
{
  unsigned long long elapsed, arrived;
  unsigned distance;
  if (s->x != s->target
      || (s->x != SCENE_LINUX_GATE_X && s->x != SCENE_WINDOWS_GATE_X))
    return -1;
  if (s->entering != SCENE_WAIT)
    {
      elapsed = now - s->enter_started;
      return 4 + (elapsed >= 180 ? 3 : (int) (elapsed / 60));
    }
  distance = s->target > s->origin ? s->target - s->origin : s->origin - s->target;
  arrived = s->move_started + (distance * 5 + 2) / 3;
  elapsed = now > arrived ? now - arrived : 0;
  return elapsed >= 240 ? 3 : (int) (elapsed / 80);
}

static enum scene_action
scene_step (struct scene_state *s, unsigned long long now, enum scene_key key)
{
  unsigned long long distance = (now - s->move_started) * 3 / 5;
  if (s->target < s->origin)
    s->x = distance >= (unsigned) (s->origin - s->target)
      ? s->target : s->origin - (int) distance;
  else
    s->x = distance >= (unsigned) (s->target - s->origin)
      ? s->target : s->origin + (int) distance;
  if (key != SCENE_NONE)
    s->cancelled = 1;
  if (!s->cancelled)
    {
      unsigned long long elapsed = now - s->started;
      s->remaining = elapsed >= 30000 ? 0 : 30000 - (int) elapsed;
      if (!s->remaining)
        return SCENE_BOOT_LINUX;
    }
  if (key == SCENE_ESCAPE)
    return SCENE_TECHNICAL;
  if (key == SCENE_LINUX)
    return SCENE_BOOT_LINUX;
  if (key == SCENE_WINDOWS)
    return SCENE_BOOT_WINDOWS;
  if (s->entering != SCENE_WAIT && key != SCENE_LEFT && key != SCENE_RIGHT)
    return now - s->enter_started >= 240 ? s->entering : SCENE_WAIT;
  if (key == SCENE_SPACE
      && (s->x == SCENE_LINUX_GATE_X || s->x == SCENE_WINDOWS_GATE_X))
    {
      s->entering = s->x == SCENE_LINUX_GATE_X ? SCENE_BOOT_LINUX : SCENE_BOOT_WINDOWS;
      s->enter_started = now;
      return SCENE_WAIT;
    }
  if (key == SCENE_LEFT || key == SCENE_RIGHT)
    {
      int target = key == SCENE_LEFT ? SCENE_LINUX_GATE_X : SCENE_WINDOWS_GATE_X;
      s->entering = SCENE_WAIT;
      /* Keep facing explicit: zero travel distance has no direction. */
      s->facing_left = key == SCENE_LEFT;
      /* Keyboard repeat must not restart interpolation or lose fractional
         travel distance. Reversal still starts at the current position. */
      if (target != s->target)
        {
          s->origin = s->x;
          s->target = target;
          s->move_started = now;
        }
    }
  return SCENE_WAIT;
}
#endif
