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
#include <grub/gfxmenu_view.h>
#include <grub/menu.h>
#include <grub/misc.h>
#include <grub/mm.h>
#include <grub/normal.h>
#include <grub/term.h>
#include <grub/time.h>
#include <grub/video.h>
#include <grub/cpu/io.h>
#include "state.h"

GRUB_MOD_LICENSE ("GPLv3+");
static grub_command_t command;
static unsigned width, height;
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
  grub_video_fill_rect (grub_video_map_rgb (r, g, b), x, y, w, h);
}

static void
label (const char *text, int center, int y, int gold)
{
  int text_width = grub_font_get_string_width (font, text);
  grub_font_draw_string (text, font,
                        gold ? grub_video_map_rgb (250, 221, 165)
                             : grub_video_map_rgb (208, 215, 209),
                        center - text_width / 2, y);
}

static void
hourglass (struct scene_state *s)
{
  int x = width - 84, y = 42, row;
  int used = (30000 - s->remaining) * 20 / 30000;
  rect (x - 18, y - 14, 72, 116, 22, 30, 39);
  rect (x, y, 36, 5, 203, 160, 94);
  rect (x, y + 60, 36, 5, 203, 160, 94);
  for (row = 0; row < 27; row++)
    {
      int half = 16 - row / 2;
      rect (x + 18 - half, y + 5 + row, 2, 1, 148, 189, 198);
      rect (x + 18 + half, y + 5 + row, 2, 1, 148, 189, 198);
      rect (x + 18 - half, y + 59 - row, 2, 1, 148, 189, 198);
      rect (x + 18 + half, y + 59 - row, 2, 1, 148, 189, 198);
      if (row >= used && row < 24)
        rect (x + 21 - half, y + 6 + row, 2 * half - 4, 1, 234, 186, 105);
      if (row < used)
        rect (x + 21 - half, y + 58 - row, 2 * half - 4, 1, 234, 186, 105);
    }
  if (!s->cancelled)
    rect (x + 18, y + 32, 2, 20 - used / 2, 234, 186, 105);
  {
    char text[24];
    grub_snprintf (text, sizeof text, "%ds", (s->remaining + 999) / 1000);
    label (s->cancelled ? "PAUSED" : text, x + 18, y + 88, 1);
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

static int
has_entry (const char *id)
{
  grub_menu_t menu = grub_env_get_menu ();
  grub_menu_entry_t entry;
  int found = 0;
  for (entry = menu ? menu->entry_list : 0; entry; entry = entry->next)
    if (!entry->submenu && entry->id && grub_strcmp (entry->id, id) == 0)
      found++;
  return found == 1;
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
run_scene (grub_command_t cmd __attribute__ ((unused)), int argc, char **args)
{
  struct grub_video_bitmap *background = 0, *actor = 0, *left_actor = 0;
  struct scene_state state;
  enum scene_action action = SCENE_WAIT;
  grub_err_t err = GRUB_ERR_NONE;
  unsigned x, y;
  int active = 0, frame_width, frame_height;
  unsigned frames = 0, render_total = 0, render_max = 0;
  const char *mode = grub_env_get ("bourgeois_gfxmode");
  if (argc != 4 || !has_entry (args[0]) || !has_entry (args[1])
      || grub_strcmp (args[0], args[1]) == 0)
    return grub_error (GRUB_ERR_BAD_ARGUMENT, "bourgeois: expected two unique entry IDs and two assets");
  font = grub_font_get ("Unifont Regular 16");
  if (!font)
    return grub_error (GRUB_ERR_BAD_FONT, "bourgeois: load a font first");
  err = grub_video_set_mode (mode ? mode : "1280x720,1024x768,auto",
                            GRUB_VIDEO_MODE_TYPE_PURE_TEXT, 0);
  if (err)
    return err;
  active = 1;
  grub_video_get_viewport (&x, &y, &width, &height);
  if (width < 800 || height < 600)
    {
      err = grub_error (GRUB_ERR_BAD_ARGUMENT, "bourgeois: display must be at least 800x600");
      goto done;
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
      grub_video_blit_bitmap (background, GRUB_VIDEO_BLIT_REPLACE, 0, 0, 0, 0, width, height);
      rect (width / 2 - 190, 24, 380, 60, 22, 30, 39);
      label ("CHOOSE YOUR KINGDOM", width / 2, 49, 1);
      label ("A journey begins with a door", width / 2, 72, 0);
      rect (width / 5 - 70, height * 28 / 100, 140, 32, 22, 30, 39);
      rect (width * 4 / 5 - 78, height * 28 / 100, 156, 32, 22, 30, 39);
      label ("LINUX  [L]", width / 5, height * 28 / 100 + 22, 1);
      label ("WINDOWS  [W]", width * 4 / 5, height * 28 / 100 + 22, 1);
      {
        int frame = state.x != state.target ? (now / 140) % 4 : 0;
        grub_video_blit_bitmap (state.target < state.origin ? left_actor : actor, GRUB_VIDEO_BLIT_BLEND,
                                state.x * width / 2400 - frame_width / 2,
                                height * 73 / 100 - frame_height,
                                frame * frame_width, 0, frame_width, frame_height);
      }
      rect (width / 2 - 310, height - 115, 620, 94, 22, 30, 39);
      label (state.x == 480 ? "Space: enter Linux" : state.x == 1920 ? "Space: enter Windows"
             : "Left / Right: walk to a gate", width / 2, height - 88, 1);
      label ("L/W: boot now    Esc: technical menu", width / 2, height - 62, 0);
      label (state.cancelled ? "Auto-boot cancelled for this visit"
             : "Linux boots when the sand runs out", width / 2, height - 36, 0);
      hourglass (&state);
      grub_video_swap_buffers ();
      {
        unsigned elapsed = grub_get_time_ms () - now;
        frames++;
        render_total += elapsed;
        if (elapsed > render_max)
          render_max = elapsed;
        grub_millisleep (elapsed < 40 ? 40 - elapsed : 1);
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
  if (active)
    {
      char *terminal[] = { (char *) "gfxterm" };
      grub_video_restore ();
      /* Reinitialize the terminal after direct GOP rendering. Restoring the
         EFI text mode alone can leave its graphical console blank. */
      grub_command_execute ("terminal_output", 1, terminal);
    }
  grub_env_set ("timeout", "-1");
  if (!err && (action == SCENE_BOOT_LINUX || action == SCENE_BOOT_WINDOWS))
    {
      const char *selected = args[action == SCENE_BOOT_LINUX ? 0 : 1];
      grub_menu_entry_t entry;
      for (entry = grub_env_get_menu ()->entry_list; entry; entry = entry->next)
        if (entry->id && grub_strcmp (entry->id, selected) == 0)
          {
            /* Authenticate before arming timeout=0. A rejected password must
               leave an interactive menu instead of retrying automatically. */
            if (entry->restricted)
              err = grub_auth_check_authentication (entry->users);
            break;
          }
      if (!err)
        err = grub_env_set ("default", selected);
      if (!err)
        {
          trace (action == SCENE_BOOT_LINUX ? "BOURGEOIS_SELECT_LINUX" : "BOURGEOIS_SELECT_WINDOWS");
          grub_env_set ("timeout", "0");
          grub_env_unset ("fallback");
        }
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
