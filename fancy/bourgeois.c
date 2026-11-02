/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (C) 2026 Norberto Lopes
 */
#include <grub/auth.h>
#include <grub/bitmap.h>
#include <grub/bitmap_scale.h>
#include <grub/command.h>
#include <grub/dl.h>
#include <grub/env.h>
#include <grub/font.h>
#include <grub/gfxterm.h>
#include <grub/gfxmenu_view.h>
#include <grub/menu.h>
#include <grub/misc.h>
#include <grub/normal.h>
#include <grub/term.h>
#include <grub/time.h>
#include <grub/video.h>
#include <grub/cpu/io.h>
#include "state.h"
#include "layout.h"

GRUB_MOD_LICENSE ("GPLv3+");
static grub_command_t command;
static unsigned width, height, ui_scale;
static grub_font_t font;

static void
trace (const char *message)
{
  const char *enabled = grub_env_get ("bourgeois_trace");
  if (enabled && grub_strcmp (enabled, "1") == 0)
    {
      while (*message)
        grub_outb (*message++, 0xe9);
      grub_outb ('\n', 0xe9);
    }
}

static void
rect (int x, int y, int w, int h, int r, int g, int b)
{
  grub_video_fill_rect (grub_video_map_rgb (r, g, b), x * ui_scale,
                        y * ui_scale, w * ui_scale, h * ui_scale);
}

static void
label (const char *text, int center, int y, int gold)
{
  int text_width = grub_font_get_string_width (font, text);
  int dx, dy;
  /* The scene remains visible behind the text. A dark outline keeps glyphs
     readable over both lit stone and foliage. */
  for (dy = -1; dy <= 1; dy += 2)
    for (dx = -1; dx <= 1; dx += 2)
      grub_font_draw_string (text, font, grub_video_map_rgb (24, 19, 22),
                             center - text_width / 2 + dx * (int) ui_scale,
                             y + dy * (int) ui_scale);
  grub_font_draw_string (text, font,
                        gold ? grub_video_map_rgb (250, 221, 165)
                             : grub_video_map_rgb (208, 215, 209),
                        center - text_width / 2, y);
}

static int
glass_half_width (int row)
{
  return 3 + 17 * (28 - row) * (28 - row) / (28 * 28);
}

static void
hourglass (struct scene_state *s, grub_uint64_t now)
{
  int x = width / ui_scale - 66, y = 32, row, side, total = 0, remaining, fallen;
  /* Draw the frame without a backing panel, so its open areas show the sky. */
  for (side = -1; side <= 1; side += 2)
    {
      int post = x + side * 27;
      rect (post - 3, y + 6, 7, 76, 43, 29, 24);
      rect (post - 1, y + 8, 3, 72, 139, 93, 48);
      rect (post - 1, y + 8, 1, 72, 218, 172, 97);
      rect (post - 3, y + 12, 7, 4, 194, 143, 72);
      rect (post - 3, y + 72, 7, 4, 194, 143, 72);
    }
  for (row = 0; row < 28; row++)
    {
      int half = glass_half_width (row);
      total += 2 * half - 3;
      for (side = -1; side <= 1; side += 2)
        {
          int edge = x + side * half;
          rect (edge - 1, y + 13 + row, 3, 1, 32, 44, 53);
          rect (edge - 1, y + 71 - row, 3, 1, 32, 44, 53);
          rect (edge, y + 13 + row, 1, 1, 157, 200, 201);
          rect (edge, y + 71 - row, 1, 1, 117, 167, 177);
        }
    }
  /* Fill by pixel area rather than height to keep both bulbs in step. */
  remaining = total * s->remaining / 30000;
  fallen = total - remaining;
  for (row = 27; row >= 0; row--)
    {
      int span = 2 * glass_half_width (row) - 3;
      int fill = remaining < span ? remaining : span;
      if (fill)
        rect (x - fill / 2, y + 13 + row, fill, 1, 234, 184, 93);
      remaining -= fill;
    }
  for (row = 0; row < 28; row++)
    {
      int span = 2 * glass_half_width (row) - 3;
      int fill = fallen < span ? fallen : span;
      if (fill)
        rect (x - fill / 2, y + 71 - row, fill, 1, 219, 155, 65);
      fallen -= fill;
      if (!s->cancelled && fallen == 0 && row > 2)
        break;
    }
  if (!s->cancelled)
    for (row = 0; row < 4; row++)
      rect (x, y + 42 + (row * 6 + now / 100) % 24, 1, 2, 250, 213, 132);
  rect (x - 2, y + 40, 1, 4, 157, 200, 201);
  rect (x + 2, y + 40, 1, 4, 117, 167, 177);
  for (row = 0; row < 2; row++)
    {
      int base = y + row * 78;
      rect (x - 31, base + 2, 63, 8, 40, 27, 25);
      rect (x - 29, base, 59, 8, 98, 57, 34);
      rect (x - 28, base + 1, 57, 2, 218, 172, 97);
      rect (x - 25, base + 4, 51, 2, 157, 107, 55);
      rect (x - 24, base + 6, 49, 1, 65, 40, 29);
    }
  {
    char text[24];
    grub_snprintf (text, sizeof text, "%ds", (s->remaining + 999) / 1000);
    label (s->cancelled ? "PAUSED" : text, x * ui_scale,
           (y + 108) * ui_scale, 1);
  }
}

