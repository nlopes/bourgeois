"""Extract two native entries without rewriting Ubuntu's boot commands."""

from dataclasses import dataclass
import re
import shlex


@dataclass
class Block:
    start: int
    opening: int
    end: int
    kind: str
    header: str


def blocks(source):
    """Read command blocks, ignoring quoted braces, comments, and ${variables}."""
    result = []
    stack = []
    quote = None
    escaped = False
    comment = False
    variable = 0
    command_start = 0
    for index, char in enumerate(source):
        if comment:
            if char == '\n':
                comment = False
                command_start = index + 1
            continue
        if escaped:
            escaped = False
            continue
        if char == '\\' and quote != "'":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            continue
        if char == '#' and (index == 0 or source[index - 1].isspace()):
            comment = True
            continue
        if char == '{' and index and source[index - 1] == '$':
            variable += 1
            continue
        if variable:
            if char == '{':
                variable += 1
            elif char == '}':
                variable -= 1
            continue
        if char == '{':
            start = command_start
            header = source[start:index].strip()
            kind = header.split(None, 1)[0] if header else ''
            stack.append((start, index, kind, header))
            command_start = index + 1
        elif char == '}':
            if not stack:
                raise ValueError('Unmatched closing brace')
            start, opening, kind, header = stack.pop()
            result.append(Block(start, opening, index + 1, kind, header))
            command_start = index + 1
        elif char in '\n;':
            command_start = index + 1
    if stack or quote or variable or escaped:
        raise ValueError('Incomplete GRUB configuration')
    return sorted(result, key=lambda block: block.start)


def entry_id(block):
    words = shlex.split(block.header, comments=False)
    for index, word in enumerate(words):
        if word == '--id' or word == '$menuentry_id_option':
            if index + 1 < len(words):
                return words[index + 1]
        if word.startswith('--id='):
            return word[5:]
    return None


def safe_id(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError(f'Unsupported entry ID: {value!r}')
    return value


def generate(source, linux_id, windows_id, theme='$prefix/bourgeois/theme.txt'):
    """Build the door selector and a native boot menu from the same source."""
    ids = [safe_id(linux_id), safe_id(windows_id)]
    if ids[0] == ids[1]:
        raise ValueError('Linux and Windows must have different entry IDs')
    parsed = blocks(source)
    menus = [b for b in parsed if b.kind in ('menuentry', 'submenu')]
    outer = [b for b in menus if not any(p.start < b.start < p.end for p in menus)]
    chosen = []
    for identifier in ids:
        matches = [b for b in menus if b.kind == 'menuentry' and entry_id(b) == identifier]
        if len(matches) != 1:
            raise ValueError(f'Expected one entry for {identifier}; found {len(matches)}')
        if any(p.kind == 'submenu' and p.start < matches[0].start < p.end for p in menus):
            raise ValueError('Choose top-level entries to preserve submenu authentication')
        chosen.append(matches[0])
    support = source
    for block in reversed(outer):
        support = support[:block.start] + '\ntrue\n' + support[block.end:]
    output = [support, '\n# bourgeois: preserve native execution and authentication.\n',
              'if [ "${bourgeois_enter}" = "true" ]; then\n']
    for name, key, identifier, block in zip(('Linux', 'Windows'), ('l', 'w'), ids, chosen):
        # Replace only the title and hotkey. Keep authentication, classes, IDs, and body.
        header = re.sub(r"^menuentry\s+(?:'[^']*'|\"[^\"]*\"|\S+)",
                        f"menuentry '{name}'", block.header, count=1)
        header = re.sub(r'\s+--hotkey(?:=\S+|\s+\S+)', '', header)
        output.append(f'{header} --hotkey={key} ' + source[block.opening:block.end] + '\n')
    output.append(f'''unset theme
terminal_output console
insmod all_video
insmod gfxterm
loadfont unicode
set gfxmode=1280x720,1024x768,auto
terminal_output gfxterm
set color_normal=white/black
set color_highlight=black/white
set menu_color_normal=white/black
set menu_color_highlight=black/white
set timeout=-1
if [ "${{bourgeois_selected}}" = '{ids[0]}' -o "${{bourgeois_selected}}" = '{ids[1]}' ]; then
  set default=$bourgeois_selected
  set timeout=0
fi
else
menuentry 'Enter the selected door' --unrestricted --hotkey=' ' --id=bourgeois-enter-door {{
  set bourgeois_enter=true
  export bourgeois_enter
  configfile $prefix/bourgeois/scene.cfg
  set bourgeois_enter=false
}}
''')
    for door, key, identifier in zip(('linux', 'windows'), ('l', 'w'), ids):
        output.append(f'''menuentry 'Select {door.title()}' --unrestricted --hotkey={key} --id=bourgeois-select-{door} {{
  set bourgeois_selected='{identifier}'
  set theme={theme.removesuffix('.txt')}-{door}.txt
}}
''')
    output.append(f'''set bourgeois_selected='{ids[0]}'
export bourgeois_selected
set default=bourgeois-enter-door
set timeout_style=menu
set timeout=30
set fallback=
insmod all_video
insmod gfxterm
insmod png
loadfont unicode
set gfxmode=1280x720,1024x768,auto
serial --unit=0 --speed=115200
terminal_output serial
echo BOURGEOIS_SLIM_READY
terminal_output gfxterm
set theme={theme}
export theme
fi
''')
    return ''.join(output)


def hook(edition, linux_id, windows_id):
    for identifier in (linux_id, windows_id):
        safe_id(identifier)
    common = '''# bourgeois: keep one-shot and failed-boot paths technical.
if [ "${recordfail}" = "1" ]; then
  set timeout=-1
  set timeout_style=menu
elif [ "${boot_once}" != "true" ]; then
  set timeout=-1
  set timeout_style=menu
'''
    finish = '''if [ "${timeout}" != "0" ]; then
  unset theme
  terminal_output console
  insmod all_video
  insmod gfxterm
  loadfont unicode
  set gfxmode=1280x720,1024x768,auto
  terminal_output gfxterm
  set color_normal=white/black
  set color_highlight=black/white
  set menu_color_normal=white/black
  set menu_color_highlight=black/white
fi
'''
    if edition == 'slim':
        return common + '''  if [ -f $prefix/bourgeois/scene.cfg -a -f $prefix/bourgeois/courtyard-nameplates.png -a -f $prefix/bourgeois/theme.txt -a -f $prefix/bourgeois/theme-linux.txt -a -f $prefix/bourgeois/theme-windows.txt -a -f $prefix/bourgeois/traveler-idle-left.png -a -f $prefix/bourgeois/traveler-idle-right.png ]; then
    configfile $prefix/bourgeois/scene.cfg
  fi
fi
''' + finish
    if edition != 'fancy':
        raise ValueError('Unknown edition')
    return common + f'''  insmod all_video
  insmod png
  loadfont unicode
  set bourgeois_trace=1
  insmod bourgeois
  if [ "${{feature_bourgeois}}" = "1" ]; then
    bourgeois '{linux_id}' '{windows_id}' $prefix/bourgeois/courtyard-nameplates.png $prefix/bourgeois/traveler.png
  fi
fi
''' + finish
