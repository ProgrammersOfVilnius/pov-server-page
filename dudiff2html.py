#!/usr/bin/python
"""
WSGI application that renders du-diff output
"""

import os
import re
import subprocess
import sys


__author__ = 'Marius Gedminas <marius@gedmin.as>'
__version__ = '0.1'


DU_DIFF_SCRIPT = 'du-diff'  # assume it's on $PATH
DATE_RANGE_RX = re.compile(r'^(\d\d\d\d-\d\d-\d\d)\.\.(\d\d\d\d-\d\d-\d\d)$')


def get_directory(environ):
    return environ.get('DIRECTORY') or os.getenv('DIRECTORY') or '.'


class Response(object):

    def __init__(self, body='', content_type='text/html; charset=UTF-8',
                 status='200 OK', headers={}):
        self.body = body
        self.status = status
        self.headers = {'Content-Type': content_type}
        self.headers.update(headers)


def not_found():
    return Response('<h1>404 Not Found</h1>', status='404 Not Found')


def render_du_diff(environ, location, old, new):
    if '.' in location or '/' in location:
        return not_found()
    directory = os.path.join(get_directory(environ), location)
    if not os.path.isdir(directory):
        return not_found()
    old_file = os.path.join(directory, 'du-%s.gz' % old)
    new_file = os.path.join(directory, 'du-%s.gz' % new)
    if not os.path.exists(old_file):
        return not_found()
    if not os.path.exists(new_file):
        return not_found()
    try:
        diff = subprocess.check_output([DU_DIFF_SCRIPT, old_file, new_file])
    except subprocess.CalledProcessError as e:
        sys.stderr.write('%s\n' % e)
        sys.stderr.flush()
        return not_found()
    else:
        return Response(diff, content_type='text/plain; charset=UTF-8')


def dispatch(environ):
    path_info = environ['PATH_INFO'] or '/'
    components = path_info.strip('/').split('/')
    if len(components) == 2:
        location, dates = components
        m = DATE_RANGE_RX.match(dates)
        if m:
            old, new = m.groups()
            return render_du_diff, (environ, location, old, new)
    return not_found, ()


def wsgi_app(environ, start_response):
    view, args = dispatch(environ)
    response = view(*args)
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
    import dudiff2html
    reload(dudiff2html)
    return dudiff2html.wsgi_app(environ, start_response)


def main():
    import optparse
    from wsgiref.simple_server import make_server
    parser = optparse.OptionParser(
        'usage: %prog [options] [directory]',
        description="Launch web server showing du-diff output")
    parser.add_option('-p', '--port', type='int', default=8080)
    parser.add_option('--public', default=False,
                      help='accept non-localhost connections')
    opts, args = parser.parse_args()
    if len(args) > 1:
        parser.error("too many arguments")
    if args:
        os.environ['DIRECTORY'] = args[0]
    host = '0.0.0.0' if opts.public else 'localhost'
    httpd = make_server(host, opts.port, reloading_wsgi_app)
    print("Serving on http://%s:%d" % (host, opts.port))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
