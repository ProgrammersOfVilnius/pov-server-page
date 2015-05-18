try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

import changelog2html as c2h


TESTENV = {
    'HOSTNAME': 'example.com',
    'SCRIPT_NAME': '/',
    'CHANGELOG_FILE': 'testlog',
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


def doctest_TextObject():
    r"""Test for TextObject

        >>> t = c2h.TextObject()
        >>> t.text.append('# dum de dum\n')
        >>> t.text.append('echo hello > world.txt\n')
        >>> print(t.as_html())
        <pre># dum de dum
        echo hello &gt; world.txt</pre>

    """


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
