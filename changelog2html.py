#!/usr/bin/python
"""
WSGI application that renders /root/Changelog
"""

import calendar
import cgi
import datetime
import io
import linecache
import os
import re
import socket
import sys
import textwrap
from functools import partial

import mako.template
import mako.exceptions


__author__ = 'Marius Gedminas <marius@gedmin.as>'
__version__ = '0.6.1'


HOSTNAME = socket.gethostname()
CHANGELOG_FILE = '/root/Changelog'
MOTD_FILE = '/etc/motd'


#
# Data model
#

class TextObject(object):

    def __init__(self, text=None):
        self.text = [] if text is None else text

    def add_line(self, line):
        self.text.append(line)

    def pre(self, slice=slice(None)):
        if not self.text:
            return ''
        return u'<pre>%s</pre>' % (
            u''.join(cgi.escape(line) for line in self.text[slice]).rstrip())

    def as_html(self):
        return self.pre()


class Preamble(TextObject):
    id = 0

    def title(self):
        return u'Preamble'

    def url(self, prefix):
        return prefix + '/'


class Entry(TextObject):

    _header_rx = re.compile(
        r'^(?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)'
        r' (?P<hour>\d\d):(?P<minute>\d\d)(?: (?P<timezone>[-+]\d\d\d\d))?'
        r'(?:: (?P<user>.*))?$')

    def __init__(self, id, year, month, day, hour, minute, timezone, user,
                 text=None):
        TextObject.__init__(self, text=text)
        self.id = id
        self.year = year
        self.month = month
        self.day = day
        self.hour = hour
        self.minute = minute
        self.timezone = timezone
        self.user = user

    def search(self, query):
        return any(query in line.lower() for line in self.text)

    def date(self):
        return datetime.date(self.year, self.month, self.day)

    def timestamp(self):
        return u'{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d} {timezone}'.format(
                year=self.year, month=self.month, day=self.day,
                hour=self.hour, minute=self.minute, timezone=self.timezone)

    def title(self):
        return u'{timestamp} {user}'.format(timestamp=self.timestamp(), user=self.user)

    def url(self, prefix):
        return u'{prefix}/{year:04d}/{month:02d}/{day:02d}/{target}'.format(
            prefix=prefix, year=self.year, month=self.month, day=self.day,
            target=self.target)

    @property
    def anchor(self):
        return u'e{id}'.format(id=self.id)

    @property
    def target(self):
        return u'#{anchor}'.format(anchor=self.anchor)

    def as_html(self):
        return (
            u'<h3>{title}</h3>\n'
            u'{text}'
        ).format(
            title=cgi.escape(self.title()),
            text=self.pre(slice(1, None)), # skip self.text[0] because it's the header
        )


class ToDoItem(TextObject):

    _todo_rx = re.compile('^(?P<prefix>.*)- \[ ] (?P<title>.*)')

    def __init__(self, entry=None, prefix=None, title=None):
        TextObject.__init__(self)
        self.entry = entry
        self.prefix = prefix
        self.title = title

    def as_html(self):
        return (
            u'<li>{title} ({entry})</li>'
        ).format(
            title=cgi.escape(self.title.strip()),
            entry=cgi.escape(self.entry.title()),
        )


class Changelog(object):

    def __init__(self, filename=None):
        self.preamble = Preamble()
        self.entries = []
        self.todo = []
        self.mtime = None
        self.date_index = {}
        if filename:
            self.read(filename)

    def filter(self, year=None, month=None, day=None):
        return [e for e in self.entries
                if (not year or e.year == year) and
                   (not month or e.month == month) and
                   (not day or e.day == day)]

    def search(self, query):
        query = query.lower()
        return [entry for entry in reversed(self.entries)
                if entry.search(query)]

    def read(self, filename):
        with io.open(filename, encoding='UTF-8', errors='replace') as fp:
            self.mtime = os.fstat(fp.fileno()).st_mtime
            self.parse(fp)

    def parse(self, fp):
        entry = self.preamble
        todo = None
        for line in fp:
            m = Entry._header_rx.match(line)
            if m is not None:
                entry = Entry(id=len(self.entries) + 1,
                              year=int(m.group('year')),
                              month=int(m.group('month')),
                              day=int(m.group('day')),
                              hour=int(m.group('hour')),
                              minute=int(m.group('minute')),
                              timezone=m.group('timezone'),
                              user=m.group('user'))
                self.entries.append(entry)
            entry.add_line(line)
            m = ToDoItem._todo_rx.match(line)
            if m is not None:
                todo = ToDoItem(entry=entry,
                                prefix=m.group('prefix'),
                                title=m.group('title'))
                todo.add_line(line)
                self.todo.append(todo)
            elif todo is not None:
                if line.startswith(todo.prefix + '  '):
                    todo.title += line[len(todo.prefix) + 1:]
                    todo.add_line(line)
                else:
                    todo = None
        self.build_index()

    def build_index(self):
        self.date_index = {}
        for e in self.entries:
            self.date_index.setdefault(e.date(), []).append(e)

    def entries_for_date(self, date):
        return self.date_index.get(date, [])

    def prev_date(self, date):
        try:
            return max((d for d in self.date_index if d < date))
        except ValueError:
            return None

    def next_date(self, date):
        try:
            return min((d for d in self.date_index if d > date))
        except ValueError:
            return None


