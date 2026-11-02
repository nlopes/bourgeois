/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <assert.h>
#include <stdarg.h>
#include <stdlib.h>
#include "grub_test.h"
#include "bourgeois.c"

enum failure
{
  MODE, VIEWPORT, INFO, RESTORE, CONSOLE, GFXTERM, WINDOW, BACKGROUND,
  SPRITES, SCALE, MIRROR, AUTH, DEFAULT, ARM_TIMER, STOP_TIMER, DRAW, SWAP,
  POSES, HANDOFF_SCALE
};
enum terminal { CONSOLE_ACTIVE, GFXTERM_ACTIVE };
static unsigned failures;
static unsigned recovery_calls, window_calls, live_bitmaps, load_calls, create_calls;
static unsigned draw_calls, key_calls, scale_calls, gate_frames;
static unsigned terminal_width, terminal_height;
static enum terminal output;
static int functional, video_active, no_menu, clock_step;
static grub_uint64_t clock_now;
static char default_value[64], timeout_value[16], fallback_value[16];
static struct grub_font loaded_font;
static struct grub_command registered_command;
static struct grub_menu_entry linux_entry, windows_entry, extra_entry;
static struct grub_menu test_menu;
static int inputs[64];
static char *arguments[] = { (char *) "linux", (char *) "windows",
                            (char *) "background.png", (char *) "sprites.png",
                            (char *) "gates.png" };
struct grub_gfxterm_background grub_gfxterm_background;
grub_err_t grub_errno;
char grub_errmsg[GRUB_MAX_ERRMSG];

static int
fail (enum failure operation)
{
  if (!(failures & (1U << operation)))
    return 0;
  grub_error (GRUB_ERR_TEST_FAILURE, "injected failure %u", (unsigned) operation);
  return 1;
}

static void
reset (void)
{
  grub_video_bitmap_destroy (grub_gfxterm_background.bitmap);
  grub_gfxterm_background.bitmap = NULL;
  assert (live_bitmaps == 0);
  failures = recovery_calls = window_calls = load_calls = create_calls = draw_calls = key_calls = 0;
  scale_calls = gate_frames = 0;
  terminal_width = 800;
  terminal_height = 600;
  functional = video_active = 1;
  no_menu = 0;
  output = GFXTERM_ACTIVE;
  clock_now = 0;
  clock_step = 17;
  grub_errno = GRUB_ERR_NONE;
  grub_errmsg[0] = 0;
  strcpy (default_value, "previous");
  strcpy (timeout_value, "30");
  strcpy (fallback_value, "1");
  loaded_font.name = "Bourgeois UI Regular 20";
  linux_entry = (struct grub_menu_entry) { .id = "linux", .title = "Linux",
                                         .next = &windows_entry };
  windows_entry = (struct grub_menu_entry) { .id = "windows", .title = "Windows" };
  extra_entry = (struct grub_menu_entry) { .id = "other", .title = "Other" };
  test_menu = (struct grub_menu) { .size = 2, .entry_list = &linux_entry };
  arguments[0] = (char *) "linux";
  arguments[1] = (char *) "windows";
  memset (inputs, 0, sizeof inputs);
  inputs[0] = 'l';
  inputs[1] = GRUB_TERM_ESC;
}

static grub_err_t
run (void)
{
  grub_err_t err = run_scene (NULL, 5, arguments);
  assert (live_bitmaps == (grub_gfxterm_background.bitmap ? 1U : 0U));
  return err;
}

