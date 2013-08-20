#!/usr/bin/python
"""
Build a generic server page.  Useful for sysadmins.

Reads a configuration file (/etc/pov/server-page.conf by default) and creates
an Apache vhost in /etc/apache2/sites-enabled/{hostname}, as well as a
static website in /var/www/{hostname}.

For full setup you also need to create the directory for Apache logs, enable
mod_rewrite, mod_ssl, make sure your Apache is listening on port 443, set up an
SSL certificate, set up a password file with htpasswd, enable the site with
a2ensite and restart Apache::

    htpasswd -c /etc/pov/fridge.passwd username
    a2enmod ssl rewrite
    # skipping SSL cert setup: too long
    a2ensite $(hostname -f)
    apache2ctl configtest && apache2ctl graceful

"""

import ConfigParser
import datetime
import errno
import optparse
import os
import sys

from mako.lookup import TemplateLookup


debian_package = (__file__ == '/usr/sbin/pov-update-server-page')


if debian_package:
    DEFAULT_CONFIG_FILE = '/etc/pov/server-page.conf'
    TEMPLATE_DIR = '/usr/share/pov-server-page/'
    COLLECTION_CGI = '/usr/lib/pov-server-page/collection.cgi'
    UPDATE_TCP_PORTS_SCRIPT = '/usr/lib/pov-server-page/update-ports'
    DEFAULT_AUTH_USER_FILE = '/etc/pov/fridge.passwd'
else:
    # running from source checkout
    here = os.path.abspath(os.path.dirname(__file__))
    DEFAULT_CONFIG_FILE = 'server-page.conf'
    TEMPLATE_DIR = os.path.join(here, 'templates')
    COLLECTION_CGI = os.path.join(here, 'collection.cgi')
    UPDATE_TCP_PORTS_SCRIPT = os.path.join(here, 'update_tcp_ports_html.py')
    DEFAULT_AUTH_USER_FILE = '/etc/pov/fridge.passwd'


def get_fqdn():
    """Return the fully-qualified hostname."""
    # socket.getfqdn() likes to get confused on Ubuntu and return
    # 'localhost6.localdomain' etc.
    return os.popen("hostname -f").read().strip()


def mkdir_with_parents(dirname):
    """Create a directory and all parent directories.

    Does nothing if the directory already exists.

    Returns True if the directory was created, False if it already existed.
    """
    try:
        os.makedirs(dirname)
    except OSError, e:
        if e.errno == errno.EEXIST and os.path.isdir(dirname):
            return False
        else:
            raise
    return True


def replace_file(filename, marker, new_contents):
    """Safely replace a file's contents.

    Creates the file if it didn't exist.

    Check that the file contains a marker before overwriting
    (so that only explicitly marked autogenerated files will be
    overwritten).

    Doesn't write if the file already has the right contents.

    Returns True if the file was created or overwritten, False if it was
    already up to date.
    """
    assert marker in new_contents
    try:
        with open(filename) as f:
            old_contents = f.read()
            if old_contents == new_contents:
                return False
            if marker not in old_contents:
                raise Error('Refusing to overwrite %s' % filename)
    except IOError, e:
        if e.errno == errno.ENOENT:
            pass
        else:
            raise
    mkdir_with_parents(os.path.dirname(filename))
    with open(filename, 'w') as f:
        f.write(new_contents)
    return True


class Error(Exception):
    pass


HTML_MARKER = '<!-- generated by pov-update-server-page -->'
CONFIG_MARKER = '# generated by pov-update-server-page'