class Motd(object):

    def __init__(self, filename=None):
        self.raw = ''
        if filename:
            self.read(filename)

    def read(self, filename):
        self.raw = ''
        try:
            with io.open(filename, encoding='UTF-8', errors='replace') as fp:
                self.raw = fp.read()
        except IOError:
            pass
        self.text = strip_ansi(self.raw)

    def as_html(self):
        if self.raw:
            return u'<pre class="motd">%s</pre>' % ansi2html(self.raw)
        else:
            return u''


# CSI: starts with ESC [, followed optionally by a ?, followed by up to 16
# decimal parameters separated by semicolons, followed by a single character
# (usually a lowercase or uppercase letter, but could be @ or `).
ANSI_RX = re.compile(r'(\033\[\??(?:\d+(?:;\d+)*)?.)')


def strip_ansi(text):
    return ANSI_RX.sub('', text)


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
    for r in [0] + list(range(55, 255, 40))
    for g in [0] + list(range(55, 255, 40))
    for b in [0] + list(range(55, 255, 40))
] + [
    # 24 greyscale levels
    '#%02x%02x%02x' % (l, l, l)
    for l in range(8, 248, 10)
]


def ansi2html(text):
    parts = []
    pending = []

    def fg(color_index):
        parts.extend(pending)
        parts.append(u'<span style="color: %s">' % COLORS[color_index])
        pending[:] = u'</span>'

    for bit in re.split(ANSI_RX, cgi.escape(text)):
        if not bit.startswith(u'\033'):
            parts.append(bit)
        elif bit.endswith(u'm'):
            try:
                numbers = [int(n) for n in bit.strip(u'\033[?m').split(';') if n]
            except ValueError:
                continue
            # this handles just a subset of the allowed color sequences; e.g.
            # it would ignore ESC [ 35;48 m which tries to set fg and bg colors
            # in one go
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
    return u''.join(parts)


#
# Environment
#

def get_changelog(filename, _cache={}):
    changelog = _cache.get(filename)
    mtime = os.stat(filename).st_mtime
    if changelog is None or mtime != changelog.mtime:
        changelog = _cache[filename] = Changelog(filename)
    return changelog


def get_hostname(environ):
    return environ.get('HOSTNAME') or os.getenv('HOSTNAME') or HOSTNAME


def get_changelog_filename(environ):
    return environ.get('CHANGELOG_FILE') or os.getenv('CHANGELOG_FILE') or CHANGELOG_FILE


def get_motd(environ):
    filename = environ.get('MOTD_FILE') or os.getenv('MOTD_FILE') or MOTD_FILE
    return Motd(filename)


#
# And now let's invent our own web microframework
# (because we're minimizing dependencies to those packages available in
# Ubuntu 10.04 for reasons)
#

class Response(object):

    def __init__(self, body='', content_type='text/html; charset=UTF-8',
                 status='200 OK', headers={}):
        self.body = body
        self.status = status
        self.headers = {'Content-Type': content_type}
        self.headers.update(headers)


PATHS = []


def path(pattern):
    def wrapper(fn):
        PATHS.append((pattern, re.compile('^(?:%s)/?$' % pattern), fn))
        return fn
    return wrapper


def not_found(environ):
    return Response('<h1>404 Not Found</h1>', status='404 Not Found')