static void
selection (void)
{
  reset ();
  arguments[0] = (char *) "1linux";
  linux_entry.id = arguments[0];
  assert (run () == GRUB_ERR_NONE);
  assert (strcmp (default_value, "0") == 0);
  assert (grub_gfxterm_background.bitmap && grub_gfxterm_background.blend_text_bg);
  {
    unsigned x = SCENE_LINUX_GATE_X * 800 / SCENE_WIDTH;
    unsigned char *pixel = grub_gfxterm_background.bitmap->data;
    pixel += (600 * 73 / 100 - 600 / 7 + 10) * 800 * 4 + x * 4;
    assert (pixel[0] == 30 && pixel[1] == 120 && pixel[2] == 70);
  }
  key_calls = 0;
  assert (run () == GRUB_ERR_NONE);
  reset ();
  linux_entry.title = "windows";
  inputs[0] = 'w';
  assert (run () == GRUB_ERR_NONE);
  assert (strcmp (default_value, "1") == 0);
  reset ();
  extra_entry.submenu = 1;
  extra_entry.next = &linux_entry;
  test_menu.entry_list = &extra_entry;
  test_menu.size = 3;
  assert (run () == GRUB_ERR_NONE);
  assert (strcmp (default_value, "1") == 0);
}

static void
recovery (void)
{
  enum failure operation;
  for (operation = INFO; operation <= WINDOW; operation++)
    {
      reset ();
      failures = 1U << operation;
      assert (run () != GRUB_ERR_NONE);
      assert (strcmp (timeout_value, "0") != 0);
      assert (strcmp (default_value, "previous") == 0);
      if (operation != CONSOLE)
        assert (output == CONSOLE_ACTIVE && functional);
    }
}

static void
mode_failure (void)
{
  reset ();
  failures = 1U << MODE;
  assert (run () != GRUB_ERR_NONE);
  assert (recovery_calls > 0 && functional);
  assert (strcmp (timeout_value, "-1") == 0);
  assert (strstr (grub_errmsg, "injected failure 0") != NULL);
}

static void
fallback (void)
{
  reset ();
  clock_step = 30000;
  inputs[0] = GRUB_TERM_NO_KEY;
  assert (run () == GRUB_ERR_NONE);
  assert (strcmp (timeout_value, "0") == 0);
  assert (strcmp (fallback_value, "1") == 0);
  reset ();
  assert (run () == GRUB_ERR_NONE);
  assert (fallback_value[0] == 0);
}

static void
missing_font (void)
{
  reset ();
  loaded_font.name = "Bourgeois UI Regular 120";
  assert (run () == GRUB_ERR_BAD_FONT);
  assert (load_calls == 0 && functional);
  assert (strcmp (timeout_value, "-1") == 0);
  assert (strstr (grub_errmsg, "font") != NULL);
  reset ();
  loaded_font.name = "<No Font>";
  assert (run () == GRUB_ERR_BAD_FONT);
}

static void
invalid_entries (void)
{
  reset ();
  no_menu = 1;
  assert (run () == GRUB_ERR_BAD_ARGUMENT);
  reset ();
  windows_entry.id = "linux";
  assert (run () == GRUB_ERR_BAD_ARGUMENT);
  reset ();
  extra_entry.id = "linux";
  extra_entry.submenu = 1;
  windows_entry.next = &extra_entry;
  assert (run () == GRUB_ERR_BAD_ARGUMENT);
  reset ();
  assert (run_scene (NULL, 0, NULL) == GRUB_ERR_BAD_ARGUMENT);
  assert (recovery_calls == 0);
}

static void
failures_before_boot (void)
{
  enum failure operations[] = { VIEWPORT, BACKGROUND, SPRITES, SCALE, MIRROR,
                                AUTH, DEFAULT, ARM_TIMER, STOP_TIMER, DRAW, SWAP, POSES };
  unsigned i;
  for (i = 0; i < sizeof operations / sizeof operations[0]; i++)
    {
      reset ();
      linux_entry.restricted = 1;
      linux_entry.users = "test-user";
      if (operations[i] == DRAW || operations[i] == SWAP)
        inputs[0] = GRUB_TERM_NO_KEY;
      failures = 1U << operations[i];
      assert (run () != GRUB_ERR_NONE);
      assert (strcmp (timeout_value, "0") != 0);
      assert (fallback_value[0] != 0);
    }
  reset ();
  failures = (1U << BACKGROUND) | (1U << GFXTERM);
  assert (run () != GRUB_ERR_NONE);
  assert (strstr (grub_errmsg, "injected failure 7") != NULL);
}

