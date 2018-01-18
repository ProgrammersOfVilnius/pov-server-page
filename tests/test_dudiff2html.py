import os
import shutil
import tempfile
import unittest

try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

import mock

import pov_server_page.dudiff2html as d2h


class TestCase(unittest.TestCase):

    def patch(self, *args, **kw):
        patcher = mock.patch(*args, **kw)
        retval = patcher.start()
        self.addCleanup(patcher.stop)
        return retval

    def mkdtemp(self):
        tmpdir = tempfile.mkdtemp(prefix='dudiff2html-test-')
        self.addCleanup(shutil.rmtree, tmpdir)
        return tmpdir


class TestGetDirectory(TestCase):

    def test_wsgi(self):
        self.assertEqual(d2h.get_directory({'DIRECTORY': '/foo'}), '/foo')

    def test_cgi(self):
        os.environ['DIRECTORY'] = '/bar'
        self.addCleanup(os.environ.pop, 'DIRECTORY', None)
        self.assertEqual(d2h.get_directory({}), '/bar')

    def test_fallback(self):
        os.environ.pop('DIRECTORY', None)
        self.assertEqual(d2h.get_directory({}), '.')


class TestFormat(TestCase):

    def test(self):
        self.assertEqual(d2h.fmt(0), '+0.0 kB')
        self.assertEqual(d2h.fmt(42), '+43.0 kB')  # 42 KiB = 43008 B = 43 KB
        self.assertEqual(d2h.fmt(12345), '+12.6 MB')
        self.assertEqual(d2h.fmt(123456789), '+126.4 GB')
        self.assertEqual(d2h.fmt(-123456789), '-126.4 GB')
        self.assertEqual(d2h.fmt(1234567890), '+1.3 TB')
        self.assertEqual(d2h.fmt(1234567890000), '+1,264.2 TB')


class TestParseDuDiff(TestCase):

    def test(self):
        self.assertEqual(
            list(d2h.parse_dudiff(
                b'-12345\t/foo\n'
                b'23456\t/bar\n'
            )),
            [
                d2h.DeltaRow(-12345, '/foo'),
                d2h.DeltaRow(23456, '/bar'),
            ])

    def test_non_ascii(self):
        self.assertEqual(
            list(d2h.parse_dudiff(
                b'-12345\t/foo\xff\n'
                b'23456\t/bar\n'
            )),
            [
                d2h.DeltaRow(-12345, u'/foo\ufffd'),
                d2h.DeltaRow(23456, u'/bar'),
            ])


class TestNotFound(TestCase):

    def test(self):
        response = d2h.not_found()
        self.assertEqual(response.body, '<h1>404 Not Found</h1>')
        self.assertEqual(response.status, '404 Not Found')
        self.assertEqual(response.headers,
                         {'Content-Type': 'text/html; charset=UTF-8'})


class TestStylesheet(TestCase):

    def test(self):
        response = d2h.stylesheet()
        self.assertTrue(response.body.startswith('body {'))
        self.assertEqual(response.status, '200 OK')
        self.assertEqual(response.headers,
                         {'Content-Type': 'text/css'})


class TestBootstrapStylesheet(TestCase):

    def test(self):
        response = d2h.bootstrap_stylesheet()
        self.assertTrue(response.body.startswith(b'/*!\n * Bootstrap'))
        self.assertEqual(response.status, '200 OK')
        self.assertEqual(response.headers,
                         {'Content-Type': 'text/css'})