def dispatch(environ):
    path_info = environ['PATH_INFO'] or '/'
    for pattern, rx, view in PATHS:
        m = rx.match(path_info)
        if m:
            return partial(view, environ, *m.groups())
    return partial(not_found, environ)


def get_prefix(environ):
    script_name = environ['SCRIPT_NAME']
    return script_name.rstrip('/')


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
        if filename.startswith('memory:'):
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


def Template(*args, **kw):
    return mako.template.Template(error_handler=mako_error_handler,
                                  default_filters=['unicode', 'h'],
                                  *args, **kw)


#
# Views
#


STYLESHEET = textwrap.dedent('''
    body {
        margin: 1em;
    }

    h1 > a {
        text-decoration: none;
        color: black;
    }

    h3:target {
        background: #ffe;
    }

    .searchbox {
        position: absolute;
        top: 1em;
        right: 1em;
    }

    .navbar strong {
        padding: 0 4px;
    }

    a.permalink {
        padding: 0 4px;
        color: white;
        text-decoration: none;
    }
    h3:hover > a.permalink {
        color: #ccc;
    }
    a.permalink:hover, a.permalink:active {
        color: white !important;
        background: #ccc;
    }

    .calendar {
        float: right;
        padding: 1em;
        margin-top: -1ex;
        background: #ececec;
    }
    .calendar th {
        padding-bottom: 1ex;
    }
    .calendar td {
        width: 2.75ex;
        text-align: right;
    }
''')


@path('/style.css')
def stylesheet(environ):
    return Response(STYLESHEET, content_type='text/css')


main_template = Template(textwrap.dedent('''
    <html>
      <head>
        <title>/root/Changelog on ${hostname}</title>
        <link rel="stylesheet" href="${prefix}/style.css" />
      </head>
      <body>
        <h1>/root/Changelog on ${hostname}</h1>

        <div class="searchbox">
          <form action="${prefix}/search" method="get">
            <input type="text" name="q" class="searchtext" autofocus accesskey="s" />
            <input type="submit" value="Search" class="searchbutton" />
          </form>
        </div>

        ${motd.as_html()|n}

        ${changelog.preamble.as_html()|n}

    % if changelog.todo:
        <h2>To do list</h2>

        <ul class="todo">
    <% todos = sorted(changelog.todo, reverse=True, key=lambda i: i.entry.id) %>
    %     for item in todos:
          <li><a href="${item.entry.url(prefix)}">${item.title}</a></li>
    %     endfor
        </ul>
    % endif

    % if not changelog.entries:
        <p>The changelog is empty.</p>
    % else:
    <% n = 5 %>
        <h2>Latest entries</h2>

    %     for entry in changelog.entries[:-n:-1]:
        <h3><a href="${entry.url(prefix)}">${entry.title()}</a></h3>
        ${entry.pre(slice(1, None))|n}
    %     endfor

    %     if len(changelog.entries) > n:
        <a href="${changelog.entries[-n].url(prefix)}">
        (${len(changelog.entries) - n} older changelog entries are present)
        </a>
    %     endif
    % endif
      </body>
    </html>
'''))


@path('/')
def main_page(environ):
    prefix = get_prefix(environ)
    hostname = get_hostname(environ)
    changelog = get_changelog(get_changelog_filename(environ))
    motd = get_motd(environ)
    return main_template.render_unicode(
        hostname=hostname, motd=motd, changelog=changelog, prefix=prefix)


all_template = Template(textwrap.dedent('''
    <html>
      <head>
        <title>All entries - /root/Changelog on ${hostname}</title>
        <link rel="stylesheet" href="${prefix}/style.css" />
      </head>
      <body>
        <h1><a href="${prefix}/">/root/Changelog on ${hostname}</a></h1>

        <div class="searchbox">
          <form action="${prefix}/search" method="get">
            <input type="text" name="q" class="searchtext" accesskey="s" />
            <input type="submit" value="Search" class="searchbutton" />
          </form>
        </div>

        ${changelog.preamble.as_html()|n}

    % if not changelog.entries:
    <p>The changelog is empty.</p>
    % else:
    %     for entry in changelog.entries:
    <h3><a href="${entry.url(prefix)}">${entry.title()}</a></h3>
        ${entry.pre(slice(1, None))|n}
    %     endfor
    % endif
      </body>
    </html>
'''))


