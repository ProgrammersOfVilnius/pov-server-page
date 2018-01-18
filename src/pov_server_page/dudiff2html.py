#!/usr/bin/python
"""
WSGI application that renders du-diff output
"""

import os
import re
import subprocess
import sys
import textwrap
from collections import namedtuple

import mako.template

from .utils import mako_error_handler


__author__ = 'Marius Gedminas <marius@gedmin.as>'
__version__ = '0.4'
__date__ = '2018-01-18'


DU_DIFF_SCRIPT = 'du-diff'  # assume it's on $PATH
DATE_RANGE_RX = re.compile(r'^(\d\d\d\d-\d\d-\d\d)\.\.(\d\d\d\d-\d\d-\d\d)(\.txt)?$')


def get_directory(environ):
    return environ.get('DIRECTORY') or os.getenv('DIRECTORY') or '.'


def get_prefix(environ):
    script_name = environ['SCRIPT_NAME']
    return script_name.rstrip('/')


DeltaRow = namedtuple('DeltaRow', 'delta, path')


def fmt(delta):
    # du reports sizes in kibibytes, let's convert to bytes then humanize
    size = delta * 1024
    for unit in 'kB', 'MB', 'GB', 'TB':
        size /= 1000.0
        if abs(size) < 1000:
            break
    return '{size:+,.1f} {unit}'.format(size=size, unit=unit)


def parse_dudiff(output):
    for line in output.splitlines():
        delta, location = line.split(None, 1)
        yield DeltaRow(int(delta), location.decode('UTF-8', 'replace'))


class Response(object):

    def __init__(self, body='', content_type='text/html; charset=UTF-8',
                 status='200 OK', headers={}):
        self.body = body
        self.status = status
        self.headers = {'Content-Type': content_type}
        self.headers.update(headers)


def not_found():
    return Response('<h1>404 Not Found</h1>', status='404 Not Found')


def Template(*args, **kw):
    return mako.template.Template(
        error_handler=mako_error_handler,
        strict_undefined=True,
        default_filters=['unicode', 'h'],
        *args, **kw)


STYLESHEET = textwrap.dedent('''
    body {
        margin: 1em;
    }

    .du-diff th:first-child {
        width: 8em;
    }
    .du-diff td:first-child {
        text-align: right;
    }

    .du-diff .sorting {
        color: #888;
        cursor: progress;
    }
    .du-diff th {
        cursor: pointer;
    }
    .du-diff th:hover {
        background: #f5f5f5;
    }
'''.lstrip('\n'))


def stylesheet():
    return Response(STYLESHEET, content_type='text/css')


def bootstrap_stylesheet():
    here = os.path.dirname(__file__)
    filename = os.path.join(here, 'static', 'css', 'bootstrap.min.css')
    with open(filename, 'rb') as f:
        return Response(f.read(), content_type='text/css')


dudiff_template = Template(textwrap.dedent('''
    <!DOCTYPE html>
    <html lang="en">
      <head>
        <meta charset="UTF-8">
        <meta http-equiv="X-UA-Compatible" content="IE=edge">
        <meta name="viewport" content="width=device-width, initial-scale=1">

        <title>du-diff for ${location}: ${old}..${new}</title>

        <link rel="stylesheet" href="/static/css/bootstrap.min.css">
        <link rel="stylesheet" href="${prefix}/style.css">

    <%
        if dudiff:
            max_depth = max(row.path.count('/') for row in dudiff)
        else:
            max_depth = 0
    %>

        <style type="text/css">
    % for n in range(1, max_depth):
        % for m in range(n + 1, max_depth + 1):
          .limit-${n} .depth-${m} { display: none; }
        % endfor
    % endfor
        </style>
      </head>
      <body>
        <h1>du-diff for ${location} <small>${old} to ${new}</small></h1>

    % if max_depth > 1:
    <div class="form-group pull-right">
      <label>Limit to depth</label>
      <div class="btn-group" role="toolbar" aria-label="Depth filter">
    %     for n in range(1, max_depth + 1):
        <button class="btn btn-default" id="depth-btn-${n}" role="group" aria-label="${n}">${n}</a>
    %     endfor
      </div>
    </div>
    % endif

        <table id="du-diff" class="du-diff table table-hover">
          <thead>
            <tr>
              <th id="sort_by_delta">Delta</th>
              <th id="sort_by_path">Location</th>
            </tr>
          </thead>
          <tbody>
    % for row in dudiff:
            <tr class="depth-${row.path.count('/')}">
              <td data-size="${row.delta}">${fmt(row.delta)}</td>
              <td>${row.path}</td>
            </tr>
    % endfor
          </tbody>
        <table>
        <script src="/static/js/dudiff.js"></script>
      </body>
    </html>
'''))


def render_du_diff(environ, location, old, new, format=None):
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
    if format == '.txt':
        return Response(diff, content_type='text/plain; charset=UTF-8')
    html = dudiff_template.render_unicode(
        location=location, old=old, new=new,
        dudiff=list(parse_dudiff(diff)), fmt=fmt,
        prefix=get_prefix(environ))
    return Response(html)


def dispatch(environ):
    path_info = environ['PATH_INFO'] or '/'
    if path_info == '/style.css':
        return stylesheet, ()
    if path_info == '/static/css/bootstrap.min.css':
        # only used for debugging
        return bootstrap_stylesheet, ()
    components = path_info.strip('/').split('/')
    if len(components) == 2:
        location, dates = components
        m = DATE_RANGE_RX.match(dates)
        if m:
            old, new, format = m.groups()
            return render_du_diff, (environ, location, old, new, format)
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
    from . import dudiff2html
    reload(dudiff2html)
    return dudiff2html.wsgi_app(environ, start_response)


def main():
    import datetime
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
    print("Looking for files under subdirectories under %s" % get_directory({}))
    print("Serving http://%s:%d/<subdir>/<date1>..<date2>[.txt]" % (host, opts.port))
    print("Try http://%s:%d/root/%s..%s"
          % (host, opts.port, datetime.date.today() - datetime.timedelta(1), datetime.date.today()))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