static enum scene_key
key (int value)
{
  switch (value)
    {
    case GRUB_TERM_NO_KEY: return SCENE_NONE;
    case GRUB_TERM_KEY_LEFT: return SCENE_LEFT;
    case GRUB_TERM_KEY_RIGHT: return SCENE_RIGHT;
    case ' ': return SCENE_SPACE;
    case 'l': case 'L': return SCENE_LINUX;
    case 'w': case 'W': return SCENE_WINDOWS;
    case GRUB_TERM_ESC: return SCENE_ESCAPE;
    default: return SCENE_OTHER;
    }
}

static grub_menu_entry_t
find_entry (const char *id, unsigned *index)
{
  grub_menu_t menu = grub_env_get_menu ();
  grub_menu_entry_t entry, found = 0;
  unsigned position = 0;
  for (entry = menu ? menu->entry_list : 0; entry; entry = entry->next)
    {
      if (entry->id && grub_strcmp (entry->id, id) == 0)
        {
          if (found || entry->submenu)
            return 0;
          found = entry;
          if (index)
            *index = position;
        }
      position++;
    }
  return found;
}

static grub_err_t
load_scaled (struct grub_video_bitmap **result, const char *path, int w, int h)
{
  struct grub_video_bitmap *original = 0;
  grub_err_t err = grub_video_bitmap_load (&original, path);
  if (!err)
    err = grub_video_bitmap_create_scaled (result, w, h, original,
                                          GRUB_VIDEO_BITMAP_SCALE_METHOD_NEAREST);
  grub_video_bitmap_destroy (original);
  return err;
}

static grub_err_t
select_entry (const char *id, int manual)
{
  unsigned index;
  char number[24];
  grub_menu_entry_t entry = find_entry (id, &index);
  grub_err_t err;
  if (!entry)
    return grub_error (GRUB_ERR_BAD_ARGUMENT, "bourgeois: entry ID is no longer unique");
  if (entry->restricted)
    {
      err = grub_auth_check_authentication (entry->users);
      if (err)
        return err;
    }
  /* GRUB resolves default as a number or title before trying entry IDs. */
  grub_snprintf (number, sizeof number, "%u", index);
  err = grub_env_set ("default", number);
  if (!err)
    err = grub_env_set ("timeout", "0");
  if (!err && manual)
    grub_env_unset ("fallback");
  return err;
}

