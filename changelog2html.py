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

    def as_html(self):
        return u'<pre>%s</pre>' % u''.join(cgi.escape(line) for line in self.text)


class Preamble(TextObject):
    pass


class Entry(TextObject):

    def __init__(self, year, month, day, hour, minute, timezone, user):
        TextObject.__init__(self)
        self.year = year
        self.month = month
        self.day = day
        self.hour = hour
        self.minute = minute
        self.timezone = timezone
        self.user = user

    def as_html(self):
        return (
            u'<h3>{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d} {timezone} {user}</h3>\n'
            u'{text}'.format(
                year=self.year, month=self.month, day=self.day,
                hour=self.hour, minute=self.minute, timezone=self.timezone,
                user=self.user,
                text=u'<pre>%s</pre>' % u''.join(cgi.escape(line)
                                                 for line in self.text[1:]).rstrip()))


class Changelog(object):

    _entry_header = re.compile(
        r'^(?P<year>\d\d\d\d)-(?P<month>\d\d)-(?P<day>\d\d)'
        r' (?P<hour>\d\d):(?P<minute>\d\d)(?: (?P<timezone>[-+]\d\d\d\d))?'
        r'(?:: (?P<user>.*))?$')

    def __init__(self, filename=None):
        self.preamble = Preamble()
        self.entries = []
        self.mtime = None
        if filename:
            self.read(filename)

    def read(self, filename):
        with open(filename) as fp:
            self.mtime = os.fstat(fp.fileno()).st_mtime
            self.parse(fp)

    def parse(self, fp):
        entry = None
        for line in fp:
            line = line.decode('UTF-8', 'replace')
            m = self._entry_header.match(line)
            if m is not None:
                entry = Entry(int(m.group('year')),
                              int(m.group('month')),
                              int(m.group('day')),
                              int(m.group('hour')),
                              int(m.group('minute')),
                              m.group('timezone'),
                              m.group('user'))
                self.entries.append(entry)
            if entry is not None:
                entry.text.append(line)
            else:
                self.preamble.text.append(line)


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

            <h2>Latest entries</h2>

            {entries}

            {more}
          </body>
        </html>
        ''').format(hostname=get_hostname(environ),
                    preamble=changelog.preamble.as_html(),
                    entries='\n'.join(e.as_html() for e in changelog.entries[:-5:-1]),
                    more='(%d older changelog entries are present)'
                            % (len(changelog.entries) - 5)
                                 if len(changelog.entries) > 5 else '')


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


def main():
    from wsgiref.simple_server import make_server
    port = 8080
    httpd = make_server('localhost', port, wsgi_app)
    print("Serving on http://localhost:%d" % port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
