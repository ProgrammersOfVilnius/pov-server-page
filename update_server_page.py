#!/usr/bin/python
"""
Build a generic server page.  Useful for sysadmins.

Reads a configuration file (/etc/pov/server-page.conf by default) and creates
an Apache vhost in /etc/apache2/sites-enabled/{hostname}.conf, as well as a
static website in /var/www/{hostname}.

For full setup you also need to create the directory for Apache logs, enable
mod_rewrite, mod_ssl, make sure your Apache is listening on port 443, set up an
SSL certificate, set up a password file with htpasswd, enable the site with
a2ensite and restart Apache::

    htpasswd -c /etc/pov/fridge.passwd username
    a2enmod ssl rewrite
    # skipping SSL cert setup: too long
    a2ensite $(hostname -f).conf
    service apache2 reload

"""

import ConfigParser
import datetime
import errno
import glob
import grp
import optparse
import os
import pwd
import stat
import subprocess
import sys
import time

from mako.lookup import TemplateLookup


debian_package = (__file__ == '/usr/sbin/pov-update-server-page')


if debian_package:
    DEFAULT_CONFIG_FILE = '/etc/pov/server-page.conf'
    DEFAULT_AUTH_USER_FILE = '/etc/pov/fridge.passwd'
    TEMPLATE_DIR = '/usr/share/pov-server-page/'
    libdir = '/usr/lib/pov-server-page'
    COLLECTION_CGI = os.path.join(libdir, 'collection.cgi')
    UPDATE_TCP_PORTS_SCRIPT = os.path.join(libdir, 'update-ports')
    CHANGELOG2HTML_SCRIPT = os.path.join(libdir, 'changelog2html')
    DU2WEBTREEMAP = os.path.join(libdir, 'du2webtreemap')
    WEBTREEMAP = os.path.join(TEMPLATE_DIR, 'webtreemap')
else:
    # running from source checkout
    here = os.path.abspath(os.path.dirname(__file__))
    DEFAULT_CONFIG_FILE = 'server-page.conf'
    DEFAULT_AUTH_USER_FILE = '/etc/pov/fridge.passwd'
    TEMPLATE_DIR = os.path.join(here, 'templates')
    COLLECTION_CGI = os.path.join(here, 'collection.cgi')
    UPDATE_TCP_PORTS_SCRIPT = os.path.join(here, 'update_tcp_ports_html.py')
    CHANGELOG2HTML_SCRIPT = os.path.join(here, 'changelog2html.py')
    DU2WEBTREEMAP = os.path.join(here, 'webtreemap-du', 'du2webtreemap.py')
    WEBTREEMAP = os.path.join(here, 'webtreemap')


def get_fqdn():
    """Return the fully-qualified hostname."""
    # socket.getfqdn() likes to get confused on Ubuntu and return
    # 'localhost6.localdomain' etc.
    return os.popen("hostname -f").read().strip()


def newer(file1, file2):
    """Is file1 newer than file2?

    Returns True if file2 doesn't exist.  file1 must exist.
    """
    mtime1 = os.stat(file1).st_mtime
    try:
        mtime2 = os.stat(file2).st_mtime
    except OSError, e:
        if e.errno == errno.ENOENT:
            return True
        else:
            raise
    return mtime1 > mtime2


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


def symlink(target, filename):
    """Create a symlink named filename that points to target.

    Does nothing if the symlink already exists.
    """
    try:
        os.symlink(target, filename)
    except OSError, e:
        if e.errno == errno.EEXIST and os.path.islink(filename) and os.readlink(filename) == target:
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


def pipeline(*args, **kwargs):
    """Construct a shell pipeline."""
    stdout = kwargs.pop('stdout', None)
    assert not kwargs
    children = []
    for n, command in enumerate(args):
        p = subprocess.Popen(
            command,
            stdin=children[-1].stdout if children else None,
            stdout=stdout if n == len(args) - 1 else subprocess.PIPE)
        children.append(p)
    for child in children:
        child.wait()


class Error(Exception):
    pass


HTML_MARKER = '<!-- generated by pov-update-server-page -->'
CONFIG_MARKER = '# generated by pov-update-server-page'


