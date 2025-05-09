# -*- coding: utf-8 -*-
import datetime
import errno
import functools
import os
import shutil
import socket
import sys
import tempfile
import textwrap
import time
import traceback
import unittest

try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

import mock
import pytest

import pov_server_page.changelog2html as c2h


class TestCase(unittest.TestCase):

    def patch(self, *args, **kw):
        patcher = mock.patch(*args, **kw)
        retval = patcher.start()
        self.addCleanup(patcher.stop)
        return retval

    def mkdtemp(self):
        tmpdir = tempfile.mkdtemp(prefix='changelog2html-test-')
        self.addCleanup(shutil.rmtree, tmpdir)
        return tmpdir


class TestTextObject(TestCase):

    def test_pre_empty(self):
        t = c2h.TextObject()
        self.assertEqual(t.pre(), '')

    def test_pre_nonempty(self):
        t = c2h.TextObject([
            '# dum de dum\n'
            'echo hello > world.txt\n'
        ])
        self.assertEqual(
            t.pre(),
            '<pre># dum de dum\n'
            'echo hello &gt; world.txt</pre>')

    def test_pre_sliced(self):
        t = c2h.TextObject(['%d\n' % n for n in range(1, 10)])
        self.assertEqual(
            t.pre(slice(3)),
            '<pre>1\n'
            '2\n'
            '3</pre>')

    def test_as_html(self):
        t = c2h.TextObject(['<same as pre(), actually>\n'])
        self.assertEqual(
            t.as_html(),
            '<pre>&lt;same as pre(), actually&gt;</pre>')


class TestPreamble(TestCase):

    def test_title(self):
        preamble = c2h.Preamble()
        self.assertEqual(preamble.title(), 'Preamble')

    def test_url(self):
        preamble = c2h.Preamble()
        self.assertEqual(preamble.url('/changelog'), '/changelog/')


class TestEntry(TestCase):

    default_example = """
        2015-11-05 15:57 +0200: mg
          # just writing tests
          # like you do
    """

    def makeEntry(self, text=default_example, id=1):
        text = textwrap.dedent(text.lstrip('\n')).splitlines(True)
        e = c2h.Entry.parse(text[0], id=id, text=text)
        assert e, "bad header: %s" % repr(text[0])
        return e

    def test_search(self):
        entry = self.makeEntry()
        self.assertTrue(entry.search('tests'))
        self.assertFalse(entry.search('cake'))

    def test_date(self):
        entry = self.makeEntry()
        self.assertTrue(entry.date(), datetime.date(2015, 11, 5))

    def test_timestamp(self):
        entry = self.makeEntry()
        self.assertTrue(entry.timestamp(), '2015-11-05 15:57 +0200')

    def test_timestamp_no_hour_minute(self):
        entry = self.makeEntry("""
            2020-05-27: mg
              # testing testing
        """)
        self.assertTrue(entry.timestamp(), '2015-11-05')

    def test_title(self):
        entry = self.makeEntry()
        self.assertTrue(entry.title(), '2015-11-05 15:57 +0200 mg')

    def test_url(self):
        entry = self.makeEntry()
        self.assertTrue(entry.url('/changelog'), '/2015/11/05/#e1')

    def test_anchor(self):
        entry = self.makeEntry()
        self.assertTrue(entry.anchor, 'e1')

    def test_target(self):
        entry = self.makeEntry()
        self.assertTrue(entry.target, '#e1')

    def test_as_html(self):
        entry = self.makeEntry()
        self.assertEqual(
            entry.as_html(),
            '<h3>2015-11-05 15:57 +0200 mg</h3>\n'
            '<pre>  # just writing tests\n'
            '  # like you do</pre>')


class TestToDoItem(TestCase):

    def test_as_html(self):
        item = c2h.ToDoItem(c2h.Preamble(), title='Laundry & stuff')
        self.assertEqual(
            item.as_html(),
            '<li>Laundry &amp; stuff (Preamble)</li>')

    def test_as_html_unicode(self):
        item = c2h.ToDoItem(c2h.Preamble(), title=u'Løündri')
        self.assertEqual(item.as_html(), u'<li>Løündri (Preamble)</li>')


