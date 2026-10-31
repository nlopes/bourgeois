/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef BOURGEOIS_STATE_H
#define BOURGEOIS_STATE_H

enum scene_key { SCENE_NONE, SCENE_LEFT, SCENE_RIGHT, SCENE_SPACE,
                 SCENE_LINUX, SCENE_WINDOWS, SCENE_ESCAPE, SCENE_OTHER };
enum scene_action { SCENE_WAIT, SCENE_BOOT_LINUX, SCENE_BOOT_WINDOWS,
                    SCENE_TECHNICAL };
struct scene_state
{
  unsigned long long started, move_started;
  int x, origin, target, cancelled, remaining;
};

static void
scene_init (struct scene_state *s, unsigned long long now)
{
  s->started = s->move_started = now;
  s->x = s->origin = s->target = 1200;
  s->cancelled = 0;
  s->remaining = 30000;
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
  if (key == SCENE_LINUX || (key == SCENE_SPACE && s->x == 480))
    return SCENE_BOOT_LINUX;
  if (key == SCENE_WINDOWS || (key == SCENE_SPACE && s->x == 1920))
    return SCENE_BOOT_WINDOWS;
  if (key == SCENE_LEFT || key == SCENE_RIGHT)
    {
      s->origin = s->x;
      s->target = key == SCENE_LEFT ? 480 : 1920;
      s->move_started = now;
    }
  return SCENE_WAIT;
}
#endif
