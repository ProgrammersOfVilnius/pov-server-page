#!/usr/bin/python
"""
WSGI application that renders /root/Changelog
"""

import calendar
import datetime
import io
import os
import re
import socket
import textwrap
from functools import partial
from mimetypes import guess_type

try:
    from html import escape
except ImportError:
    from cgi import escape
try:
    from urllib.parse import parse_qs
except ImportError:
    from urlparse import parse_qs

import mako.template
import mako.lookup

from .utils import ansi2html, mako_error_handler


__author__ = 'Marius Gedminas <marius@gedmin.as>'
__version__ = '0.9.1'
__date__ = '2021-03-29'


HOSTNAME = socket.gethostname()
CHANGELOG_FILE = '/root/Changelog'
MOTD_FILE = '/etc/motd'

STATIC_ASSETS = os.path.join(os.path.dirname(__file__), 'static')
if not os.path.exists(STATIC_ASSETS):  # nocover: testing installed package
    STATIC_ASSETS = '/usr/share/pov-server-page/static'


#
# Data model
#

class TextObject(object):

    def __init__(self, text=None):
        self.text = [] if text is None else text

    def add_line(self, line):
        self.text.append(line)

    def pre(self, slice=slice(None), highlight=None):
        if not self.text:
            return ''
        excerpt = u''.join(linkify(line) for line in self.text[slice]).rstrip()
        if highlight:
            excerpt = highlight_text(highlight, excerpt)
        return u'<pre>%s</pre>' % excerpt

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
        r'(?: (?P<hour>\d\d):(?P<minute>\d\d))?(?: (?P<timezone>[-+]\d\d\d\d))?'
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

    @classmethod
    def parse(cls, line, id, text=None):
        m = cls._header_rx.match(line)
        if m is not None:
            return cls(id=id,
                       year=int(m.group('year')),
                       month=int(m.group('month')),
                       day=int(m.group('day')),
                       hour=int(m.group('hour')) if m.group('hour') else None,
                       minute=int(m.group('minute')) if m.group('minute') else None,
                       timezone=m.group('timezone'),
                       user=m.group('user'),
                       text=text)

    def search(self, query):
        return any(query in line.lower() for line in self.text)

    def date(self):
        return datetime.date(self.year, self.month, self.day)

    def timestamp(self):
        template = u'{year:04d}-{month:02d}-{day:02d}'
        if self.hour is not None:
            template += u' {hour:02d}:{minute:02d}'
        if self.timezone is not None:
            template += u' {timezone}'
        return template.format(
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
            title=escape(self.title()),
            text=self.pre(slice(1, None)), # skip self.text[0] because it's the header
        )


