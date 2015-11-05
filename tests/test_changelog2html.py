import unittest
try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

import changelog2html as c2h

from nose.tools import assert_equal


TESTENV = {
    'HOSTNAME': 'example.com',
    'SCRIPT_NAME': '/',
    'CHANGELOG_FILE': 'testlog',
    'MOTD_FILE': '/dev/null'
}


TESTLOG = '''\
Test changelog
with some rambling preamble text

- [ ] and maybe a todo item

2014-10-08 09:26 +0300: mg
  # did a thing
  vi /etc/thing
    blah blah

'''


def environ(**kw):
    e = TESTENV.copy()
    e.update(kw)
    return e


def get_changelog(filename):
    assert filename == 'testlog'
    changelog = c2h.Changelog()
    changelog.parse(StringIO(TESTLOG))
    return changelog


def setup_module(module):
    module.orig_get_changelog = c2h.get_changelog
    c2h.get_changelog = get_changelog


def teardown_module(module):
    c2h.get_changelog = module.orig_get_changelog


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


def doctest_main_page():
    """Test for main_page

        >>> print(c2h.main_page(environ())) # doctest: +NORMALIZE_WHITESPACE
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
        <BLANKLINE>
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

    """


def test_strip_ansi():
    assert_equal(c2h.strip_ansi('Hello, \033[1;37minvisible\033[m world'),
                 'Hello, invisible world')


def test_ansi2html():
    assert_equal(c2h.ansi2html('Hello, \033[1;37minvisible\033[m world! <>&'),
                 'Hello, <span style="color: #ededeb">invisible</span> world! &lt;&gt;&amp;')
