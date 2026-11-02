/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef BOURGEOIS_GRUB_TEST_H
#define BOURGEOIS_GRUB_TEST_H

/* Host test declarations. The native build checks the real GRUB headers. */
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>

typedef int grub_err_t;
typedef uint64_t grub_uint64_t;
typedef uint32_t grub_video_color_t;
struct grub_command { int registered; };
typedef struct grub_command *grub_command_t;
struct grub_font { const char *name; };
typedef struct grub_font *grub_font_t;

#define GRUB_MOD_LICENSE(value)
#define GRUB_MOD_INIT(name) static void test_module_init (void)
#define GRUB_MOD_FINI(name) static void test_module_fini (void)
#define GRUB_MAX_ERRMSG 256
enum { GRUB_ERR_NONE, GRUB_ERR_BAD_ARGUMENT, GRUB_ERR_BAD_FONT,
       GRUB_ERR_TEST_FAILURE, GRUB_ERR_FILE_NOT_FOUND };
enum { GRUB_VIDEO_MODE_TYPE_PURE_TEXT = 1,
       GRUB_VIDEO_MODE_TYPE_DOUBLE_BUFFERED = 2,
       GRUB_VIDEO_MODE_TYPE_UPDATING_SWAP = 4 };
enum { GRUB_VIDEO_BLIT_REPLACE, GRUB_VIDEO_BLIT_BLEND,
       GRUB_VIDEO_BITMAP_SCALE_METHOD_NEAREST };
enum { GRUB_TERM_NO_KEY = -1, GRUB_TERM_ESC = 27,
       GRUB_TERM_KEY_LEFT = 1000, GRUB_TERM_KEY_RIGHT };
#define GRUB_VIDEO_RENDER_TARGET_DISPLAY NULL
#define grub_strcmp strcmp
#define grub_memcpy memcpy
#define grub_snprintf snprintf

struct grub_error_saved
{
  grub_err_t grub_errno;
  char errmsg[GRUB_MAX_ERRMSG];
};
struct grub_menu_entry
{
  const char *id, *title, *users;
  int restricted, submenu;
  struct grub_menu_entry *next;
};
typedef struct grub_menu_entry *grub_menu_entry_t;
struct grub_menu { int size; grub_menu_entry_t entry_list; };
typedef struct grub_menu *grub_menu_t;
struct grub_video_mode_info
{
  unsigned width, height, pitch, blit_format, bytes_per_pixel, mode_type;
};
struct grub_video_bitmap
{
  struct grub_video_mode_info mode_info;
  void *data;
};
struct grub_video_render_target;

extern grub_err_t grub_errno;
extern char grub_errmsg[GRUB_MAX_ERRMSG];
grub_err_t grub_error (grub_err_t code, const char *format, ...)
  __attribute__ ((format (printf, 2, 3)));
void grub_print_error (void);
const char *grub_env_get (const char *name);
grub_err_t grub_env_set (const char *name, const char *value);
void grub_env_unset (const char *name);
grub_err_t grub_env_export (const char *name);
grub_menu_t grub_env_get_menu (void);
grub_err_t grub_auth_check_authentication (const char *users);
grub_command_t grub_register_command (const char *name,
                                     grub_err_t (*func) (grub_command_t, int, char **),
                                     const char *summary, const char *description);
void grub_unregister_command (grub_command_t cmd);
grub_err_t grub_command_execute (const char *name, int argc, char **args);
void grub_outb (unsigned char value, unsigned short port);
grub_font_t grub_font_get (const char *name);
const char *grub_font_get_name (grub_font_t value);
int grub_font_get_string_width (grub_font_t value, const char *text);
grub_err_t grub_font_draw_string (const char *text, grub_font_t value,
                                 grub_video_color_t color, int x, int y);
grub_err_t grub_video_set_mode (const char *mode, unsigned mask, unsigned value);
grub_err_t grub_video_get_viewport (unsigned *x, unsigned *y, unsigned *w, unsigned *h);
grub_err_t grub_video_get_info (struct grub_video_mode_info *info);
grub_err_t grub_video_restore (void);
grub_video_color_t grub_video_map_rgb (unsigned char r, unsigned char g, unsigned char b);
grub_err_t grub_video_fill_rect (grub_video_color_t color, int x, int y,
                                unsigned w, unsigned h);
grub_err_t grub_video_blit_bitmap (struct grub_video_bitmap *bitmap, int operation,
                                  int x, int y, int sx, int sy, unsigned w, unsigned h);
grub_err_t grub_video_swap_buffers (void);
grub_err_t grub_video_bitmap_create (struct grub_video_bitmap **bitmap,
                                    unsigned w, unsigned h, int format);
grub_err_t grub_video_bitmap_load (struct grub_video_bitmap **bitmap, const char *path);
grub_err_t grub_video_bitmap_create_scaled (struct grub_video_bitmap **bitmap,
                                           int w, int h, struct grub_video_bitmap *src,
                                           int method);
grub_err_t grub_video_bitmap_destroy (struct grub_video_bitmap *bitmap);
grub_err_t grub_gfxterm_set_window (struct grub_video_render_target *target,
                                   int x, int y, int w, int h, int repaint,
                                   grub_font_t value, int border);
grub_uint64_t grub_get_time_ms (void);
int grub_getkey_noblock (void);
void grub_millisleep (grub_uint64_t duration);

#endif