class ToDoItem(TextObject):

    _todo_rx = re.compile(r'^(?P<prefix>.*)- \[ ] (?P<title>.*)')

    def __init__(self, entry=None, prefix=None, title=None):
        TextObject.__init__(self)
        self.entry = entry
        self.prefix = prefix
        self.title = title

    @classmethod
    def parse(cls, line, entry):
        m = cls._todo_rx.match(line)
        if m is not None:
            return cls(entry=entry,
                       prefix=m.group('prefix'),
                       title=m.group('title'))

    def as_html(self):
        return (
            u'<li>{title} ({entry})</li>'
        ).format(
            title=escape(self.title.strip()),
            entry=escape(self.entry.title()),
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
            new_entry = Entry.parse(line, id=len(self.entries) + 1)
            if new_entry is not None:
                entry = new_entry
                self.entries.append(entry)
            entry.add_line(line)
            maybe_todo = ToDoItem.parse(line, entry=entry)
            if maybe_todo is not None:
                todo = maybe_todo
                todo.add_line(line)
                self.todo.append(todo)
            elif todo is not None:
                if line.startswith(todo.prefix + '  '):
                    todo.title += ' ' + line[len(todo.prefix) + 1:].strip()
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

    def __init__(self, filename=None, raw=''):
        self.raw = raw
        if filename:
            self.read(filename)

    def read(self, filename):
        self.raw = ''
        try:
            with io.open(filename, encoding='UTF-8', errors='replace') as fp:
                self.raw = fp.read()
        except IOError:
            pass

    def as_html(self):
        if self.raw:
            return u'<pre class="motd">%s</pre>' % ansi2html(self.raw.rstrip())
        else:
            return u''


LINK_RX = re.compile(r'(?P<url>https?://\S+[^.,)\s\]])|LP: #(?P<lp>\d+)')


def linkify(text):
    def _replace(match):
        g = match.groupdict()
        g['text'] = match.group(0)
        if g['url']:
            return u'<a href="{url}">{url}</a>'.format(**g)
        elif g['lp']:
            return u'<a href="https://pad.lv/{lp}">{text}</a>'.format(**g)
        else: # nocover:
            return g['text']
    return LINK_RX.sub(_replace, escape(text, True))


def highlight_text(what, text):
    what = escape(what, True)
    return re.sub(
        '(<[^>]*>)|(%s)' % re.escape(what),
        lambda m: m.group(1) or u'<mark>{}</mark>'.format(m.group(2)),
        text,
        flags=re.IGNORECASE)


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


def get_motd_filename(environ):
    return environ.get('MOTD_FILE') or os.getenv('MOTD_FILE') or MOTD_FILE


def get_motd(filename):
    # This is the place to add a cache, if one seems needed
    return Motd(filename)


#
# And now let's invent our own web microframework
# (because we were minimizing dependencies to those packages available in
# Ubuntu 10.04 for reasons; now it's fine to target 12.04 so maybe I can
# use python-flask or something)
#

class Response(object):

    def __init__(self, body='', content_type='text/html; charset=UTF-8',
                 status='200 OK', headers={}):
        self.body = body
        self.status = status
        self.headers = {'Content-Type': content_type}
        self.headers.update(headers)


PATHS = []


def path(pattern, **kwargs):
    def wrapper(fn):
        PATHS.append((pattern, re.compile('^(?:%s)/?$' % pattern), fn, kwargs))
        return fn
    return wrapper


def not_found(environ):
    return Response('<h1>404 Not Found</h1>', status='404 Not Found')


def dispatch(environ):
    path_info = environ['PATH_INFO'] or '/'
    for pattern, rx, view, kwargs in PATHS:
        m = rx.match(path_info)
        if m:
            return partial(view, environ, *m.groups(), **kwargs)
    return partial(not_found, environ)


def get_prefix(environ):
    script_name = environ['SCRIPT_NAME']
    return script_name.rstrip('/')


TEMPLATES = mako.lookup.TemplateLookup()


def Template(*args, **kw):
    template = mako.template.Template(
        error_handler=mako_error_handler,
        strict_undefined=True,
        default_filters=['unicode', 'h'],
        lookup=TEMPLATES,
        *args, **kw)
    TEMPLATES.put_template(template.uri, template)
    return template


#
# Views
#


page_template = Template(uri="page.html", text=textwrap.dedent('''
    <!DOCTYPE html>
    <html lang="en">
      <head>
        <meta charset="UTF-8">
        <meta http-equiv="X-UA-Compatible" content="IE=edge">
        <meta name="viewport" content="width=device-width, initial-scale=1">

        <title>${self.title()}</title>

        <link rel="stylesheet" href="/static/css/bootstrap.min.css">
        <link rel="stylesheet" href="/static/css/style.css">
        <link rel="stylesheet" href="${prefix}/style.css">
      </head>
      <body>
        ${self.body()}
      </body>
    </html>

    <%def name="searchbox(query=None, autofocus=False)">
        <div class="searchbox hidden-print">
          <form action="${prefix}/search" method="get" class="form-inline">
            <input type="text" name="q" aria-label="Search" class="form-control" accesskey="s"\\
    % if query:
     value="${query}"\\
    % endif
    % if autofocus:
     autofocus\\
    % endif
    >
            <button type="submit" class="btn btn-primary">Search</button>
          </form>
        </div>
    </%def>
'''))


STYLESHEET = textwrap.dedent('''
    body {
        margin: 1em;
    }

    h1 > a {
        text-decoration: none;
        color: black;
    }

    h3 {
        padding: 10px;
        margin: 10px -10px 0px -10px;
    }
    h3:target {
        background: #ffe;
    }

    @media (min-width: 768px) {
        .searchbox {
            position: absolute;
            top: 1em;
            right: 1em;
        }
        .searchbox input {
            margin-right: 10px;
        }
    }
    @media (max-width: 767px) {
        .searchbox {
            text-align: right;
            margin-top: 20px;
            margin-bottom: 20px;
        }
        .searchbox input, .searchbox button {
            display: inline-block;
            width: auto;
            vertical-align: middle;
        }
        .searchbox input {
            margin-right: 10px;
        }
    }

    .simple-navbar strong {
        padding: 0 4px;
    }

    a.permalink {
        margin-left: 8px;
        color: transparent;
        text-decoration: none;
    }
    h3:hover > a.permalink {
        color: #337ab7;
    }
    a.permalink:hover, a.permalink:active {
        color: #23527c !important;
    }

    .calendar {
        float: right;
        padding: 1em;
        margin-top: -1ex;
        margin-left: 1ex;
        background: #ececec;
        border-collapse: separate;
    }
    .calendar th {
        padding-bottom: 1ex;
        text-align: center;
    }
    .calendar td {
        width: 2.75ex;
        text-align: right;
    }

    pre {
        border: none;
        background: inherit;
    }
    pre + pre {
        margin-top: -10px;
    }
'''.lstrip('\n'))


@path('/style.css')
def stylesheet(environ):
    return Response(STYLESHEET, content_type='text/css')


@path('/static/(.*)')
def static(environ, pathname):
    if '_ALLOW_STATIC_FILES' not in environ:
        return not_found(environ)
    pathname = os.path.normpath(pathname)
    if '..' in pathname or pathname.startswith('/'):
        return not_found(environ)
    pathname = os.path.join(STATIC_ASSETS, pathname)
    content_type = guess_type(pathname)[0] or 'application/octet-stream'
    with open(pathname, 'rb') as f:
        return Response(f.read(), content_type=content_type)


main_template = Template(uri="main.html", text=textwrap.dedent('''
    <%inherit file="page.html" />
    <%def name="title()">/root/Changelog on ${hostname}</%def>

        <h1>${self.title()}</h1>

        ${self.searchbox(autofocus=True)}

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
'''))


@path('/')
def main_page(environ):
    prefix = get_prefix(environ)
    hostname = get_hostname(environ)
    try:
        changelog = get_changelog(get_changelog_filename(environ))
    except OSError:
        # It would be nice to distinguish ENOENT from other errors like EPERM
        return not_found(environ)
    motd = get_motd(get_motd_filename(environ))
    return main_template.render_unicode(
        hostname=hostname, motd=motd, changelog=changelog, prefix=prefix)


@path('/raw', content_disposition='inline')
@path('/download', content_disposition='attachment')
def raw_page(environ, content_disposition='inline'):
    filename = get_changelog_filename(environ)
    try:
        with open(filename, 'rb') as f:
            raw = f.read()
    except IOError:
        return not_found(environ)
    hostname = get_hostname(environ)
    outfilename = 'Changelog.{hostname}'.format(hostname=hostname)
    headers = {
        'Content-Disposition': '{disposition}; filename="{outfilename}"'.format(
            disposition=content_disposition,
            outfilename=outfilename,
        ),
    }
    return Response(raw, content_type='text/plain; charset=UTF-8',
                    headers=headers)


all_template = Template(uri="all.html", text=textwrap.dedent('''
    <%inherit file="page.html" />
    <%def name="title()">All entries - /root/Changelog on ${hostname}</%def>

        <h1><a href="${prefix}/">/root/Changelog on ${hostname}</a></h1>

        ${self.searchbox()}

        ${changelog.preamble.as_html()|n}

    % if not changelog.entries:
    <p>The changelog is empty.</p>
    % else:
    %     for entry in changelog.entries:
    <h3><a href="${entry.url(prefix)}">${entry.title()}</a></h3>
        ${entry.pre(slice(1, None))|n}
    %     endfor
    % endif
'''))


@path(r'/all')
def all_page(environ):
    prefix = get_prefix(environ)
    hostname = get_hostname(environ)
    try:
        changelog = get_changelog(get_changelog_filename(environ))
    except OSError:
        return not_found(environ)
    return all_template.render_unicode(
        hostname=hostname, changelog=changelog, prefix=prefix)


year_template = Template(uri="year.html", text=textwrap.dedent('''
    <%inherit file="page.html" />
    <%def name="title()">${date} - /root/Changelog on ${hostname}</%def>

        <h1><a href="${prefix}/">/root/Changelog on ${hostname}</a></h1>

        ${self.searchbox()}

        ${calendar|n}

    <%def name="navbar()">
        <div class="simple-navbar">
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
'''))


@path(r'/(\d\d\d\d)')
def year_page(environ, year):
    prefix = get_prefix(environ)
    hostname = get_hostname(environ)
    try:
        changelog = get_changelog(get_changelog_filename(environ))
    except OSError:
        return not_found(environ)
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


month_template = Template(uri="month.html", text=textwrap.dedent('''
    <%inherit file="page.html" />
    <%def name="title()">${date} - /root/Changelog on ${hostname}</%def>

        <h1><a href="${prefix}/">/root/Changelog on ${hostname}</a></h1>

        ${self.searchbox()}

        ${calendar|n}

    <%def name="navbar()">
        <div class="simple-navbar">
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
'''))


@path(r'/(\d\d\d\d)/(\d\d)')
def month_page(environ, year, month):
    prefix = get_prefix(environ)
    hostname = get_hostname(environ)
    try:
        changelog = get_changelog(get_changelog_filename(environ))
    except OSError:
        return not_found(environ)
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
    <%inherit file="page.html" />
    <%def name="title()">${date} - /root/Changelog on ${hostname}</%def>

        <h1><a href="${prefix}/">/root/Changelog on ${hostname}</a></h1>

        ${self.searchbox()}

        ${calendar|n}

    <%def name="navbar()">
        <div class="simple-navbar">
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
'''))


@path(r'/(\d\d\d\d)/(\d\d)/(\d\d)')
def day_page(environ, year, month, day):
    prefix = get_prefix(environ)
    try:
        date = datetime.date(int(year), int(month), int(day))
    except ValueError:
        return not_found(environ)
    hostname = get_hostname(environ)
    try:
        changelog = get_changelog(get_changelog_filename(environ))
    except OSError:
        return not_found(environ)
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
    <%inherit file="page.html" />
    <%def name="title()">${query} - /root/Changelog on ${hostname}</%def>

        <h1><a href="${prefix}/">/root/Changelog on ${hostname}</a></h1>

        ${self.searchbox(query=query)}

        <p>${len(entries)} results for '${query}'</h2>

    % for entry in entries:
        <h3><a href="${entry.url(prefix)}">${entry.title()}</a></h3>
        ${entry.pre(slice(1, None), highlight=query)|n}
    % endfor
'''))


@path(r'/search')
def search_page(environ):
    prefix = get_prefix(environ)
    form = parse_qs(environ.get('QUERY_STRING', ''))
    query = form.get('q', [''])[0]
    # NB: python 2 gives us str (aka bytes) with UTF-8 in it;
    # python 3 gives us str with decoded unicode characters in it
    if isinstance(query, bytes):  # pragma: PY2
        query = query.decode('UTF-8')
    hostname = get_hostname(environ)
    try:
        changelog = get_changelog(get_changelog_filename(environ))
    except OSError:
        return not_found(environ)
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
    from . import changelog2html
    reload(changelog2html)
    environ['_ALLOW_STATIC_FILES'] = True
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