@path(r'/all')
def all_page(environ):
    prefix = get_prefix(environ)
    hostname = get_hostname(environ)
    changelog = get_changelog(get_changelog_filename(environ))
    return all_template.render_unicode(
        hostname=hostname, changelog=changelog, prefix=prefix)


year_template = Template(textwrap.dedent('''
    <html>
      <head>
        <title>${date} - /root/Changelog on ${hostname}</title>
        <link rel="stylesheet" href="${prefix}/style.css" />
      </head>
      <body>
        <h1><a href="${prefix}/">/root/Changelog on ${hostname}</a></h1>

        <div class="searchbox">
          <form action="${prefix}/search" method="get">
            <input type="text" name="q" class="searchtext" accesskey="s" />
            <input type="submit" value="Search" class="searchbutton" />
          </form>
        </div>

        ${calendar|n}

    <%def name="navbar()">
        <div class="navbar">
    % if prev_url:
          <a href="${prev_url}">&laquo; ${prev_date}</a>
    % endif
          <strong>${date}</strong>
    % if next_url:
          <a href="${next_url}">${next_date} &raquo;</a>
    % endif
        </div>
    </%def>
        ${navbar()}

    % if not entries:
        <p>No entries for this year.</p>
    % else:

    %     for entry in entries:
    <h3><a href="${entry.url(prefix)}">${entry.title()}</a></h3>
        ${entry.pre(slice(1, None))|n}
    %     endfor
    % endif

        ${navbar()}
      </body>
    </html>
'''))


@path(r'/(\d\d\d\d)')
def year_page(environ, year):
    prefix = get_prefix(environ)
    hostname = get_hostname(environ)
    changelog = get_changelog(get_changelog_filename(environ))
    entries = changelog.filter(year=int(year))
    year_1st = datetime.date(int(year), 1, 1)
    year_last = datetime.date(int(year), 12, 31)
    prev_date = changelog.prev_date(year_1st)
    next_date = changelog.next_date(year_last)
    prev_url = prev_date and (prefix + prev_date.strftime('/%Y'))
    next_url = next_date and (prefix + next_date.strftime('/%Y'))
    calendar = year_calendar(
        changelog, int(year), prefix,
        prev_url=prev_url, next_url=next_url,
        url=lambda e: '{prefix}/{year:04}/{month:02}'.format(
            prefix=prefix, year=e.year, month=e.month))
    return year_template.render_unicode(
        hostname=hostname, date=str(year), entries=entries,
        prev_url=prev_url,
        prev_date=prev_date and prev_date.strftime('%Y'),
        next_url=next_url,
        next_date=next_date and next_date.strftime('%Y'),
        calendar=calendar,
        prefix=prefix)


def year_calendar(changelog, year, prefix, url, prev_url=None, next_url=None):
    header = year_header(year, prefix, prev_url=prev_url, next_url=next_url)
    matrix = [range(1, 7), range(7, 13)]
    return html_table([[month_link(changelog, year, month, url)
                        for month in row] for row in matrix],
                      'calendar', header=header)


def month_link(changelog, year, month, url):
    if not month:
        return ''
    entries = changelog.filter(year=year, month=month)
    if not entries:
        return str(month)
    else:
        return '<a href="%s">%d</a>' % (url(entries[0]), month)


def year_header(year, prefix, prev_url=None, next_url=None):
    title = '<a href="{prefix}/{year:04}">{year:04}</a>'.format(
        year=year, prefix=prefix)
    prev = '<a href="{}">&laquo;</a>'.format(prev_url) if prev_url else ''
    next = '<a href="{}">&raquo;</a>'.format(next_url) if next_url else ''
    return ('<thead>'
            '<tr>'
            '<th>{prev}</th>'
            '<th colspan="4">{title}</th>'
            '<th>{next}</th>'
            '</tr>'
            '</thead>'.format(prev=prev, next=next, title=title))


