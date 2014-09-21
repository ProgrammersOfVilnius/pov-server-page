#!/usr/bin/python
"""
WSGI application that renders /root/Changelog
"""

import re
import os
import textwrap
import socket
import cgi
import sys
import linecache
import datetime
from functools import partial

import mako.template
import mako.exceptions


__author__ = 'Marius Gedminas <marius@gedmin.as>'
__version__ = '0.2'


HOSTNAME = socket.gethostname()
CHANGELOG_FILE = '/root/Changelog'


#
# Data model
#

class TextObject(object):

    def __init__(self):
        self.text = []

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


class Entry(TextObject):

    def __init__(self, id, year, month, day, hour, minute, timezone, user):
        TextObject.__init__(self)
        self.id = id
        self.year = year
        self.month = month
        self.day = day
        self.hour = hour
        self.minute = minute
        self.timezone = timezone
        self.user = user

    def search(self, query):
        return any(query in line for line in self.text)

    def date(self):
        return datetime.date(self.year, self.month, self.day)

    def timestamp(self):
        return u'{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d} {timezone}'.format(
                year=self.year, month=self.month, day=self.day,
                hour=self.hour, minute=self.minute, timezone=self.timezone)

    def title(self):
        return u'{timestamp} {user}'.format(timestamp=self.timestamp(), user=self.user)

    def url(self):
        return u'/{year:04d}/{month:02d}/{day:02d}/#e{id}'.format(
            year=self.year, month=self.month, day=self.day, id=self.id)

    def as_html(self):
        return (
            u'<h3>{title}</h3>\n'
            u'{text}'
        ).format(
            title=cgi.escape(self.title()),
            text=self.pre(slice(1, None)), # skip self.text[0] because it's the header
        )


class ToDoItem(TextObject):

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

    _entry_header = re.compile(
        r'^(?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)'
        r' (?P<hour>\d\d):(?P<minute>\d\d)(?: (?P<timezone>[-+]\d\d\d\d))?'
        r'(?:: (?P<user>.*))?$')
    _todo_item = re.compile('^(?P<prefix>.*)- \[ ] (?P<title>.*)')

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
        for entry in reversed(self.entries):
            if entry.search(query):
                yield entry

    def read(self, filename):
        with open(filename) as fp:
            self.mtime = os.fstat(fp.fileno()).st_mtime
            self.parse(fp)

    def parse(self, fp):
        entry = self.preamble
        todo = None
        for line in fp:
            line = line.decode('UTF-8', 'replace')
            m = self._entry_header.match(line)
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
            entry.text.append(line)
            m = self._todo_item.match(line)
            if m is not None:
                todo = ToDoItem(entry=entry,
                                prefix=m.group('prefix'),
                                title=m.group('title'))
                todo.text.append(line)
                self.todo.append(todo)
            elif todo is not None:
                if line.startswith(todo.prefix + '  '):
                    todo.title += line[len(todo.prefix) + 1:]
                    todo.text.append(line)
                else:
                    todo = None
        self.build_index()

    def build_index(self):
        self.date_index = {}
        for e in self.entries:
            self.date_index.setdefault(e.date(), []).append(e)

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


#
# Pretty error messages
#


def mako_error_handler(context, error):
    """Decorate tracebacks when Mako errors happen.

    Evil hack: walk the traceback frames, find compiled Mako templates,
    stuff their (transformed) source into linecache.cache.

    https://gist.github.com/mgedmin/4269249
    """
    rich_tb = mako.exceptions.RichTraceback(error)
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
                extra = '    # {} line {} in {}:\n    # {}'.format(*cur_rich)
                lines[lineno-1] += extra
        tb = tb.tb_next
    # Don't return False -- that will lose the actual Mako frame.  Instead
    # re-raise.
    raise


def Template(*args, **kw):
    return mako.template.Template(error_handler=mako_error_handler,
                                  *args, **kw)


#
# Views
#


STYLESHEET = textwrap.dedent('''
    h1 > a {
        text-decoration: none;
        color: black;
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
''')


@path('/style.css')
def stylesheet(environ):
    return Response(STYLESHEET, content_type='text/css')


