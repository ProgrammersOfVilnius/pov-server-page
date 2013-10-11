#!/usr/bin/python
"""
WSGI application that renders /root/Changelog
"""

import re
import os
import textwrap
import socket
import cgi


__author__ = 'Marius Gedminas <marius@gedmin.as>'
__version__ = '0.1'


HOSTNAME = socket.gethostname()
CHANGELOG_FILE = '/root/Changelog'


class TextObject(object):

    def __init__(self):
        self.text = []

    def pre(self, slice=slice(None)):
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

    def timestamp(self):
        return u'{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d} {timezone}'.format(
                year=self.year, month=self.month, day=self.day,
                hour=self.hour, minute=self.minute, timezone=self.timezone)

    def title(self):
        return u'{timestamp} {user}'.format(timestamp=self.timestamp(), user=self.user)

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
        if filename:
            self.read(filename)

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


def render_changelog(environ):
    changelog = get_changelog(get_changelog_filename(environ))
    return textwrap.dedent(u'''
        <html>
          <head>
            <title>/root/Changelog on {hostname}</title>
          </head>
          <body>
            <h1>/root/Changelog on {hostname}</h1>

            {preamble}

            {todos}

            <h2>Latest entries</h2>

            {entries}

            {more}
          </body>
        </html>
        ''').format(hostname=get_hostname(environ),
                    preamble=changelog.preamble.as_html(),
                    todos=render_todos(changelog),
                    entries='\n'.join(e.as_html() for e in changelog.entries[:-5:-1]),
                    more='(%d older changelog entries are present)'
                            % (len(changelog.entries) - 5)
                                 if len(changelog.entries) > 5 else '')


def render_todos(changelog):
    if not changelog.todo:
        return u''
    return textwrap.dedent(u'''
        <h2>To do list</h2>

        <ul class="todo">
        {items}
        </ul>
        ''').format(items='\n'.join('  ' + i.as_html()
                                    for i in sorted(changelog.todo,
                                                    reverse=True,
                                                    key=lambda i: i.entry.id)))


def wsgi_app(environ, start_response):
    PATH_INFO = environ['PATH_INFO']
    if PATH_INFO != '/' and PATH_INFO != '':
        status = '404 Not Found'
        headers = [('Content-Type', 'text/plain')]
        start_response(status, headers)
        return ['404 Not Found: ' + PATH_INFO]
    status = '200 OK'
    headers = [('Content-Type', 'text/html; charset=UTF-8')]
    start_response(status, headers)
    return [render_changelog(environ).encode('UTF-8')]


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