class TestChangelog(TestCase):

    default_example = """
        Hey hello this is a preamble
        You see it is text before the first entry

        It may also have to-do items, e.g.:

        - [ ] write some tests
              for parsing to-do items

        2014-01-01 17:00 +0200: mg
          # why not have more than one year in the changelog?

        2015-11-04 12:00 +0200: mg
          # decided to do a lot of test coverage for great justice

        2015-11-05 15:57 +0200: mg
          # just writing tests
          # like you do
    """

    def makeChangelog(self, text=default_example):
        changelog = c2h.Changelog()
        changelog.parse(StringIO(textwrap.dedent(text.lstrip('\n'))))
        return changelog

    def test_filter(self):
        changelog = self.makeChangelog()
        self.assertEqual(len(changelog.filter()), 3)
        self.assertEqual(len(changelog.filter(2014)), 1)
        self.assertEqual(len(changelog.filter(2015)), 2)
        self.assertEqual(len(changelog.filter(2015, 10)), 0)
        self.assertEqual(len(changelog.filter(2015, 11)), 2)
        self.assertEqual(len(changelog.filter(2015, 11, 4)), 1)

    def test_search(self):
        changelog = self.makeChangelog()
        self.assertEqual(len(changelog.search('test')), 2)
        self.assertEqual(len(changelog.search('Test')), 2)

    def test_search_order_is_newest_first(self):
        changelog = self.makeChangelog()
        self.assertEqual([e.id for e in changelog.search('test')], [3, 2])

    def test_parse(self):
        changelog = self.makeChangelog()
        self.assertEqual(changelog.preamble.text[0],
                         'Hey hello this is a preamble\n')
        self.assertEqual(len(changelog.entries), 3)
        self.assertEqual(changelog.todo[0].title,
                         'write some tests for parsing to-do items')

    def test_entries_for_date(self):
        changelog = self.makeChangelog()
        self.assertEqual(
            len(changelog.entries_for_date(datetime.date(2015, 11, 4))), 1)
        self.assertEqual(
            len(changelog.entries_for_date(datetime.date(2015, 11, 3))), 0)

    def test_prev_date(self):
        changelog = self.makeChangelog()
        self.assertEqual(changelog.prev_date(datetime.date(2015, 11, 4)),
                         datetime.date(2014, 1, 1))
        self.assertEqual(changelog.prev_date(datetime.date(2014, 1, 1)),
                         None)

    def test_next_date(self):
        changelog = self.makeChangelog()
        self.assertEqual(changelog.next_date(datetime.date(2015, 11, 4)),
                         datetime.date(2015, 11, 5))
        self.assertEqual(changelog.next_date(datetime.date(2015, 11, 5)),
                         None)

    def test_read(self):
        filename = os.path.join(self.mkdtemp(), 'changelog')
        with open(filename, 'w') as f:
            f.write(textwrap.dedent(self.default_example.lstrip('\n')))
        changelog = c2h.Changelog(filename)
        self.assertEqual(changelog.preamble.text[0],
                         'Hey hello this is a preamble\n')
        self.assertEqual(len(changelog.entries), 3)
        self.assertNotEqual(changelog.mtime, None)

    def test_read_nonascii(self):
        filename = os.path.join(self.mkdtemp(), 'changelog')
        with open(filename, 'wb') as f:
            f.write(u'\N{SNOWMAN}\n'.encode('UTF-8'))
        changelog = c2h.Changelog(filename)
        self.assertEqual(changelog.preamble.text[0],
                         u'\N{SNOWMAN}\n')


class TestMotd(TestCase):

    def test_read_file(self):
        motd = c2h.Motd(__file__)
        self.assertTrue(motd.raw)

    def test_read_no_file(self):
        motd = c2h.Motd('/no/such/file')
        self.assertEqual(motd.raw, '')

    def test_as_html_empty(self):
        motd = c2h.Motd()
        self.assertEqual(motd.as_html(), '')

    def test_as_html_nonempty(self):
        motd = c2h.Motd(raw='Hello <\033[31mworld\033[0m>!\n')
        self.assertEqual(
            motd.as_html(),
            '<pre class="motd">Hello &lt;<span style="color: #cc0000">world</span>&gt;!</pre>')