static void
enter_and_handoff (void)
{
  unsigned i;
  reset ();
  clock_step = 100;
  for (i = 0; i < 64; i++)
    inputs[i] = GRUB_TERM_NO_KEY;
  inputs[0] = GRUB_TERM_KEY_RIGHT;
  inputs[8] = ' ';
  assert (run () == GRUB_ERR_NONE);
  assert ((gate_frames & 13) == 13);
  assert (strcmp (default_value, "1") == 0);
  reset ();
  terminal_width = 1024;
  terminal_height = 768;
  assert (run () == GRUB_ERR_NONE);
  assert (grub_gfxterm_background.bitmap->mode_info.width == 1024);
  reset ();
  terminal_width = 1024;
  failures = 1U << HANDOFF_SCALE;
  assert (run () != GRUB_ERR_NONE);
  assert (grub_gfxterm_background.bitmap == NULL && functional);
  assert (strcmp (timeout_value, "-1") == 0);
}

static void
render_and_escape (void)
{
  reset ();
  inputs[0] = GRUB_TERM_NO_KEY;
  assert (run () == GRUB_ERR_NONE);
  assert (draw_calls > 0 && window_calls == 1 && functional);
  assert (strcmp (timeout_value, "-1") == 0);
  assert (strcmp (default_value, "previous") == 0);
  test_module_init ();
  test_module_fini ();
}

int
main (int argc, char **argv)
{
  struct { const char *name; void (*test) (void); } cases[] = {
    { "selection", selection }, { "recovery", recovery },
    { "mode", mode_failure }, { "fallback", fallback }, { "font", missing_font },
    { "entries", invalid_entries }, { "failures", failures_before_boot },
    { "render", render_and_escape }, { "enter", enter_and_handoff }
  };
  unsigned i;
  for (i = 0; i < sizeof cases / sizeof cases[0]; i++)
    if (argc == 1 || strcmp (argv[1], cases[i].name) == 0)
      {
        cases[i].test ();
        printf ("PASS command: %s\n", cases[i].name);
      }
  grub_video_bitmap_destroy (grub_gfxterm_background.bitmap);
  assert (live_bitmaps == 0);
  return 0;
}

grub_err_t
grub_error (grub_err_t code, const char *format, ...)
{
  va_list args;
  va_start (args, format);
  vsnprintf (grub_errmsg, sizeof grub_errmsg, format, args);
  va_end (args);
  return grub_errno = code;
}

void grub_print_error (void) { grub_errno = GRUB_ERR_NONE; }

const char *
grub_env_get (const char *name)
{
  if (strcmp (name, "default") == 0) return default_value;
  if (strcmp (name, "timeout") == 0) return timeout_value;
  if (strcmp (name, "fallback") == 0) return fallback_value;
  return NULL;
}

grub_err_t
grub_env_set (const char *name, const char *value)
{
  if (strcmp (name, "default") == 0)
    {
      if (fail (DEFAULT)) return GRUB_ERR_TEST_FAILURE;
      snprintf (default_value, sizeof default_value, "%s", value);
    }
  if (strcmp (name, "timeout") == 0)
    {
      if (fail (strcmp (value, "0") == 0 ? ARM_TIMER : STOP_TIMER)) return GRUB_ERR_TEST_FAILURE;
      snprintf (timeout_value, sizeof timeout_value, "%s", value);
    }
  return GRUB_ERR_NONE;
}

void grub_env_unset (const char *name)
{ if (strcmp (name, "fallback") == 0) fallback_value[0] = 0; }
grub_err_t grub_env_export (const char *name) { (void) name; return GRUB_ERR_NONE; }
grub_menu_t grub_env_get_menu (void) { return no_menu ? NULL : &test_menu; }

grub_err_t
grub_auth_check_authentication (const char *users)
{
  assert (functional && users && strcmp (users, "test-user") == 0);
  return fail (AUTH) ? GRUB_ERR_TEST_FAILURE : GRUB_ERR_NONE;
}