month_template = Template(textwrap.dedent('''
    <html>
      <head>
        <title>${date} - /root/Changelog on ${hostname}</title>
        <link rel="stylesheet" href="${prefix}/style.css" />
      </head>
      <body>
        <h1><a href="${prefix}/">/root/Changelog on ${hostname}</a></h1>

        <div class="searchbox">
          <form action="${prefix}/search" method="get">
            <input type="text" name="q" class="searchtext" accesskey="s" />
            <input type="submit" value="Search" class="searchbutton" />
          </form>
        </div>

        ${calendar|n}

    <%def name="navbar()">
        <div class="navbar">
    % if prev_url:
          <a href="${prev_url}">&laquo; ${prev_date}</a>
    % endif
          <strong>${date}</strong>
    % if next_url:
          <a href="${next_url}">${next_date} &raquo;</a>
    % endif
        </div>
    </%def>
        ${navbar()}

    % if not entries:
        <p>No entries for this month.</p>
    % else:

    %     for entry in entries:
    <h3 id="${entry.anchor}"><a href="${entry.url(prefix)}">${entry.title()}</a></h3>
        ${entry.pre(slice(1, None))|n}
    %     endfor
    % endif

        ${navbar()}
      </body>
    </html>
'''))


@path(r'/(\d\d\d\d)/(\d\d)')
def month_page(environ, year, month):
    prefix = get_prefix(environ)
    hostname = get_hostname(environ)
    changelog = get_changelog(get_changelog_filename(environ))
    entries = changelog.filter(year=int(year), month=int(month))
    month_1st = datetime.date(int(year), int(month), 1)
    month_last = (month_1st + datetime.timedelta(31)).replace(day=1) - datetime.timedelta(1)
    prev_date = changelog.prev_date(month_1st)
    prev_url = prev_date and (prefix + prev_date.strftime('/%Y/%m'))
    next_date = changelog.next_date(month_last)
    next_url = next_date and (prefix + next_date.strftime('/%Y/%m'))
    calendar = month_calendar(changelog, int(year), int(month), prefix,
                              prev_url=prev_url, next_url=next_url,
                              url=lambda e: e.target)
    return month_template.render_unicode(
        hostname=hostname, date='%s-%s' % (year, month), entries=entries,
        prev_url=prev_url,
        prev_date=prev_date and prev_date.strftime('%Y-%m'),
        next_url=next_url,
        next_date=next_date and next_date.strftime('%Y-%m'),
        calendar=calendar,
        prefix=prefix)


def month_calendar(changelog, year, month, prefix, url, prev_url=None,
                   next_url=None):
    header = month_header(year, month, prefix, prev_url=prev_url,
                          next_url=next_url)
    matrix = calendar.monthcalendar(year, month)
    return html_table([[day_link(changelog, year, month, day, url)
                        for day in row]
                       for row in matrix], 'calendar',
                      header=header)


def day_link(changelog, year, month, day, url):
    if not day:
        return ''
    entries = changelog.filter(year=year, month=month, day=day)
    if not entries:
        return str(day)
    else:
        return '<a href="%s">%d</a>' % (url(entries[0]), day)


def month_header(year, month, prefix, prev_url=None, next_url=None):
    title = (
        '<a href="{prefix}/{year:04}">{year:04}</a>-'
        '<a href="{prefix}/{year:04}/{month:02}">{month:02}</a>'.format(
            year=year, month=month, prefix=prefix))
    prev = '<a href="{}">&laquo;</a>'.format(prev_url) if prev_url else ''
    next = '<a href="{}">&raquo;</a>'.format(next_url) if next_url else ''
    return ('<thead>'
            '<tr>'
            '<th>{prev}</th>'
            '<th colspan="5">{title}</th>'
            '<th>{next}</th>'
            '</tr>'
            '</thead>'.format(prev=prev, next=next, title=title))


def html_table(matrix, css_class, header=''):
    return '<table class="%s">%s<tbody>%s</tbody></table>' % (
        css_class,
        header,
        ''.join(['<tr>%s</tr>' % ''.join(['<td>%s</td>' % cell for cell in row])
                 for row in matrix]))


day_template = Template(textwrap.dedent('''
    <html>
      <head>
        <title>${date} - /root/Changelog on ${hostname}</title>
        <link rel="stylesheet" href="${prefix}/style.css" />
      </head>
      <body>
        <h1><a href="${prefix}/">/root/Changelog on ${hostname}</a></h1>

        <div class="searchbox">
          <form action="${prefix}/search" method="get">
            <input type="text" name="q" class="searchtext" accesskey="s" />
            <input type="submit" value="Search" class="searchbutton" />
          </form>
        </div>

        ${calendar|n}

    <%def name="navbar()">
        <div class="navbar">
    % if prev_url:
          <a href="${prev_url}">&laquo; ${prev_date}</a>
    % endif
          <strong>${date}</strong>
    % if next_url:
          <a href="${next_url}">${next_date} &raquo;</a>
    % endif
        </div>
    </%def>
        ${navbar()}

    % if not entries:
        <p>No entries for this date.</p>
    % else:

    %     for entry in entries:
        <h3 id="${entry.anchor}">${entry.title()} <a class="permalink" href="${entry.url(prefix)}">&para;</a></h3>
        ${entry.pre(slice(1, None))|n}
    %     endfor
    % endif

        ${navbar()}
      </body>
    </html>
'''))