class TestAnsiColors(TestCase):

    def test_ansi2html(self):
        self.assertEqual(
            c2h.ansi2html('Hello, \033[1;37minvisible\033[m world! <>&'),
            'Hello, <span style="color: #ededeb">invisible</span> world! &lt;&gt;&amp;')

    def test_ansi2html_hi_intensity(self):
        self.assertEqual(c2h.ansi2html('\033[91m*'),
                         '<span style="color: #ef2828">*</span>')

    def test_ansi2html_bold(self):
        self.assertEqual(c2h.ansi2html('\033[1;31m*'),
                         '<span style="color: #ef2828">*</span>')

    def test_ansi2html_explicit_non_bold(self):
        self.assertEqual(c2h.ansi2html('\033[0;31m*'),
                         '<span style="color: #cc0000">*</span>')

    def test_ansi2html_regular(self):
        self.assertEqual(c2h.ansi2html('\033[31m*'),
                         '<span style="color: #cc0000">*</span>')

    def test_ansi2html_xterm_256_color(self):
        self.assertEqual(c2h.ansi2html('\033[38;5;255m*'),
                         '<span style="color: #eeeeee">*</span>')

    def test_ansi2html_short_reset(self):
        self.assertEqual(c2h.ansi2html('\033[31m*\033[m.'),
                         '<span style="color: #cc0000">*</span>.')

    def test_ansi2html_alt_syntax(self):
        # Xterm maintains a color palette whose entries are identified
        # by an index beginning with zero.  If 88- or 256-color support
        # is compiled, the following apply:
        # o All parameters are decimal integers.
        # o RGB values range from zero (0) to 255.
        # o ISO-8613-3 can be interpreted in more than one way; xterm
        #   allows the semicolons in this control to be replaced by
        #   colons (but after the first colon, colons must be used).
        #
        # These ISO-8613-3 controls are supported:
        #   Pm = 3 8 ; 2 ; Pr; Pg; Pb -> Set foreground color to the
        # closest match in xterm's palette for the given RGB Pr/Pg/Pb.
        #   Pm = 3 8 ; 5 ; Ps -> Set foreground color to the second Ps.
        #   Pm = 4 8 ; 2 ; Pr; Pg; Pb -> Set background color to the
        # closest match in xterm's palette for the given RGB Pr/Pg/Pb.
        #   Pm = 4 8 ; 5 ; Ps -> Set background color to the second Ps.
        #       -- http://invisible-island.net/xterm/ctlseqs/ctlseqs.html
        self.assertEqual(c2h.ansi2html('\033[38;2;255;255;255m*'),
                         '<span style="color: #ffffff">*</span>')
        self.assertEqual(c2h.ansi2html('\033[38;2;255:255:255m*'),
                         '<span style="color: #ffffff">*</span>')


class TestLinkify(TestCase):

    def test(self):
        self.assertEqual(c2h.linkify('hello'), 'hello')

    def test_html(self):
        self.assertEqual(c2h.linkify('<he&lo>'), '&lt;he&amp;lo&gt;')

    def test_link(self):
        self.assertEqual(
            c2h.linkify('see http://example.com for more'),
            'see <a href="http://example.com">http://example.com</a> for more',
        )

    def test_link_in_parens(self):
        self.assertEqual(
            c2h.linkify('see [link](http://example.com)'),
            'see [link](<a href="http://example.com">http://example.com</a>)',
        )

    def test_link_with_ampersands(self):
        self.assertEqual(
            c2h.linkify('see http://example.com/?q=a&b for more'),
            'see <a href="http://example.com/?q=a&amp;b">'
            'http://example.com/?q=a&amp;b</a> for more',
        )

    def test_link_with_quotes(self):
        self.assertEqual(
            c2h.linkify('see http://example.com/?q="a" for more'),
            'see <a href="http://example.com/?q=&quot;a&quot;">'
            'http://example.com/?q=&quot;a&quot;</a> for more',
        )

    def test_launchpad_bug(self):
        self.assertEqual(
            c2h.linkify('# LP: #12345'),
            '# <a href="https://pad.lv/12345">LP: #12345</a>',
        )

    def test_link_unicode(self):
        self.assertEqual(
            c2h.linkify(u'see http://example.com/?q=ünicøde for more'),
            u'see <a href="http://example.com/?q=ünicøde">'
            u'http://example.com/?q=ünicøde</a> for more',
        )