class TestRenderDuDiff(TestCase):

    def setUp(self):
        os.environ.pop('DIRECTORY', None)
        self.dir = None
        # cannot rely on du-diff being installed while running tests
        d2h.DU_DIFF_SCRIPT = 'diff'
        self.addCleanup(setattr, d2h, 'DU_DIFF_SCRIPT', 'du-diff')
        self.stderr = self.patch('sys.stderr', StringIO())
        self.environ = {'SCRIPT_NAME': '/du/diff'}

    def create_dir(self):
        if self.dir is None:
            tmpdir = self.mkdtemp()
            os.environ['DIRECTORY'] = tmpdir
            self.addCleanup(os.environ.pop, 'DIRECTORY', None)
            self.dir = os.path.join(tmpdir, 'dir')
            os.mkdir(self.dir)

    def create_fake_file(self, date, data=b'42 /dir\n'):
        self.create_dir()
        with open(os.path.join(self.dir, 'du-%s.gz' % date), 'wb') as f:
            f.write(data)

    def render(self, *args):
        return d2h.render_du_diff(self.environ, *args)

    def test_bad_location_dots(self):
        response = self.render('..', '2016-02-03', '2016-02-04')
        self.assertEqual(response.status, '404 Not Found')

    def test_bad_location_slashes(self):
        response = self.render('sub/dir', '2016-02-03', '2016-02-04')
        self.assertEqual(response.status, '404 Not Found')

    def test_bad_location_no_such_dir(self):
        response = self.render('nosuchdir', '2016-02-03', '2016-02-04')
        self.assertEqual(response.status, '404 Not Found')

    def test_bad_location_no_old_file(self):
        self.create_dir()
        response = self.render('dir', '2016-02-03', '2016-02-04')
        self.assertEqual(response.status, '404 Not Found')

    def test_bad_location_no_new_file(self):
        self.create_fake_file('2016-02-03')
        response = self.render('dir', '2016-02-03', '2016-02-04')
        self.assertEqual(response.status, '404 Not Found')

    def test_good(self):
        self.create_fake_file('2016-02-03')
        self.create_fake_file('2016-02-04')
        response = self.render('dir', '2016-02-03', '2016-02-04')
        self.assertEqual(response.status, '200 OK')
        self.assertEqual(response.headers['Content-Type'], 'text/html; charset=UTF-8')

    def test_non_ascii(self):
        self.create_fake_file('2016-02-03', data=b'42 /dir\xc3\xbf')
        self.create_fake_file('2016-02-04', data=b'43 /dir\xc3\xff')
        d2h.DU_DIFF_SCRIPT = 'cat'  # diff doesn't like .gz files with binary data ;)
        response = self.render('dir', '2016-02-03', '2016-02-04')
        self.assertEqual(self.stderr.getvalue(), '')
        self.assertEqual(response.status, '200 OK')
        self.assertEqual(response.headers['Content-Type'], 'text/html; charset=UTF-8')

    def test_plaintext(self):
        self.create_fake_file('2016-02-03')
        self.create_fake_file('2016-02-04')
        response = self.render('dir', '2016-02-03', '2016-02-04', '.txt')
        self.assertEqual(response.status, '200 OK')
        self.assertEqual(response.headers['Content-Type'], 'text/plain; charset=UTF-8')

    def test_fail(self):
        d2h.DU_DIFF_SCRIPT = 'false'
        self.create_fake_file('2016-02-03')
        self.create_fake_file('2016-02-04')
        response = self.render('dir', '2016-02-03', '2016-02-04')
        self.assertEqual(response.status, '404 Not Found')
        self.assertIn('returned non-zero exit status', self.stderr.getvalue())


class TestDispatch(TestCase):

    def test_not_found(self):
        view, args = d2h.dispatch({'PATH_INFO': '/404'})
        self.assertEqual(view, d2h.not_found)
        self.assertEqual(args, ())

    def test_stylesheet(self):
        view, args = d2h.dispatch({'PATH_INFO': '/style.css'})
        self.assertEqual(view, d2h.stylesheet)
        self.assertEqual(args, ())

    def test_bootstrap_stylesheet(self):
        view, args = d2h.dispatch({'PATH_INFO': '/static/css/bootstrap.min.css'})
        self.assertEqual(view, d2h.bootstrap_stylesheet)
        self.assertEqual(args, ())

    def test_du_diff(self):
        environ = {'PATH_INFO': '/dir/2016-02-03..2016-02-04'}
        view, args = d2h.dispatch(environ)
        self.assertEqual(view, d2h.render_du_diff)
        self.assertEqual(args, (environ, 'dir', '2016-02-03', '2016-02-04', None))

    def test_du_diff_plaintext(self):
        environ = {'PATH_INFO': '/dir/2016-02-03..2016-02-04.txt'}
        view, args = d2h.dispatch(environ)
        self.assertEqual(view, d2h.render_du_diff)
        self.assertEqual(args, (environ, 'dir', '2016-02-03', '2016-02-04', '.txt'))


class TestWsgiApp(TestCase):

    def test(self):
        start_response = mock.Mock()
        body = d2h.wsgi_app({'PATH_INFO': '/404'}, start_response)
        self.assertEqual(body, [b'<h1>404 Not Found</h1>'])
        self.assertEqual(start_response.call_count, 1)
        self.assertEqual(start_response.call_args[0],
                         ('404 Not Found', [
                             ('Content-Type', 'text/html; charset=UTF-8'),
                         ]))


class TestReloadingWsgiApp(TestCase):

    def test(self):
        environ = dict(PATH_INFO='/404')
        start_response = mock.Mock()
        d2h.reloading_wsgi_app(environ, start_response)
        self.assertEqual(start_response.call_count, 1)


class TestMain(TestCase):

    def setUp(self):
        self.mock_make_server = self.patch('wsgiref.simple_server.make_server')
        self.stderr = self.patch('sys.stderr', StringIO())

    def run_main(self, *args):
        with mock.patch('sys.argv', ['dudiff2html.py'] + list(args)):
            d2h.main()

    def test(self):
        self.run_main()
        self.assertTrue(self.mock_make_server().serve_forever.called)

    def test_directory_override(self):
        self.run_main('/tmp/dir')
        self.assertTrue(self.mock_make_server().serve_forever.called)
        self.assertEqual(os.environ['DIRECTORY'], '/tmp/dir')

    def test_error_handling(self):
        with self.assertRaises(SystemExit):
            self.run_main('too', 'many')
        self.assertIn("dudiff2html.py: error: too many arguments",
                      self.stderr.getvalue())

    def test_clean_interruption(self):
        self.mock_make_server().serve_forever.side_effect = KeyboardInterrupt
        self.run_main()
        self.assertEqual(self.stderr.getvalue(), "")