main_template = Template(textwrap.dedent('''
    <html>
      <head>
        <title>/root/Changelog on ${hostname}</title>
        <link rel="stylesheet" href="/style.css" />
      </head>
      <body>
        <h1>/root/Changelog on ${hostname}</h1>

        <div class="searchbox">
          <form action="search" method="get">
            <input type="text" name="q" class="searchtext" autofocus accesskey="s" />
            <input type="submit" value="Search" class="searchbutton" />
          </form>
        </div>

        ${changelog.preamble.as_html()}

    % if changelog.todo:
        <h2>To do list</h2>

        <ul class="todo">
    <% todos = sorted(changelog.todo, reverse=True, key=lambda i: i.entry.id) %>
    %     for item in todos:
          <li><a href="${item.entry.url()}">${item.title}</a></li>
    %     endfor
        </ul>
    % endif

    % if not changelog.entries:
        <p>The changelog is empty.</p>
    % else:
    <% n = 5 %>
        <h2>Latest entries</h2>

    %     for entry in changelog.entries[:-n:-1]:
        <h3><a href="${entry.url()}">${entry.title()}</a></h3>
        ${entry.pre(slice(1, None))}
    %     endfor

    %     if len(changelog.entries) > n:
        <a href="${changelog.entries[-n].url()}">
        (${len(changelog.entries) - n} older changelog entries are present)
        </a>
    %     endif
    % endif
      </body>
    </html>
'''))


@path('/')
def main_page(environ):
    hostname = get_hostname(environ)
    changelog = get_changelog(get_changelog_filename(environ))
    return main_template.render(hostname=hostname, changelog=changelog)


year_template = Template(textwrap.dedent('''
    <html>
      <head>
        <title>${date} - /root/Changelog on ${hostname}</title>
        <link rel="stylesheet" href="/style.css" />
      </head>
      <body>
        <h1><a href="/">/root/Changelog on ${hostname}</a></h1>

        <div class="searchbox">
          <form action="search" method="get">
            <input type="text" name="q" class="searchtext" accesskey="s" />
            <input type="submit" value="Search" class="searchbutton" />
          </form>
        </div>

    <%block name="navbar">
        <div class="navbar">
    % if prev_url:
          <a href="${prev_url}">&laquo; ${prev_date}</a>
    % endif
          <strong>${date}</strong>
    % if next_url:
          <a href="${next_url}">${next_date} &raquo;</a>
    % endif
        </div>
    </%block>

    % if not entries:
        <p>No entries for this year.</p>
    % else:

    %     for entry in entries:
    <h3><a href="${entry.url()}">${entry.title()}</a></h3>
        ${entry.pre(slice(1, None))}
    %     endfor
    % endif

        ${navbar()}
      </body>
    </html>
'''))


@path(r'/(\d\d\d\d)')
def year_page(environ, year):
    hostname = get_hostname(environ)
    changelog = get_changelog(get_changelog_filename(environ))
    entries = changelog.filter(year=int(year))
    year_1st = datetime.date(int(year), 1, 1)
    year_last = datetime.date(int(year), 12, 31)
    prev_date = changelog.prev_date(year_1st)
    next_date = changelog.next_date(year_last)
    return year_template.render(hostname=hostname,
                                date=year,
                                entries=entries,
                                prev_url=prev_date and prev_date.strftime('/%Y'),
                                prev_date=prev_date and prev_date.strftime('%Y'),
                                next_url=next_date and next_date.strftime('/%Y'),
                                next_date=next_date and next_date.strftime('%Y'))


month_template = Template(textwrap.dedent('''
    <html>
      <head>
        <title>${date} - /root/Changelog on ${hostname}</title>
        <link rel="stylesheet" href="/style.css" />
      </head>
      <body>
        <h1><a href="/">/root/Changelog on ${hostname}</a></h1>

        <div class="searchbox">
          <form action="search" method="get">
            <input type="text" name="q" class="searchtext" accesskey="s" />
            <input type="submit" value="Search" class="searchbutton" />
          </form>
        </div>


    <%block name="navbar">
        <div class="navbar">
    % if prev_url:
          <a href="${prev_url}">&laquo; ${prev_date}</a>
    % endif
          <strong>${date}</strong>
    % if next_url:
          <a href="${next_url}">${next_date} &raquo;</a>
    % endif
        </div>
    </%block>

    % if not entries:
        <p>No entries for this month.</p>
    % else:

    %     for entry in entries:
    <h3><a href="${entry.url()}">${entry.title()}</a></h3>
        ${entry.pre(slice(1, None))}
    %     endfor
    % endif

        ${navbar()}
      </body>
    </html>
'''))


def month_url(date):
    return date.strftime('/%Y/%m') if date else None