class TestHighlightText(TestCase):

    def test(self):
        text = 'Hello world'
        self.assertEqual(
            c2h.highlight_text('lo', text),
            'Hel<mark>lo</mark> world',
        )

    def test_case_insensitive(self):
        text = 'HelLo world'
        self.assertEqual(
            c2h.highlight_text('lo', text),
            'Hel<mark>Lo</mark> world',
        )

    def test_markup(self):
        text = 'Hello &amp; goodbye'
        self.assertEqual(
            c2h.highlight_text('lo & goo', text),
            'Hel<mark>lo &amp; goo</mark>dbye',
        )

    def test_link(self):
        text = '<a href="https://example.com/">https://example.com/'
        self.assertEqual(
            c2h.highlight_text('example', text),
            '<a href="https://example.com/">https://<mark>example</mark>.com/',
        )

    def test_unicode(self):
        text = u'Hellø world'
        self.assertEqual(
            c2h.highlight_text(u'lø', text),
            u'Hel<mark>lø</mark> world',
        )


class TestGetChangelog(TestCase):

    def test(self):
        changelog = c2h.get_changelog(__file__)
        self.assertIsInstance(changelog, c2h.Changelog)

    def test_cached_load(self):
        changelog = c2h.get_changelog(__file__)
        changelog_again = c2h.get_changelog(__file__)
        self.assertTrue(changelog is changelog_again)

    def test_cache_invalidation(self):
        mtime = time.time() - 1
        filename = os.path.join(self.mkdtemp(), 'changelog')
        with open(filename, 'w') as f:
            f.write('first version')
        os.utime(filename, (mtime, mtime))
        changelog = c2h.get_changelog(filename)
        with open(filename, 'w') as f:
            f.write('new version')
        changelog_again = c2h.get_changelog(filename)
        self.assertEqual(changelog.preamble.text[0], 'first version')
        self.assertEqual(changelog_again.preamble.text[0], 'new version')


class TestHostname(TestCase):

    def test_wsgi(self):
        environ = {'HOSTNAME': 'frog.example.com'}
        self.assertEqual(c2h.get_hostname(environ), 'frog.example.com')

    def test_cgi(self):
        os.environ['HOSTNAME'] = 'toad.example.com'
        self.assertEqual(c2h.get_hostname({}), 'toad.example.com')

    def test_fallback(self):
        os.environ.pop('HOSTNAME', None)
        self.assertEqual(c2h.get_hostname({}), socket.gethostname())


class TestChangelogFilename(TestCase):

    def test_wsgi(self):
        environ = {'CHANGELOG_FILE': '/tmp/changelog'}
        self.assertEqual(c2h.get_changelog_filename(environ), '/tmp/changelog')

    def test_cgi(self):
        os.environ['CHANGELOG_FILE'] = '/srv/changelog'
        self.assertEqual(c2h.get_changelog_filename({}), '/srv/changelog')

    def test_fallback(self):
        os.environ.pop('CHANGELOG_FILE', None)
        self.assertEqual(c2h.get_changelog_filename({}), '/root/Changelog')


class TestGetMotdFilename(TestCase):

    def test_wsgi(self):
        environ = {'MOTD_FILE': '/tmp/motd'}
        self.assertEqual(c2h.get_motd_filename(environ), '/tmp/motd')

    def test_cgi(self):
        os.environ['MOTD_FILE'] = '/srv/motd'
        self.assertEqual(c2h.get_motd_filename({}), '/srv/motd')

    def test_fallback(self):
        os.environ.pop('MOTD_FILE', None)
        self.assertEqual(c2h.get_motd_filename({}), '/etc/motd')


class TestResponse(TestCase):

    def test(self):
        response = c2h.Response('hello')
        self.assertEqual(response.body, 'hello')
        self.assertEqual(response.status, '200 OK')
        self.assertEqual(response.headers,
                         {'Content-Type': 'text/html; charset=UTF-8'})


class TestNotFound(TestCase):

    def test(self):
        response = c2h.not_found({})
        self.assertEqual(response.body, '<h1>404 Not Found</h1>')
        self.assertEqual(response.status, '404 Not Found')
        self.assertEqual(response.headers,
                         {'Content-Type': 'text/html; charset=UTF-8'})