class Builder(object):

    section = 'pov-server-page'

    defaults = dict(
        ENABLED=False,
        HOSTNAME=get_fqdn(),
        SERVER_ALIASES='',
        CANONICAL_REDIRECT=True,
        COLLECTION_CGI=COLLECTION_CGI,
        UPDATE_TCP_PORTS_SCRIPT=UPDATE_TCP_PORTS_SCRIPT,
        AUTH_USER_FILE=DEFAULT_AUTH_USER_FILE,
        INCLUDE='',
        APACHE_EXTRA_CONF='',
        EXTRA_LINKS='',
        DISK_USAGE='',
        DISK_USAGE_DELETE_OLD=True,
        DISK_USAGE_KEEP_DAILY=60,
        DISK_USAGE_KEEP_MONTHLY=12,
        DISK_USAGE_KEEP_YEARLY=5,
        SKIP='',
        REDIRECT='',
    )

    # sub-builders

    class Directory(object):
        def build(self, filename, builder):
            if mkdir_with_parents(filename) and builder.verbose:
                print("Created %s/" % filename)

    class Symlink(object):
        def __init__(self, target):
            self.target = target

        def build(self, filename, builder):
            mkdir_with_parents(os.path.dirname(filename))
            if symlink(self.target, filename) and builder.verbose:
                print("Created %s" % filename)

    class Template(object):
        def __init__(self, template_name, marker=HTML_MARKER):
            self.template_name = template_name
            self.marker = marker

        def build(self, filename, builder, extra_vars=None):
            template = builder.lookup.get_template(self.template_name)
            if extra_vars:
                kw = builder.vars.copy()
                kw.update(extra_vars)
            else:
                kw = builder.vars
            new_contents = template.render(**kw).encode('UTF-8')
            builder.replace_file(filename, self.marker, new_contents)

    class ScriptOutput(object):
        def __init__(self, command, marker=HTML_MARKER):
            self.command = command
            self.marker = marker

        def build(self, filename, builder):
            command = self.command.format(**builder.vars)
            new_contents = os.popen(command).read()
            builder.replace_file(filename, self.marker, new_contents)

    class DiskUsage(object):
        def location_name(self, location):
            # mimic collectd's mangling
            # '/apps' -> 'apps'
            # '/' -> 'root'
            # '/var/log' -> 'var-log'
            return location.lstrip('/').replace('/', '-') or 'root'

        def disk_graph_url(self, location, timespan='trend'):
            if self.has_disk_graph_v5(location):
                return self.disk_graph_url_v5(location, timespan)
            else:
                return self.disk_graph_url_v4(location, timespan)

        def disk_graph_url_v4(self, location, timespan='trend'):
            return ('/stats/{hostname}?action=show_graph;'
                    'host={collectd_hostname};plugin=df;type=df;'
                    'type_instance={location_name};timespan={timespan}'.format(
                        hostname=self.hostname,
                        collectd_hostname=self.collectd_hostname,
                        location_name=self.location_name(location),
                        timespan=timespan))

        def disk_graph_url_v5(self, location, timespan='trend'):
            return ('/stats/{hostname}?action=show_graph;'
                    'host={collectd_hostname};plugin=df;type=df_complex;'
                    'plugin_instance={location_name};timespan={timespan}'.format(
                        hostname=self.hostname,
                        collectd_hostname=self.collectd_hostname,
                        location_name=self.location_name(location),
                        timespan=timespan))

        def has_disk_graph(self, location):
            return (self.has_disk_graph_v4(location) or
                    self.has_disk_graph_v5(location))

        def has_disk_graph_v4(self, location):
            return os.path.exists('/var/lib/collectd/rrd/%s/df/df-%s.rrd' %
                                  (self.collectd_hostname,
                                   self.location_name(location)))

        def has_disk_graph_v5(self, location):
            return os.path.exists('/var/lib/collectd/rrd/%s/df-%s/df_complex-used.rrd' %
                                  (self.collectd_hostname,
                                   self.location_name(location)))

        @classmethod
        def get_all_locations(cls):
            locations = []
            for line in os.popen("df -PT").readlines()[1:]:
                bits = line.split()
                # device, type, size, used, free, %, mountpoint
                fstype = bits[1]
                mountpoint = bits[-1]
                if fstype not in ('tmpfs', 'devtmpfs', 'ecryptfs', 'nfs'):
                    locations.append(mountpoint)
            return locations

        @classmethod
        def parse(cls, disk_usage):
            locations = disk_usage.split()
            if locations == ['all']:
                locations = cls.get_all_locations()
            return locations

        def build(self, dirname, builder):
            locations = builder.vars['DISK_USAGE_LIST']
            if not locations:
                return
            delete_old = builder.vars['DISK_USAGE_DELETE_OLD']
            keep_daily = builder.vars['DISK_USAGE_KEEP_DAILY']
            keep_monthly = builder.vars['DISK_USAGE_KEEP_MONTHLY']
            keep_yearly = builder.vars['DISK_USAGE_KEEP_YEARLY']
            self.collectd_hostname = get_fqdn()
            self.hostname = builder.vars['SHORTHOSTNAME']
            index_html = os.path.join(dirname, 'index.html')
            Builder.Template('du.html.in').build(
                index_html, builder,
                extra_vars=dict(location_name=self.location_name,
                                has_disk_graph=self.has_disk_graph,
                                disk_graph_url=self.disk_graph_url))
            webtreemap = os.path.join(dirname, 'webtreemap')
            Builder.Symlink(WEBTREEMAP).build(webtreemap, builder)
            today = time.strftime('%Y-%m-%d')
            for location in locations:
                location_name = self.location_name(location)
                datadir = os.path.join(dirname, location_name)
                if delete_old:
                    if builder.verbose:
                        print('Deleting old snapshots in %s' % datadir)
                    self.delete_old_files(datadir, keep_daily,
                                          keep_monthly, keep_yearly)
                du_file = os.path.join(datadir, 'du-%s.gz' % today)
                js_file = os.path.join(datadir, 'du.js')
                index_html = os.path.join(datadir, 'index.html')
                if not os.path.exists(du_file):
                    if builder.verbose:
                        print('Creating %s' % du_file)
                    mkdir_with_parents(datadir)
                    started = time.time()
                    with open(du_file, 'wb') as f:
                        pipeline(['du', '-x', location], ['gzip'], stdout=f)
                    duration = time.time() - started
                    need_build = True
                else:
                    duration = 0 # sadly, unknown
                    need_build = newer(du_file, js_file)
                if need_build:
                    if builder.verbose:
                        print('Creating %s' % js_file)
                    with open(js_file, 'w') as f:
                        pipeline(['zcat', du_file], [DU2WEBTREEMAP], stdout=f)
                        timestamp = time.strftime('%Y-%m-%d %H:%M:%S %z')
                        f.write('\nvar last_updated = "%s";\n' % timestamp)
                        f.write('var duration = "%.0f";\n' % duration)
                Builder.Template('du-page.html.in').build(
                    index_html, builder,
                    extra_vars=dict(location=location,
                                    location_name=self.location_name,
                                    has_disk_graph=self.has_disk_graph,
                                    disk_graph_url=self.disk_graph_url))

        def delete_old_files(self, datadir, keep_daily, keep_monthly,
                             keep_yearly):
            files = glob.glob(os.path.join(datadir, 'du-????-??-??.gz'))
            keep = self.files_to_keep(files, keep_daily, keep_monthly, keep_yearly)
            delete = set(files) - keep
            for fn in sorted(delete):
                os.unlink(fn)

        @staticmethod
        def files_to_keep(files, keep_daily=0, keep_monthly=0, keep_yearly=0):
            files = sorted(files)
            keep = set()
            if keep_daily:
                keep.update(files[-keep_daily:])
            if keep_monthly or keep_yearly:
                monthly = {}
                yearly = {}
                for fn in files:
                    date = os.path.basename(fn)[len('du-'):-len('.gz')]
                    monthly.setdefault(date[:4+1+2], fn)
                    yearly.setdefault(date[:4], fn)
                if keep_monthly:
                    keep.update(fn for date, fn in
                                sorted(monthly.items())[-keep_monthly:])
                if keep_yearly:
                    keep.update(fn for date, fn in
                                sorted(yearly.items())[-keep_yearly:])
            return keep

    # things to build

    build_list = [
        # (destination, subbuilder)
        ('/var/www/{HOSTNAME}/index.html',
         Template('index.html.in', HTML_MARKER)),
        ('/var/www/{HOSTNAME}/ports/index.html',
         ScriptOutput('{UPDATE_TCP_PORTS_SCRIPT} -H {HOSTNAME} -o /dev/stdout')),
        ('/var/www/{HOSTNAME}/ssh/index.html',
         Template('ssh.html.in', HTML_MARKER)),
        ('/var/www/{HOSTNAME}/du',
         DiskUsage()),
        ('/var/log/apache2/{HOSTNAME}',
         Directory()),
        ('/etc/apache2/sites-available/{HOSTNAME}.conf',
         Template('apache.conf.in', CONFIG_MARKER)),
    ]
    check_list = [
        ('/etc/apache2/mods-enabled/ssl.load', 'a2enmod ssl'),
        ('/etc/apache2/mods-enabled/rewrite.load', 'a2enmod rewrite'),
        ('/etc/apache2/mods-enabled/wsgi.load', 'a2enmod wsgi'),
        ('/etc/apache2/mods-enabled/cgid.load', 'a2enmod cgid'),
        ('/etc/apache2/sites-enabled/{HOSTNAME}.conf', 'a2ensite {HOSTNAME}.conf'),
        ('{AUTH_USER_FILE}', 'htpasswd -c {AUTH_USER_FILE} <username>')
    ]

    def __init__(self, vars, template_dir=TEMPLATE_DIR, destdir='', verbose=False):
        self.verbose = verbose
        self.vars = vars
        self.lookup = TemplateLookup(directories=[template_dir])
        self.destdir = destdir
        for name, value in self.defaults.items():
            self.vars.setdefault(name, value)
        self.needs_apache_reload = False

    @classmethod
    def ConfigParser(cls, **extra):
        cp = ConfigParser.SafeConfigParser()
        cp.add_section(cls.section)
        for name, value in cls.defaults.items():
            cp.set(cls.section, name, str(value))
        return cp

    @classmethod
    def from_config(cls, cp, section=None, template_dir=TEMPLATE_DIR,
                    destdir=''):
        if not section:
            section = cls.section
        vars = dict(
            (name,
             cp.getboolean(section, name) if isinstance(default, bool) else
             cp.getint(section, name) if isinstance(default, int) else
             cp.get(section, name))
            for name, default in cls.defaults.items())
        return cls(vars, template_dir, destdir)

    def _compute_derived(self):
        self.vars['SHORTHOSTNAME'] = self.vars['HOSTNAME'].partition('.')[0]
        self.vars['TIMESTAMP'] = str(datetime.datetime.now())
        self.vars['SERVER_ALIAS_LIST'] = self.vars['SERVER_ALIASES'].split()
        self.vars['DISK_USAGE_LIST'] = self.DiskUsage.parse(self.vars['DISK_USAGE'])
        self.vars['EXTRA_LINKS_MAP'] = self.parse_pairs(self.vars['EXTRA_LINKS'])
        self.vars['CHANGELOG2HTML_SCRIPT'] = CHANGELOG2HTML_SCRIPT
        self.vars['CHANGELOG'] = self.file_readable_to('/root/Changelog',
                                                       'www-data',
                                                       'www-data')
        if self.verbose and not self.vars['CHANGELOG']:
            print("Skipping changelog view since /root/Changelog is not readable by user www-data")

    def file_readable_to(self, filename, user, group):
        try:
            uid = pwd.getpwnam(user).pw_uid
        except KeyError:
            uid = -1
        try:
            gid = grp.getgrnam(user).gr_gid
        except KeyError:
            gid = -1
        if not self.can_read(filename, uid, gid):
            return False
        dirname = os.path.dirname(filename)
        while True:
            if not self.can_execute(dirname, uid, gid):
                return False
            pardir = os.path.dirname(dirname)
            if pardir == dirname:
                return True
            dirname = pardir

    def can_read(self, filename, uid, gid):
        try:
            st = os.stat(filename)
        except OSError:
            return False
        if st.st_uid == uid and stat.S_IMODE(st.st_mode) & stat.S_IRUSR:
            return True
        if st.st_gid == gid and stat.S_IMODE(st.st_mode) & stat.S_IRGRP:
            return True
        return stat.S_IMODE(st.st_mode) & stat.S_IROTH

    def can_execute(self, filename, uid, gid):
        try:
            st = os.stat(filename)
        except OSError:
            return False
        if st.st_uid == uid and stat.S_IMODE(st.st_mode) & stat.S_IXUSR:
            return True
        if st.st_gid == gid and stat.S_IMODE(st.st_mode) & stat.S_IXGRP:
            return True
        return stat.S_IMODE(st.st_mode) & stat.S_IXOTH

    def replace_file(self, destination, marker, new_contents):
        if marker not in new_contents:
            new_contents = marker + '\n' + new_contents
        if replace_file(destination, marker, new_contents) and self.verbose:
            print("Created %s" % destination)
            if destination.startswith('/etc/apache2'):
                self.needs_apache_reload = True

    def parse_pairs(self, value):
        result = []
        for line in value.splitlines():
            line = line.strip()
            if ' = ' in line:
                source, destination = line.split(' = ', 1)
            elif '=' in line:
                source, destination = line.split('=', 1)
            else:
                continue
            result.append((source.strip(), destination.strip()))
        return result

    def parse_map(self, value):
        return dict(self.parse_pairs(value))

    def build(self, verbose=None):
        if verbose is not None:
            self.verbose = verbose
        self._compute_derived()
        skip = self.vars['SKIP'].split()
        redirect = self.parse_map(self.vars['REDIRECT'])
        for destination, subbuilder in self.build_list:
            filename = self.destdir + destination.format(**self.vars)
            if filename not in skip:
                if filename in redirect:
                    filename = redirect[filename]
                subbuilder.build(filename, self)
            elif self.verbose:
                print("Skipping %s" % filename)

    def check(self):
        self._compute_derived()
        for target, command in self.check_list:
            filename = self.destdir + target.format(**self.vars)
            if not os.path.exists(filename):
                print("Please run %s" % command.format(**self.vars))
        if self.needs_apache_reload:
            print("Please run service apache2 reload")


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
    cp = Builder.ConfigParser()
    if not cp.read([opts.config_file]):
        sys.exit("Could not read %s" % opts.config_file)
    # Command-line overrides
    for arg in args:
        name, _, value = arg.partition('=')
        cp.set(Builder.section, name, value)
    # Enabled?
    enabled = cp.getboolean(Builder.section, 'enabled')
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