static grub_err_t
restore_terminal (const char *background, grub_font_t scene_font)
{
  char *console[] = { (char *) "console" };
  char *terminal[] = { (char *) "gfxterm" };
  char *image[] = { (char *) "--mode=stretch", (char *) background };
  struct grub_video_mode_info info;
  struct grub_error_saved saved;
  grub_err_t err;

  /* Disable gfxterm before replacing the adapter that owns its window. */
  err = grub_command_execute ("terminal_output", 1, console);
  if (err)
    return err;
  err = grub_video_restore ();
  if (err)
    return err;
  err = grub_command_execute ("terminal_output", 1, terminal);
  if (err)
    goto console_fallback;
  if (!scene_font)
    return GRUB_ERR_NONE;

  /* A former theme may have narrowed the terminal. Handoff messages belong
     to a full-screen window with the courtyard behind them. */
  err = grub_video_get_info (&info);
  if (!err)
    err = grub_gfxterm_set_window (GRUB_VIDEO_RENDER_TARGET_DISPLAY,
                                  0, 0, info.width, info.height,
                                  (info.mode_type & GRUB_VIDEO_MODE_TYPE_DOUBLE_BUFFERED)
                                  && !(info.mode_type & GRUB_VIDEO_MODE_TYPE_UPDATING_SWAP),
                                  scene_font, 0);
  if (err)
    goto console_fallback;
  if (grub_command_execute ("background_image", 2, image))
    {
      trace ("BOURGEOIS_BACKGROUND_UNAVAILABLE");
      grub_print_error ();
    }
  return GRUB_ERR_NONE;

 console_fallback:
  /* Window setup destroys the previous window even when its replacement
     fails. Keep a usable console and preserve the setup error. */
  saved.grub_errno = err;
  grub_memcpy (saved.errmsg, grub_errmsg, sizeof saved.errmsg);
  grub_errno = GRUB_ERR_NONE;
  grub_command_execute ("terminal_output", 1, console);
  grub_errno = saved.grub_errno;
  grub_memcpy (grub_errmsg, saved.errmsg, sizeof saved.errmsg);
  return err;
}