@path(r'/(\d\d\d\d)/(\d\d)')
def month_page(environ, year, month):
    hostname = get_hostname(environ)
    changelog = get_changelog(get_changelog_filename(environ))
    entries = changelog.filter(year=int(year), month=int(month))
    month_1st = datetime.date(int(year), int(month), 1)
    month_last = (month_1st + datetime.timedelta(31)).replace(day=1) - datetime.timedelta(1)
    prev_date = changelog.prev_date(month_1st)
    next_date = changelog.next_date(month_last)
    return month_template.render(hostname=hostname,
                                 date='%s-%s' % (year, month),
                                 entries=entries,
                                 prev_url=month_url(prev_date),
                                 prev_date=prev_date and prev_date.strftime('%Y-%m'),
                                 next_url=month_url(next_date),
                                 next_date=next_date and next_date.strftime('%Y-%m'))


day_template = Template(textwrap.dedent('''
    <html>
      <head>
        <title>${date} - /root/Changelog on ${hostname}</title>
        <link rel="stylesheet" href="/style.css" />
      </head>
      <body>
        <h1><a href="/">/root/Changelog on ${hostname}</a></h1>

        <div class="searchbox">
          <form action="search" method="get">
            <input type="text" name="q" class="searchtext" accesskey="s" />
            <input type="submit" value="Search" class="searchbutton" />
          </form>
        </div>

    <%block name="navbar">
        <div class="navbar">
    % if prev_url:
          <a href="${prev_url}">&laquo; ${prev_date}</a>
    % endif
          <strong>${date}</strong>
    % if next_url:
          <a href="${next_url}">${next_date} &raquo;</a>
    % endif
        </div>
    </%block>

    % if not entries:
        <p>No entries for this date.</p>
    % else:

    %     for entry in entries:
        <h3 id="e${entry.id}">${entry.title()} <a class="permalink" href="${entry.url()}">&para;</a></h3>
        ${entry.pre(slice(1, None))}
    %     endfor
    % endif

        ${navbar()}
      </body>
    </html>
'''))


def date_url(date):
    return date.strftime('/%Y/%m/%d') if date else None


@path(r'/(\d\d\d\d)/(\d\d)/(\d\d)')
def day_page(environ, year, month, day):
    try:
        date = datetime.date(int(year), int(month), int(day))
    except ValueError:
        return not_found(environ)
    hostname = get_hostname(environ)
    changelog = get_changelog(get_changelog_filename(environ))
    entries = changelog.date_index.get(date, [])
    prev_date = changelog.prev_date(date)
    next_date = changelog.next_date(date)
    return day_template.render(date=date,
                               hostname=hostname,
                               entries=entries,
                               prev_url=date_url(prev_date),
                               prev_date=prev_date,
                               next_url=date_url(next_date),
                               next_date=next_date)


search_template = Template(textwrap.dedent('''
    <html>
      <head>
        <title>${query} - /root/Changelog on ${hostname}</title>
        <link rel="stylesheet" href="/style.css" />
      </head>
      <body>
        <h1><a href="/">/root/Changelog on ${hostname}</a></h1>

        <div class="searchbox">
          <form action="search" method="get">
            <input type="text" name="q" class="searchtext" value="${query}" accesskey="s" />
            <input type="submit" value="Search" class="searchbutton" />
          </form>
        </div>

        <p>${len(entries)} results for '${query}'</h2>

    % for entry in entries:
        <h3><a href="${entry.url()}">${entry.title()}</a></h3>
        ${entry.pre(slice(1, None))}
    % endfor

      </body>
    </html>
'''))


@path(r'/search')
def search_page(environ):
    form = cgi.parse_qs(environ.get('QUERY_STRING', ''))
    query = form.get('q', [''])[0]
    hostname = get_hostname(environ)
    changelog = get_changelog(get_changelog_filename(environ))
    entries = list(changelog.search(query))
    return search_template.render(hostname=hostname, query=query, entries=entries)


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


def reloading_wsgi_app(environ, start_response):
    # Horrible hack that gives me a fast development loop: reload the code on
    # every request!
    import changelog2html
    reload(changelog2html)
    return changelog2html.wsgi_app(environ, start_response)


def main():
    from wsgiref.simple_server import make_server
    port = 8080
    httpd = make_server('localhost', port, reloading_wsgi_app)
    print("Serving on http://localhost:%d" % port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