@path(r'/(\d\d\d\d)/(\d\d)/(\d\d)')
def day_page(environ, year, month, day):
    prefix = get_prefix(environ)
    try:
        date = datetime.date(int(year), int(month), int(day))
    except ValueError:
        return not_found(environ)
    hostname = get_hostname(environ)
    changelog = get_changelog(get_changelog_filename(environ))
    entries = changelog.entries_for_date(date)
    prev_date = changelog.prev_date(date)
    next_date = changelog.next_date(date)
    calendar = month_calendar(changelog, int(year), int(month), prefix,
                              url=lambda e: e.target)
    return day_template.render_unicode(
        date=str(date), hostname=hostname, entries=entries,
        prev_url=prev_date and (prefix + prev_date.strftime('/%Y/%m/%d')),
        prev_date=str(prev_date),
        next_url=next_date and (prefix + next_date.strftime('/%Y/%m/%d')),
        next_date=str(next_date),
        calendar=calendar,
        prefix=prefix)


search_template = Template(textwrap.dedent('''
    <html>
      <head>
        <title>${query} - /root/Changelog on ${hostname}</title>
        <link rel="stylesheet" href="${prefix}/style.css" />
      </head>
      <body>
        <h1><a href="${prefix}/">/root/Changelog on ${hostname}</a></h1>

        <div class="searchbox">
          <form action="${prefix}/search" method="get">
            <input type="text" name="q" class="searchtext" value="${query}" accesskey="s" />
            <input type="submit" value="Search" class="searchbutton" />
          </form>
        </div>

        <p>${len(entries)} results for '${query}'</h2>

    % for entry in entries:
        <h3><a href="${entry.url(prefix)}">${entry.title()}</a></h3>
        ${entry.pre(slice(1, None))|n}
    % endfor

      </body>
    </html>
'''))


@path(r'/search')
def search_page(environ):
    prefix = get_prefix(environ)
    form = cgi.parse_qs(environ.get('QUERY_STRING', ''))
    query = form.get('q', [''])[0]
    if isinstance(query, bytes):
        query = query.decode('UTF-8')
    hostname = get_hostname(environ)
    changelog = get_changelog(get_changelog_filename(environ))
    entries = list(changelog.search(query))
    return search_template.render_unicode(
        hostname=hostname, query=query, entries=entries, prefix=prefix)


def wsgi_app(environ, start_response):
    view = dispatch(environ)
    response = view()
    if not isinstance(response, Response):
        response = Response(response)
    start_response(response.status, sorted(response.headers.items()))
    body = response.body
    if not isinstance(body, bytes):
        body = body.encode('UTF-8')
    return [body]


application = wsgi_app  # for mod_wsgi


try:
    from importlib import reload
except ImportError:
    pass


def reloading_wsgi_app(environ, start_response):
    # Horrible hack that gives me a fast development loop: reload the code on
    # every request!
    import changelog2html
    reload(changelog2html)
    return changelog2html.wsgi_app(environ, start_response)


def main():
    import optparse
    from wsgiref.simple_server import make_server
    parser = optparse.OptionParser(
        'usage: %prog [options] [filename]',
        description="Launch web server showing /root/Changelog")
    parser.add_option('-p', '--port', type='int', default=8080)
    parser.add_option('--public', default=False,
                      help='accept non-localhost connections')
    parser.add_option('--name', help='override hostname in page title')
    opts, args = parser.parse_args()
    if opts.name:
        os.environ['HOSTNAME'] = opts.name
    if len(args) > 1:
        parser.error("too many arguments")
    if args:
        os.environ['CHANGELOG_FILE'] = args[0]
    host = '0.0.0.0' if opts.public else 'localhost'
    httpd = make_server(host, opts.port, reloading_wsgi_app)
    print("Serving on http://%s:%d" % (host, opts.port))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