grub_command_t
grub_register_command (const char *name, grub_err_t (*func) (grub_command_t, int, char **),
                       const char *summary, const char *description)
{
  (void) name; (void) func; (void) summary; (void) description;
  registered_command.registered = 1;
  return &registered_command;
}
void grub_unregister_command (grub_command_t cmd) { assert (cmd && cmd->registered); }

grub_err_t
grub_command_execute (const char *name, int argc, char **args)
{
  assert (argc > 0 && args);
  if (strcmp (name, "terminal_output") == 0)
    {
      recovery_calls++;
      if (strcmp (args[0], "console") == 0)
        {
          if (fail (CONSOLE)) return GRUB_ERR_TEST_FAILURE;
          output = CONSOLE_ACTIVE;
          functional = 1;
          video_active = 0;
          grub_errno = GRUB_ERR_NONE;
        }
      else
        {
          assert (strcmp (args[0], "gfxterm") == 0);
          if (fail (GFXTERM)) return GRUB_ERR_TEST_FAILURE;
          output = GFXTERM_ACTIVE;
          functional = video_active = 1;
        }
    }
  return GRUB_ERR_NONE;
}

void grub_outb (unsigned char value, unsigned short port) { (void) value; (void) port; }
grub_font_t grub_font_get (const char *name) { (void) name; return &loaded_font; }
const char *grub_font_get_name (grub_font_t value) { return value->name; }
int grub_font_get_string_width (grub_font_t value, const char *text)
{ (void) value; return (int) strlen (text) * 10; }
grub_err_t grub_font_draw_string (const char *text, grub_font_t value,
                                 grub_video_color_t color, int x, int y)
{ (void) text; (void) value; (void) color; (void) x; (void) y; return GRUB_ERR_NONE; }

grub_err_t
grub_video_set_mode (const char *mode, unsigned mask, unsigned value)
{
  (void) mode; (void) mask; (void) value;
  video_active = 0;
  if (fail (MODE)) { functional = 0; return GRUB_ERR_TEST_FAILURE; }
  video_active = 1;
  return GRUB_ERR_NONE;
}
grub_err_t
grub_video_get_viewport (unsigned *x, unsigned *y, unsigned *w, unsigned *h)
{
  if (fail (VIEWPORT)) return GRUB_ERR_TEST_FAILURE;
  *x = *y = 0; *w = 800; *h = 600;
  return GRUB_ERR_NONE;
}
grub_err_t
grub_video_get_info (struct grub_video_mode_info *info)
{
  if (fail (INFO)) return GRUB_ERR_TEST_FAILURE;
  *info = (struct grub_video_mode_info) { .width = terminal_width, .height = terminal_height };
  return GRUB_ERR_NONE;
}
grub_err_t grub_video_restore (void)
{ video_active = 0; return fail (RESTORE) ? GRUB_ERR_TEST_FAILURE : GRUB_ERR_NONE; }
grub_video_color_t grub_video_map_rgb (unsigned char r, unsigned char g, unsigned char b)
{ return (unsigned) r << 16 | (unsigned) g << 8 | b; }
grub_err_t grub_video_fill_rect (grub_video_color_t color, int x, int y, unsigned w, unsigned h)
{ (void) color; (void) x; (void) y; (void) w; (void) h; return GRUB_ERR_NONE; }
grub_err_t
grub_video_blit_bitmap (struct grub_video_bitmap *bitmap, int operation,
                        int x, int y, int sx, int sy, unsigned w, unsigned h)
{
  (void) operation; (void) x; (void) y;
  assert (bitmap && video_active && sx >= 0 && sy >= 0);
  assert ((unsigned) sx + w <= bitmap->mode_info.width);
  assert ((unsigned) sy + h <= bitmap->mode_info.height);
  if (bitmap->mode_info.width == (600 / 7 * 3 / 4) * 4 && w)
    gate_frames |= 1U << ((unsigned) sx / w);
  draw_calls++;
  return fail (DRAW) ? GRUB_ERR_TEST_FAILURE : GRUB_ERR_NONE;
}
grub_err_t grub_video_swap_buffers (void) { return fail (SWAP) ? GRUB_ERR_TEST_FAILURE : GRUB_ERR_NONE; }