class TestDispatch(TestCase):

    def test_no_args(self):
        environ = {'PATH_INFO': '/'}
        view = c2h.dispatch(environ)
        self.assertIsInstance(view, functools.partial)
        self.assertEqual(view.func, c2h.main_page)
        self.assertEqual(view.args, (environ, ))

    def test_with_args(self):
        environ = {'PATH_INFO': '/2013/'}
        view = c2h.dispatch(environ)
        self.assertIsInstance(view, functools.partial)
        self.assertEqual(view.func, c2h.year_page)
        self.assertEqual(view.args, (environ, '2013'))

    def test_not_found(self):
        environ = {'PATH_INFO': '/nosuch'}
        view = c2h.dispatch(environ)
        self.assertIsInstance(view, functools.partial)
        self.assertEqual(view.func, c2h.not_found)
        self.assertEqual(view.args, (environ, ))


class TestGetPrefix(TestCase):

    def test(self):
        environ = {'SCRIPT_NAME': '/changelog/'}
        self.assertEqual(c2h.get_prefix(environ), '/changelog')


class TestMakoErrorHandler(unittest.TestCase):

    @pytest.mark.xfail(
        sys.version_info >= (3, 13),
        reason="traceback formatter in 3.13 shows only the first line of code",
    )
    def test(self):
        template = c2h.Template(textwrap.dedent('''
           <h1>Hello</h1>

           ${x / y}
        '''))
        try:
            template.render_unicode(x=0, y=0)
        except ZeroDivisionError:
            tb = ''.join(traceback.format_tb(sys.exc_info()[-1])).splitlines()
            last_part = '\n'.join(tb[-5:])
            self.assertIn(' line 4 in render_body:', last_part)
            self.assertIn('# ${x / y}', last_part)
        else:
            self.fail("did not let the error escape")


class TestTemplateDefaultFilters(unittest.TestCase):

    def test(self):
        template = c2h.Template('<p>${var}</p>')
        self.assertEqual(template.render_unicode(var='&'),
                         '<p>&amp;</p>')


class TestStylesheet(TestCase):

    def test(self):
        response = c2h.stylesheet({})
        self.assertTrue(response.body.startswith('body {'))
        self.assertEqual(response.status, '200 OK')
        self.assertEqual(response.headers, {'Content-Type': 'text/css'})


class TestStatic(TestCase):

    env = {'_ALLOW_STATIC_FILES': True}

    def test(self):
        response = c2h.static(self.env, 'css/bootstrap.min.css')
        self.assertTrue(response.body.startswith(b'/*!\n * Bootstrap'))
        self.assertEqual(response.status, '200 OK')
        self.assertEqual(response.headers, {'Content-Type': 'text/css'})

    def test_not_available_for_mod_wsgi(self):
        response = c2h.static({}, 'css/bootstrap.min.css')
        self.assertEqual(response.status, '404 Not Found')

    def test_no_jailbreak_via_abs_path(self):
        response = c2h.static(self.env, '/etc/passwd')
        self.assertEqual(response.status, '404 Not Found')

    def test_no_jailbreak_via_pardir(self):
        response = c2h.static(self.env, '../Makefile')
        self.assertEqual(response.status, '404 Not Found')


class PageTestCase(TestCase):

    maxDiff = None

    environment = {
        'HOSTNAME': 'example.com',
        'SCRIPT_NAME': '/',
        'CHANGELOG_FILE': 'testlog',
        'MOTD_FILE': 'testmotd'
    }

    changelog_text = """
        Test changelog
        with some rambling preamble text

        - [ ] and maybe a todo item

        2014-10-08 09:26 +0300: mg
          # did a thing
          vi /etc/thing
            blah blah

    """

    motd_text = "Welcome to example.com!\n"

    def setUp(self):
        self.patch('pov_server_page.changelog2html.get_changelog', self.get_changelog)
        self.patch('pov_server_page.changelog2html.get_motd', self.get_motd)

    def get_changelog(self, filename):
        if filename == 'nosuchfile':
            raise OSError(errno.ENOENT)
        assert filename == 'testlog'
        changelog_text = textwrap.dedent(self.changelog_text.lstrip('\n'))
        changelog = c2h.Changelog()
        changelog.parse(StringIO(changelog_text))
        return changelog

    def get_motd(self, filename):
        assert filename == 'testmotd'
        return c2h.Motd(raw=self.motd_text)

    def environ(self, **kw):
        return dict(self.environment, **kw)

    def assertResponse(self, actual, expected):
        expected = textwrap.dedent(expected.lstrip('\n'))
        if self.normalize(actual) != self.normalize(expected):
            self.assertEqual(actual, expected)

    def normalize(self, text):
        return ' '.join(text.strip().split())