static grub_err_t
run_scene (grub_command_t cmd __attribute__ ((unused)), int argc, char **args)
{
  struct grub_video_bitmap *background = 0, *actor = 0, *left_actor = 0;
  struct scene_state state = { 0 };
  enum scene_action action = SCENE_WAIT;
  grub_err_t err = GRUB_ERR_NONE, recovery_err;
  struct grub_error_saved saved;
  unsigned x, y;
  int frame_width = 0, frame_height = 0;
  unsigned frames = 0, render_total = 0, render_max = 0;
  char *console[] = { (char *) "console" };
  const char *mode = grub_env_get ("bourgeois_gfxmode");
  if (!mode || !*mode)
    mode = grub_env_get ("gfxmode");
  if (argc != 4 || !find_entry (args[0], 0) || !find_entry (args[1], 0)
      || grub_strcmp (args[0], args[1]) == 0)
    return grub_error (GRUB_ERR_BAD_ARGUMENT, "bourgeois: expected two unique entry IDs and two assets");
  err = grub_env_set ("timeout", "-1");
  if (err)
    return err;
  err = grub_command_execute ("terminal_output", 1, console);
  if (err)
    return err;
  err = grub_video_set_mode (mode && *mode ? mode : "auto",
                            GRUB_VIDEO_MODE_TYPE_PURE_TEXT, 0);
  if (err)
    goto done;
  err = grub_video_get_viewport (&x, &y, &width, &height);
  if (err)
    goto done;
  if (width < 800 || height < 600)
    {
      err = grub_error (GRUB_ERR_BAD_ARGUMENT, "bourgeois: display must be at least 800x600");
      goto done;
    }
  ui_scale = scene_ui_scale (width, height);
  {
    char name[64];
    grub_snprintf (name, sizeof name, "Bourgeois UI Regular %u", 20 * ui_scale);
    font = grub_font_get (name);
    if (!font || grub_strcmp (grub_font_get_name (font), name) != 0)
      {
        err = grub_error (GRUB_ERR_BAD_FONT, "bourgeois: load font `%s' first", name);
        goto done;
      }
  }
  frame_height = height / 7;
  frame_width = frame_height * 5 / 8;
  if ((err = load_scaled (&background, args[2], width, height))
      || (err = load_scaled (&actor, args[3], frame_width * 4, frame_height)))
    goto done;
  if ((err = grub_video_bitmap_create (&left_actor, frame_width * 4, frame_height,
                                       actor->mode_info.blit_format)))
    goto done;
  {
    int frame, row, col, bytes = actor->mode_info.bytes_per_pixel;
    for (frame = 0; frame < 4; frame++)
      for (row = 0; row < frame_height; row++)
        for (col = 0; col < frame_width; col++)
          grub_memcpy ((char *) left_actor->data + row * left_actor->mode_info.pitch
                       + (frame * frame_width + col) * bytes,
                       (char *) actor->data + row * actor->mode_info.pitch
                       + (frame * frame_width + frame_width - 1 - col) * bytes, bytes);
  }
  scene_init (&state, grub_get_time_ms ());
  trace ("BOURGEOIS_SCENE_READY");
  while (action == SCENE_WAIT)
    {
      grub_uint64_t now = grub_get_time_ms ();
      enum scene_key input = key (grub_getkey_noblock ());
      int was_cancelled = state.cancelled;
      action = scene_step (&state, now, input);
      if (!was_cancelled && state.cancelled)
        trace ("BOURGEOIS_TIMER_CANCELLED");
      if (action != SCENE_WAIT)
        break;
      err = grub_video_blit_bitmap (background, GRUB_VIDEO_BLIT_REPLACE,
                                    0, 0, 0, 0, width, height);
      if (err)
        goto done;
      label ("CHOOSE YOUR KINGDOM", width / 2, 49 * ui_scale, 1);
      label ("A journey begins with a door", width / 2, 72 * ui_scale, 0);
      {
        int frame = state.x != state.target ? (now / 140) % 4 : 0;
        err = grub_video_blit_bitmap (state.facing_left ? left_actor : actor, GRUB_VIDEO_BLIT_BLEND,
                                      state.x * width / SCENE_WIDTH - frame_width / 2,
                                      height * 73 / 100 - frame_height,
                                      frame * frame_width, 0, frame_width, frame_height);
        if (err)
          goto done;
      }
      label (state.x == SCENE_LINUX_GATE_X ? "Space: enter Linux"
             : state.x == SCENE_WINDOWS_GATE_X ? "Space: enter Windows"
             : "Left / Right: walk to a gate", width / 2, height - 88 * ui_scale, 1);
      label ("L/W: boot now    Esc: technical menu", width / 2, height - 62 * ui_scale, 0);
      label (state.cancelled ? "Auto-boot cancelled for this visit"
             : "Linux boots when the sand runs out", width / 2, height - 36 * ui_scale, 0);
      hourglass (&state, now);
      err = grub_errno;
      if (!err)
        err = grub_video_swap_buffers ();
      if (err)
        goto done;
      {
        unsigned elapsed = grub_get_time_ms () - now;
        frames++;
        render_total += elapsed;
        if (elapsed > render_max)
          render_max = elapsed;
        grub_millisleep (elapsed < 17 ? 17 - elapsed : 1);
      }
    }
  if (action == SCENE_TECHNICAL)
    trace ("BOURGEOIS_TECHNICAL");
 done:
  if (frames)
    {
      char stats[160];
      grub_snprintf (stats, sizeof stats,
                     "BOURGEOIS_RENDER %ux%u frames=%u avg_ms=%u max_ms=%u bitmap_bytes=%u",
                     width, height, frames, render_total / frames, render_max,
                     background->mode_info.pitch * height + actor->mode_info.pitch * frame_height * 2);
      trace (stats);
    }
  grub_video_bitmap_destroy (left_actor);
  grub_video_bitmap_destroy (actor);
  grub_video_bitmap_destroy (background);
  saved.grub_errno = err;
  grub_memcpy (saved.errmsg, grub_errmsg, sizeof saved.errmsg);
  grub_errno = GRUB_ERR_NONE;
  recovery_err = restore_terminal (args[2], err ? 0 : font);
  if (err)
    {
      grub_errno = saved.grub_errno;
      grub_memcpy (grub_errmsg, saved.errmsg, sizeof saved.errmsg);
    }
  else
    err = recovery_err;
  if (!err && (action == SCENE_BOOT_LINUX || action == SCENE_BOOT_WINDOWS))
    {
      const char *selected = args[action == SCENE_BOOT_LINUX ? 0 : 1];
      err = select_entry (selected, state.cancelled);
      if (!err)
        trace (action == SCENE_BOOT_LINUX ? "BOURGEOIS_SELECT_LINUX" : "BOURGEOIS_SELECT_WINDOWS");
    }
  return err;
}

GRUB_MOD_INIT (bourgeois)
{
  grub_env_set ("feature_bourgeois", "1");
  grub_env_export ("feature_bourgeois");
  command = grub_register_command ("bourgeois", run_scene, "LINUX_ID WINDOWS_ID BACKGROUND SPRITES",
                                   "Walk to an operating system gate.");
}
GRUB_MOD_FINI (bourgeois)
{
  grub_env_unset ("feature_bourgeois");
  grub_unregister_command (command);
}