grub_err_t
grub_video_bitmap_create (struct grub_video_bitmap **bitmap, unsigned w, unsigned h, int format)
{
  create_calls++;
  if (create_calls == 5 && fail (MIRROR)) return GRUB_ERR_TEST_FAILURE;
  *bitmap = calloc (1, sizeof **bitmap);
  assert (*bitmap);
  (*bitmap)->mode_info = (struct grub_video_mode_info) {
    .width = w, .height = h, .pitch = w * 4, .blit_format = (unsigned) format,
    .bytes_per_pixel = 4
  };
  (*bitmap)->data = calloc (h, w * 4);
  assert ((*bitmap)->data);
  live_bitmaps++;
  return GRUB_ERR_NONE;
}
grub_err_t
grub_video_bitmap_load (struct grub_video_bitmap **bitmap, const char *path)
{
  unsigned i;
  grub_err_t err;
  (void) path;
  load_calls++;
  if (load_calls == 3 && fail (POSES)) return GRUB_ERR_TEST_FAILURE;
  if (fail (load_calls == 1 ? BACKGROUND : SPRITES)) return GRUB_ERR_TEST_FAILURE;
  err = grub_video_bitmap_create (bitmap, 4, 1, 0);
  if (err)
    return err;
  for (i = 0; i < 4; i++)
    {
      unsigned char *pixel = (unsigned char *) (*bitmap)->data + i * 4;
      pixel[0] = load_calls == 3 ? 30 : 20;
      pixel[1] = load_calls == 3 ? 120 : 30;
      pixel[2] = load_calls == 3 ? 70 : 60;
      pixel[3] = 255;
    }
  return GRUB_ERR_NONE;
}
grub_err_t
grub_video_bitmap_create_scaled (struct grub_video_bitmap **bitmap, int w, int h,
                                 struct grub_video_bitmap *src, int method)
{
  grub_err_t err;
  unsigned row, col;
  (void) method;
  assert (src && w > 0 && h > 0);
  scale_calls++;
  if (scale_calls == 4 && fail (HANDOFF_SCALE)) return GRUB_ERR_TEST_FAILURE;
  if (fail (SCALE)) return GRUB_ERR_TEST_FAILURE;
  err = grub_video_bitmap_create (bitmap, (unsigned) w, (unsigned) h, 0);
  if (err)
    return err;
  for (row = 0; row < (unsigned) h; row++)
    for (col = 0; col < (unsigned) w; col++)
      memcpy ((unsigned char *) (*bitmap)->data + row * (*bitmap)->mode_info.pitch + col * 4,
              src->data, 4);
  return GRUB_ERR_NONE;
}
grub_err_t
grub_video_bitmap_destroy (struct grub_video_bitmap *bitmap)
{
  if (bitmap)
    {
      assert (live_bitmaps > 0);
      live_bitmaps--;
      free (bitmap->data);
      free (bitmap);
    }
  return GRUB_ERR_NONE;
}
grub_err_t
grub_gfxterm_set_window (struct grub_video_render_target *target, int x, int y,
                         int w, int h, int repaint, grub_font_t value, int border)
{
  (void) target; (void) x; (void) y; (void) w; (void) h;
  (void) repaint; (void) value; (void) border;
  window_calls++;
  functional = 0;
  if (fail (WINDOW)) return GRUB_ERR_TEST_FAILURE;
  functional = 1;
  return GRUB_ERR_NONE;
}
grub_uint64_t grub_get_time_ms (void) { clock_now += (unsigned) clock_step; return clock_now; }
int grub_getkey_noblock (void) { assert (key_calls < 64); return inputs[key_calls++]; }
void grub_millisleep (grub_uint64_t duration) { (void) duration; }
void grub_gfxterm_schedule_repaint (void) { assert (functional); }