class Builder(object):

    defaults = dict(
        HOSTNAME=get_fqdn(),
        COLLECTION_CGI=COLLECTION_CGI,
        UPDATE_TCP_PORTS_SCRIPT=UPDATE_TCP_PORTS_SCRIPT,
        AUTH_USER_FILE=DEFAULT_AUTH_USER_FILE,
        INCLUDE='',
        APACHE_EXTRA_CONF='',
    )

    # sub-builders

    class Directory(object):
        def build(self, filename, builder):
            if mkdir_with_parents(filename) and builder.verbose:
                print("Created %s/" % filename)

    class Template(object):
        def __init__(self, template_name, marker=HTML_MARKER):
            self.template_name = template_name
            self.marker = marker

        def build(self, filename, builder):
            template = builder.lookup.get_template(self.template_name)
            new_contents = template.render(**builder.vars)
            builder.replace_file(filename, self.marker, new_contents)

    class ScriptOutput(object):
        def __init__(self, command, marker=HTML_MARKER):
            self.command = command
            self.marker = marker

        def build(self, filename, builder):
            command = self.command.format(**builder.vars)
            new_contents = os.popen(command).read()
            builder.replace_file(filename, self.marker, new_contents)

    # things to build

    build_list = [
        # (destination, subbuilder)
        ('/var/www/{HOSTNAME}/index.html',
             Template('index.html.in', HTML_MARKER)),
        ('/var/www/{HOSTNAME}/ports/index.html',
             ScriptOutput('{UPDATE_TCP_PORTS_SCRIPT} -H {HOSTNAME} -o /dev/stdout')),
        ('/var/log/apache2/{HOSTNAME}',
             Directory()),
        ('/etc/apache2/sites-available/{HOSTNAME}',
             Template('apache.conf.in', CONFIG_MARKER)),
    ]
    check_list = [
        ('/etc/apache2/mods-enabled/ssl.load', 'a2enmod ssl'),
        ('/etc/apache2/mods-enabled/rewrite.load', 'a2enmod rewrite'),
        ('/etc/apache2/sites-enabled/{HOSTNAME}', 'a2ensite {HOSTNAME}'),
        ('{AUTH_USER_FILE}', 'htpasswd -c {AUTH_USER_FILE} <username>')
    ]

    def __init__(self, vars, template_dir=TEMPLATE_DIR, destdir=''):
        self.vars = vars
        self.lookup = TemplateLookup(directories=[template_dir])
        self.destdir = destdir
        for name, value in self.defaults.items():
            self.vars.setdefault(name, value)

    @classmethod
    def from_config(cls, cp, section='pov-server-page',
                    template_dir=TEMPLATE_DIR, destdir=''):
        vars = dict((name, cp.get(section, name)) for name in cls.defaults)
        return cls(vars, template_dir, destdir)

    def _compute_derived(self):
        self.vars['SHORTHOSTNAME'] = self.vars['HOSTNAME'].partition('.')[0]
        self.vars['TIMESTAMP'] = str(datetime.datetime.now())

    def replace_file(self, destination, marker, new_contents):
        if marker not in new_contents:
            new_contents = marker + '\n' + new_contents
        if replace_file(destination, marker, new_contents) and self.verbose:
            print("Created %s" % destination)

    def build(self, verbose=False):
        self._compute_derived()
        self.verbose = verbose
        for destination, subbuilder in self.build_list:
            filename = self.destdir + destination.format(**self.vars)
            subbuilder.build(filename, self)

    def check(self):
        self._compute_derived()
        for target, command in self.check_list:
            filename = self.destdir + target.format(**self.vars)
            if not os.path.exists(filename):
                print("Please run %s" % command.format(**self.vars))


def main():
    # Command-line options
    description = "Generate Apache configuration for a server page"
    parser = optparse.OptionParser('usage: %prog [options] [var=value ...]',
                                   description=description)
    parser.add_option('-v', '--verbose', action='store_true')
    parser.add_option('--no-checks', action='store_false', dest='checks',
                      default=True)
    parser.add_option('-c', '--config-file', default=DEFAULT_CONFIG_FILE)
    parser.add_option('--destdir', default='')
    opts, args = parser.parse_args()
    # Config file parsing
    cp = ConfigParser.SafeConfigParser(dict(
        enabled=False,
        **Builder.defaults
    ))
    if not cp.read([opts.config_file]):
        sys.exit("Could not read %s" % opts.config_file)
    # Command-line overrides
    for arg in args:
        name, _, value = arg.partition('=')
        cp.set('pov-server-page', name, value)
    # Enabled?
    enabled = cp.getboolean('pov-server-page', 'enabled')
    if not enabled:
        if opts.verbose:
            print("Disabled in the config file, quitting.")
        return
    # Build /var/www/{hostname} and /etc/apache2/sites-available/
    builder = Builder.from_config(cp, destdir=opts.destdir)
    try:
        builder.build(verbose=opts.verbose)
        if opts.checks:
            builder.check()
    except Error, e:
        sys.exit(str(e))


if __name__ == '__main__':
    main()
