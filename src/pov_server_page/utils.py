import linecache
import re
import sys

try:
    from html import escape
except ImportError:
    from cgi import escape

import mako.exceptions
from markupsafe import Markup


#
# ANSI to HTML colorizer
#

# CSI: starts with ESC [, followed optionally by a ?, followed by up to 16
# decimal parameters separated by semicolons, followed by a single character
# (usually a lowercase or uppercase letter, but could be @ or `).
ANSI_RX = re.compile(r'(\033\[\??(?:\d+(?:[;:]\d+)*)?.)')


COLORS = [
    # Tango colors 0..15
    '#000000',
    '#cc0000',
    '#4d9a05',
    '#c3a000',
    '#3464a3',
    '#754f7b',
    '#05979a',
    '#d3d6cf',
    '#545652',
    '#ef2828',
    '#89e234',
    '#fbe84f',
    '#729ecf',
    '#ac7ea8',
    '#34e2e2',
    '#ededeb',
] + [
    # 6x6x6 color cube
    '#%02x%02x%02x' % (r, g, b)
    for r in [0] + list(range(95, 256, 40))
    for g in [0] + list(range(95, 256, 40))
    for b in [0] + list(range(95, 256, 40))
] + [
    # 24 greyscale levels
    '#%02x%02x%02x' % (i, i, i)
    for i in range(8, 248, 10)
]


def ansi2html(text):
    parts = []
    pending = []

    def fg(color_index):
        parts.extend(pending)
        parts.append(u'<span style="color: %s">' % COLORS[color_index])
        pending[:] = u'</span>'

    def fg_rgb(r, g, b):
        parts.extend(pending)
        parts.append(u'<span style="color: #%02x%02x%02x">' % (r, g, b))
        pending[:] = u'</span>'

    for bit in re.split(ANSI_RX, escape(text)):
        if not bit.startswith(u'\033'):
            parts.append(bit)
        elif bit.endswith(u'm'):
            numbers = [int(n) for n in bit.strip(u'\033[?m').replace(':', ';').split(';') if n]
            # this handles just a subset of the allowed color sequences; e.g.
            # it would ignore ESC [ 35;48 m which tries to set fg and bg colors
            # in one go
            if len(numbers) == 5 and numbers[:2] == [38, 2]:
                # 24-bit colors!
                fg_rgb(*numbers[2:])
            if len(numbers) == 3 and numbers[:2] == [38, 5] and 0 <= numbers[2] <= 255:
                # 256-color code for foreground
                fg(numbers[2])
            elif len(numbers) == 2 and numbers[0] == 1 and 30 <= numbers[1] <= 37:
                # bold foreground color
                fg(8 + numbers[1] - 30)
            elif len(numbers) == 2 and numbers[0] == 0 and 30 <= numbers[1] <= 37:
                # regular foreground color
                fg(numbers[1] - 30)
            elif len(numbers) == 1 and 90 <= numbers[0] <= 97:
                # high-intensity foreground color
                fg(8 + numbers[0] - 90)
            elif len(numbers) == 1 and 30 <= numbers[0] <= 37:
                # regular foreground color
                fg(numbers[0] - 30)
            elif numbers == [0] or not numbers:
                # reset
                parts.extend(pending)
                del pending[:]
    parts += pending
    return Markup(u''.join(parts))


#
# Pretty error messages
#

def mako_error_handler(context, error):
    """Decorate tracebacks when Mako errors happen.

    Evil hack: walk the traceback frames, find compiled Mako templates,
    stuff their (transformed) source into linecache.cache.

    https://gist.github.com/mgedmin/4269249
    """
    rich_tb = mako.exceptions.RichTraceback()
    rich_iter = iter(rich_tb.traceback)
    tb = sys.exc_info()[-1]
    source = {}
    annotated = set()
    while tb is not None:
        cur_rich = next(rich_iter)
        f = tb.tb_frame
        co = f.f_code
        filename = co.co_filename
        lineno = tb.tb_lineno
        if filename.startswith('memory:') or filename.endswith(('_html', '_in')):
            lines = source.get(filename)
            if lines is None:
                info = mako.template._get_module_info(filename)
                lines = source[filename] = info.module_source.splitlines(True)
                linecache.cache[filename] = (None, None, lines, filename)
            if (filename, lineno) not in annotated:
                annotated.add((filename, lineno))
                extra = '    # {0} line {1} in {2}:\n    # {3}'.format(*cur_rich)
                lines[lineno-1] += extra
        tb = tb.tb_next
    # Don't return False -- that will lose the actual Mako frame.  Instead
    # re-raise.
    raise


#
# Unicode conversion for Mako, because decode.utf8 is buggy in
# python-mako 0.9.1 from Ubuntu 14.04 LTS
#

try:
    # Python 2
    text_type = unicode
except NameError:
    # Python 3
    text_type = str


def to_unicode(s):
    if isinstance(s, text_type):
        return s
    if isinstance(s, bytes):
        return s.decode('UTF-8')
    return text_type(s)