class TestMainPage(PageTestCase):

    def test(self):
        response = c2h.main_page(self.environ())
        self.assertResponse(response, """
        <!DOCTYPE html>
        <html lang="en">
          <head>
            <meta charset="UTF-8">
            <meta http-equiv="X-UA-Compatible" content="IE=edge">
            <meta name="viewport" content="width=device-width, initial-scale=1">

            <title>/root/Changelog on example.com</title>

            <link rel="stylesheet" href="/static/css/bootstrap.min.css">
            <link rel="stylesheet" href="/static/css/style.css">
            <link rel="stylesheet" href="/style.css">
          </head>
          <body>

            <h1>/root/Changelog on example.com</h1>
            <div class="searchbox hidden-print">
              <form action="/search" method="get" class="form-inline">
                <input type="text" name="q" aria-label="Search" class="form-control" accesskey="s" autofocus>
                <button type="submit" class="btn btn-primary">Search</button>
              </form>
            </div>

            <pre class="motd">Welcome to example.com!</pre>

            <pre>Test changelog
        with some rambling preamble text

        - [ ] and maybe a todo item</pre>

            <h2>To do list</h2>

            <ul class="todo">
              <li><a href="/">and maybe a todo item</a></li>
            </ul>

            <h2>Latest entries</h2>

            <h3><a href="/2014/10/08/#e1">2014-10-08 09:26 +0300 mg</a></h3>

            <pre>  # did a thing
          vi /etc/thing
            blah blah</pre>

          </body>
        </html>
        """)

    def test_not_found(self):
        response = c2h.main_page(self.environ(CHANGELOG_FILE='nosuchfile'))
        self.assertEqual(response.status, '404 Not Found')


class TestRawPage(PageTestCase):

    changelog_text = u"Test changelog\n\N{SNOWMAN}".encode('UTF-8')

    def setUp(self):
        filename = os.path.join(self.mkdtemp(), 'changelog')
        with open(filename, 'wb') as f:
            f.write(self.changelog_text)
        self.environment = dict(self.environment, CHANGELOG_FILE=filename)

    def test(self):
        response = c2h.raw_page(self.environ(), 'attachment')
        self.assertEqual(response.body, self.changelog_text)
        self.assertEqual(response.status, '200 OK')
        self.assertEqual(
            response.headers,
            {
                'Content-Type': 'text/plain; charset=UTF-8',
                'Content-Disposition':
                    'attachment; filename="Changelog.example.com"',
            })

    def test_not_found(self):
        response = c2h.raw_page(self.environ(CHANGELOG_FILE='nosuchfile'))
        self.assertEqual(response.status, '404 Not Found')


class TestAllPage(PageTestCase):

    def test(self):
        response = c2h.all_page(self.environ())
        self.assertIn('All entries', response)

    def test_not_found(self):
        response = c2h.all_page(self.environ(CHANGELOG_FILE='nosuchfile'))
        self.assertEqual(response.status, '404 Not Found')


class TestYearPage(PageTestCase):

    def test(self):
        response = c2h.year_page(self.environ(), '2014')
        self.assertIn('<title>2014', response)

    def test_empty_year(self):
        response = c2h.year_page(self.environ(), '2010')
        self.assertIn('<title>2010', response)
        self.assertIn('No entries for this year', response)

    def test_not_found(self):
        response = c2h.year_page(self.environ(CHANGELOG_FILE='nosuchfile'),
                                 '2021')
        self.assertEqual(response.status, '404 Not Found')


class TestMonthPage(PageTestCase):

    def test(self):
        response = c2h.month_page(self.environ(), '2014', '10')
        self.assertIn('<title>2014-10', response)

    def test_empty_month(self):
        response = c2h.month_page(self.environ(), '2014', '11')
        self.assertIn('<title>2014-11', response)
        self.assertIn('No entries for this month', response)

    def test_not_found(self):
        response = c2h.month_page(self.environ(CHANGELOG_FILE='nosuchfile'),
                                  '2021', '03')
        self.assertEqual(response.status, '404 Not Found')


