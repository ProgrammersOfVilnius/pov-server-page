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


__author__ = 'Marius Gedminas <marius@gedmin.as>'
__version__ = '0.2'


DU_DIFF_SCRIPT = 'du-diff'  # assume it's on $PATH
DATE_RANGE_RX = re.compile(r'^(\d\d\d\d-\d\d-\d\d)\.\.(\d\d\d\d-\d\d-\d\d)$')


def get_directory(environ):
    return environ.get('DIRECTORY') or os.getenv('DIRECTORY') or '.'


def get_prefix(environ):
    script_name = environ['SCRIPT_NAME']
    return script_name.rstrip('/')


DeltaRow = namedtuple('DeltaRow', 'delta, path')


def fmt(delta):
    return '{0:,}'.format(delta)


def parse_dudiff(output):
    for line in output.splitlines():
        delta, location = line.split(None, 1)
        yield DeltaRow(int(delta), location)


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
        strict_undefined=True,
        default_filters=['unicode', 'h'],
        *args, **kw)


STYLESHEET = textwrap.dedent('''
    body {
        margin: 1em;
    }

    .du-diff {
        border-collapse: collapse;
    }
    .du-diff .sorting {
        color: #888;
        cursor: progress;
    }
    .du-diff th {
        text-align: left;
        cursor: pointer;
    }
    .du-diff td:first-child {
        text-align: right;
        padding: 4px;
    }
'''.lstrip('\n'))


def stylesheet():
    return Response(STYLESHEET, content_type='text/css')


dudiff_template = Template(textwrap.dedent('''
    <html>
      <head>
        <title>du-diff for ${location}: ${old}..${new}</title>
        <link rel="stylesheet" href="${prefix}/style.css" />
        <script type="text/javascript">
          function by_delta(row) {
            return parseInt(row.cells[0].innerText.replace(/,/g, ''));
          }
          function by_path(row) {
            return row.cells[1].innerText;
          }
          function sort(key) {
            var table = document.getElementById("du-diff");
            var tbody = table.tBodies[0];
            var rows = tbody.rows;
            var nrows = tbody.rows.length;
            var arr = new Array();
            var i;
            tbody.className = 'sorting';
            for (i = 0; i < nrows; i++) {
              var row = rows[i];
              arr[i] = [key(row), row.outerHTML];
            };
            arr.sort(function(a, b) {
              return (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0);
            });
            for (i = 0; i < nrows; i++) {
              arr[i] = arr[i][1];
            }
            tbody.innerHTML = arr.join('');
            tbody.className = '';
          }
        </script>
      </head>
      <body>
        <h1>du-diff for ${location}: ${old}..${new}</h1>

        <table id="du-diff" class="du-diff">
          <thead>
            <tr>
              <th onclick="sort(by_delta);">Delta</th>
              <th onclick="sort(by_path);">Location</th>
            </tr>
          </thead>
          <tbody>
    % for row in dudiff:
            <tr>
              <td>${fmt(row.delta)}</td>
              <td>${row.path}</td>
            </tr>
    % endfor
          </tbody>
        <table>
      </body>
    </html>
'''))


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
        html = dudiff_template.render_unicode(
            location=location, old=old, new=new,
            dudiff=parse_dudiff(diff), fmt=fmt,
            prefix=get_prefix(environ))
        return Response(html)


def dispatch(environ):
    path_info = environ['PATH_INFO'] or '/'
    if path_info == '/style.css':
        return stylesheet, ()
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
