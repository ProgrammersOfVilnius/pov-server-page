import datetime
import os
import shutil
import tempfile
import textwrap
import unittest

try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

import mock

import changelog2html as c2h


class TestTextObject(unittest.TestCase):

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


class TestPreamble(unittest.TestCase):

    def test_title(self):
        preamble = c2h.Preamble()
        self.assertEqual(preamble.title(), 'Preamble')

    def test_url(self):
        preamble = c2h.Preamble()
        self.assertEqual(preamble.url('/changelog'), '/changelog/')


class TestEntry(unittest.TestCase):

    default_example = """
        2015-11-05 15:57 +0200: mg
          # just writing tests
          # like you do
    """

    def makeEntry(self, text=default_example, id=1):
        text = textwrap.dedent(text.lstrip('\n')).splitlines(True)
        m = c2h.Entry._header_rx.match(text[0])
        assert m, "bad header: %s" % repr(text[0])
        return c2h.Entry(id=id,
                         year=int(m.group('year')),
                         month=int(m.group('month')),
                         day=int(m.group('day')),
                         hour=int(m.group('hour')),
                         minute=int(m.group('minute')),
                         timezone=m.group('timezone'),
                         user=m.group('user'),
                         text=text)

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


class TestToDoItem(unittest.TestCase):

    def test_as_html(self):
        item = c2h.ToDoItem(c2h.Preamble(), title='Laundry & stuff')
        self.assertEqual(
            item.as_html(),
            '<li>Laundry &amp; stuff (Preamble)</li>')


class TestChangelog(unittest.TestCase):

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

    def mkdtemp(self):
        tmpdir = tempfile.mkdtemp(prefix='changelog2html-test-')
        self.addCleanup(shutil.rmtree, tmpdir)
        return tmpdir

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


class TestMotd(unittest.TestCase):

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
        motd = c2h.Motd(raw='Hello <\033[31mworld\033[0m>!')
        self.assertEqual(
            motd.as_html(),
            '<pre class="motd">Hello &lt;<span style="color: #cc0000">world</span>&gt;!</pre>')


class TestAnsiColors(unittest.TestCase):

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

    @unittest.skip("Not implemented yet")
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
        self.assertEqual(c2h.ansi2html('\033[38;2;255:255:255m*'), '*')


class TestMainPage(unittest.TestCase):

    maxDiff = None

    environment = {
        'HOSTNAME': 'example.com',
        'SCRIPT_NAME': '/',
        'CHANGELOG_FILE': 'testlog',
        'MOTD_FILE': '/dev/null'
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

    def environ(self, **kw):
        return dict(self.environment, **kw)

    def get_changelog(self, filename):
        assert filename == 'testlog'
        changelog_text = textwrap.dedent(self.changelog_text.lstrip('\n'))
        changelog = c2h.Changelog()
        changelog.parse(StringIO(changelog_text))
        return changelog

    def setUp(self):
        patcher = mock.patch('changelog2html.get_changelog', self.get_changelog)
        patcher.start()
        self.addCleanup(patcher.stop)

    def assertResponse(self, actual, expected):
        expected = textwrap.dedent(expected.lstrip('\n'))
        if self.normalize(actual) != self.normalize(expected):
            self.assertEqual(actual, expected)

    def normalize(self, text):
        return ' '.join(text.strip().split())

    def test(self):
        response = c2h.main_page(self.environ())
        self.assertResponse(response, """
        <html>
          <head>
            <title>/root/Changelog on example.com</title>
            <link rel="stylesheet" href="/style.css" />
          </head>
          <body>
            <h1>/root/Changelog on example.com</h1>
            <div class="searchbox">
              <form action="/search" method="get">
                <input type="text" name="q" class="searchtext" autofocus accesskey="s" />
                <input type="submit" value="Search" class="searchbutton" />
              </form>
            </div>
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