class TestDayPage(PageTestCase):

    def test(self):
        response = c2h.day_page(self.environ(), '2014', '10', '08')
        self.assertIn('<title>2014-10-08', response)

    def test_empty_day(self):
        response = c2h.day_page(self.environ(), '2014', '10', '09')
        self.assertIn('<title>2014-10-09', response)
        self.assertIn('No entries for this date', response)

    def test_bad_date(self):
        response = c2h.day_page(self.environ(), '2014', '02', '29')
        self.assertEqual(response.status, '404 Not Found')

    def test_not_found(self):
        response = c2h.day_page(self.environ(CHANGELOG_FILE='nosuchfile'),
                                '2021', '03', '29')
        self.assertEqual(response.status, '404 Not Found')


class TestSearchPage(PageTestCase):

    def test(self):
        response = c2h.search_page(self.environ(QUERY_STRING='q=thing'))
        self.assertIn('<title>thing -', response)
        self.assertIn("1 results for 'thing'", response)

    def test_unicode(self):
        response = c2h.search_page(self.environ(QUERY_STRING='q=%C4%85'))
        self.assertIn(u'<title>ą -', response)

    def test_not_found(self):
        response = c2h.search_page(self.environ(CHANGELOG_FILE='nosuchfile'))
        self.assertEqual(response.status, '404 Not Found')


class TestWsgiApp(PageTestCase):

    def test_view_that_returns_response(self):
        start_response = mock.Mock()
        body = c2h.wsgi_app(self.environ(PATH_INFO='/notfound'), start_response)
        self.assertEqual(body, [b'<h1>404 Not Found</h1>'])
        self.assertEqual(start_response.call_count, 1)
        self.assertEqual(start_response.call_args[0],
                         ('404 Not Found', [
                             ('Content-Type', 'text/html; charset=UTF-8'),
                         ]))

    def test_view_that_returns_string(self):
        start_response = mock.Mock()
        body = c2h.wsgi_app(self.environ(PATH_INFO='/'), start_response)
        self.assertEqual(len(body), 1)
        self.assertIn(b'<title>/root/Changelog on example.com', body[0])
        self.assertEqual(start_response.call_count, 1)
        self.assertEqual(start_response.call_args[0],
                         ('200 OK', [
                             ('Content-Type', 'text/html; charset=UTF-8'),
                         ]))


class TestReloadingWsgiApp(PageTestCase):

    def test(self):
        # reloading_wsgi_app reloads the module, which neatly destroys
        # all of our carefully monkey-patched mocks
        environ = self.environ(
            PATH_INFO='/',
            CHANGELOG_FILE='/dev/null',
            MOTD_FILE='/dev/null',
        )
        start_response = mock.Mock()
        c2h.reloading_wsgi_app(environ, start_response)
        self.assertEqual(start_response.call_count, 1)


class TestMain(TestCase):

    def setUp(self):
        super(TestMain, self).setUp()
        self.mock_make_server = self.patch('wsgiref.simple_server.make_server')
        self.stderr = self.patch('sys.stderr', StringIO())

    def run_main(self, *args):
        orig_argv = sys.argv
        try:
            sys.argv = ['changelog2html.py'] + list(args)
            c2h.main()
        finally:
            sys.argv = orig_argv

    def test(self):
        self.run_main()
        self.assertTrue(self.mock_make_server().serve_forever.called)

    def test_hostname_override(self):
        self.run_main('--name', 'frog.example.com')
        self.assertTrue(self.mock_make_server().serve_forever.called)
        self.assertEqual(os.environ['HOSTNAME'], 'frog.example.com')

    def test_changelog_file_override(self):
        self.run_main('/tmp/alt-changelog')
        self.assertTrue(self.mock_make_server().serve_forever.called)
        self.assertEqual(os.environ['CHANGELOG_FILE'], '/tmp/alt-changelog')

    def test_error_handling(self):
        with self.assertRaises(SystemExit):
            self.run_main('too', 'many')
        self.assertIn("changelog2html.py: error: too many arguments",
                      self.stderr.getvalue())

    def test_clean_interruption(self):
        self.mock_make_server().serve_forever.side_effect = KeyboardInterrupt
        self.run_main()
        self.assertEqual(self.stderr.getvalue(), "")
