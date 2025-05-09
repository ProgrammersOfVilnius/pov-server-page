# -*- coding: utf-8 -*-
import errno
import getpass
import grp
import os
import random
import shutil
import sys
import tempfile
import time
import unittest

try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

import mock
import pytest

from pov_server_page.update_server_page import (
    CHANGELOG2HTML_SCRIPT,
    HTML_MARKER,
    Builder,
    Error,
    get_fqdn,
    main,
    mkdir_with_parents,
    newer,
    pipeline,
    replace_file,
    symlink,
)


class FilesystemTests(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='pov-update-server-page-test-')
        self.addCleanup(shutil.rmtree, self.tmpdir)

    def patch(self, *args, **kw):
        patcher = mock.patch(*args, **kw)
        retval = patcher.start()
        self.addCleanup(patcher.stop)
        return retval

    def raise_oserror(self, *args):
        raise OSError(errno.EACCES, 'cannot access parent directory')

    def raise_ioerror(self, *args):
        raise IOError(errno.EACCES, 'cannot access parent directory')


class TestNewer(FilesystemTests):

    def setUp(self):
        FilesystemTests.setUp(self)
        self.file1 = os.path.join(self.tmpdir, 'file1')
        self.file2 = os.path.join(self.tmpdir, 'file2')
        self.stamp = time.time() - 1
        self.touch(self.file1, self.stamp)
        self.real_stat = os.stat

    def touch(self, filename, stamp=None):
        with open(filename, 'ab'):
            pass
        if stamp:
            os.utime(filename, (stamp, stamp))

    def test_newer_file1_is_newer_than_file2(self):
        self.touch(self.file2, self.stamp - 1)
        self.assertTrue(newer(self.file1, self.file2))

    def test_newer_file1_is_older_than_file2(self):
        self.touch(self.file2, self.stamp + 1)
        self.assertFalse(newer(self.file1, self.file2))

    def test_newer_file1_is_same_age_as_file2(self):
        self.touch(self.file2, self.stamp)
        self.assertFalse(newer(self.file1, self.file2))

    def test_newer_file2_does_not_exist(self):
        self.assertTrue(newer(self.file1, self.file2))

    def _fake_stat(self, filename):
        if filename == self.file2:
            self.raise_oserror(filename)
        else:
            return self.real_stat(filename)

    def test_newer_file2_raises_some_error(self):
        with mock.patch('os.stat', self._fake_stat):
            with self.assertRaises(OSError):
                self.assertTrue(newer(self.file1, self.file2))


class TestMkdir(FilesystemTests):

    def test_mkdir_with_parents_when_doesnt_exist(self):
        path = os.path.join(self.tmpdir, 'a', 'b', 'c')
        rv = mkdir_with_parents(path)
        self.assertTrue(os.path.isdir(path))
        self.assertTrue(rv)

    def test_mkdir_with_parents_when_already_exists(self):
        rv = mkdir_with_parents(self.tmpdir)
        self.assertFalse(rv)

    def test_mkdir_with_parents_when_cannot(self):
        with mock.patch('os.makedirs', self.raise_oserror):
            with self.assertRaises(OSError):
                mkdir_with_parents(self.tmpdir)


class TestSymlink(FilesystemTests):

    def setUp(self):
        FilesystemTests.setUp(self)
        self.stderr = self.patch('sys.stderr', StringIO())

    def test_symlink(self):
        a = os.path.join(self.tmpdir, 'a')
        b = os.path.join(self.tmpdir, 'b')
        rv = symlink(a, b)
        self.assertTrue(rv)
        self.assertTrue(os.path.islink(b))
        self.assertEqual(os.readlink(b), a)

    def test_symlink_already_exists(self):
        a = os.path.join(self.tmpdir, 'a')
        b = os.path.join(self.tmpdir, 'b')
        symlink(a, b)
        rv = symlink(a, b)
        self.assertFalse(rv)

    def test_symlink_error(self):
        a = os.path.join(self.tmpdir, 'a')
        b = os.path.join(self.tmpdir, 'b')
        with mock.patch('os.symlink', self.raise_oserror):
            with self.assertRaises(OSError):
                symlink(a, b)
        self.assertIn("Couldn't create symlink", self.stderr.getvalue())

    def test_symlink_no_overwriting(self):
        a = os.path.join(self.tmpdir, 'a')
        b = os.path.join(self.tmpdir, 'b')
        symlink(a, b)
        c = os.path.join(self.tmpdir, 'c')
        with self.assertRaises(Error):
            symlink(c, b)


class TestReplaceFile(FilesystemTests):

    def test_replace_file_creates_new_file(self):
        fn = os.path.join(self.tmpdir, 'file.txt')
        new_contents = b'New contents (with @MARKER@)'
        rv = replace_file(fn, b'@MARKER@', new_contents)
        with open(fn, 'rb') as f:
            self.assertEqual(f.read(), new_contents)
        self.assertTrue(rv)

    def test_replace_file_replaces_file(self):
        fn = os.path.join(self.tmpdir, 'file.txt')
        with open(fn, 'wb') as f:
            f.write(b'Old contents (with @MARKER@)')
        new_contents = b'New contents (with @MARKER@)'
        rv = replace_file(fn, b'@MARKER@', new_contents)
        with open(fn, 'rb') as f:
            self.assertEqual(f.read(), new_contents)
        self.assertTrue(rv)

    def test_replace_file_keeps_same_file(self):
        fn = os.path.join(self.tmpdir, 'file.txt')
        old_contents = b'Old contents (with @MARKER@)'
        with open(fn, 'wb') as f:
            f.write(old_contents)
        rv = replace_file(fn, b'@MARKER@', old_contents)
        with open(fn, 'rb') as f:
            self.assertEqual(f.read(), old_contents)
        self.assertFalse(rv)

    def test_replace_file_leaves_file_alone(self):
        fn = os.path.join(self.tmpdir, 'file.txt')
        old_contents = b'Old contents (without a marker)'
        with open(fn, 'wb') as f:
            f.write(old_contents)
        with self.assertRaises(Error):
            replace_file(fn, b'@MARKER@', b'New contents (with @MARKER@)')
        with open(fn, 'rb') as f:
            self.assertEqual(f.read(), old_contents)

    def test_replace_file_error(self):
        fn = os.path.join(self.tmpdir, 'file.txt')
        with mock.patch('pov_server_page.update_server_page.open', self.raise_ioerror):
            with self.assertRaises(IOError):
                replace_file(fn, b'@MARKER@', b'New contents (with @MARKER@)')


class TestPipeline(FilesystemTests):

    def test_pipeline(self):
        fn = os.path.join(self.tmpdir, 'outfile')
        with open(fn, 'w') as f:
            pipeline(['printf', '%s\n', 'aaa', 'aab', 'bbc'],
                     ['grep', '^a'],
                     ['sort', '-r'], stdout=f)
        with open(fn, 'r') as f:
            self.assertEqual(f.readlines(), ['aab\n', 'aaa\n'])


class BuilderTests(FilesystemTests):

    def setUp(self):
        FilesystemTests.setUp(self)
        self.stdout = self.patch('sys.stdout', StringIO())
        self.stderr = self.patch('sys.stderr', StringIO())
        self.builder = Builder({'foo': 'two', 'HOSTNAME': 'frog.example.com'},
                               destdir=self.tmpdir)
        self.builder.verbose = True
        self.builder.skip = []
        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        self.builder.html_lookup.directories.append(os.path.normpath(template_dir))
        self.builder.lookup.directories.append(os.path.normpath(template_dir))


class TestBuilders(BuilderTests):

    def test_Directory(self):
        dirname = os.path.join(self.tmpdir, 'subdir')
        Builder.Directory().build(dirname, self.builder)
        self.assertEqual(self.stdout.getvalue(),
                         "Created %s/subdir/\n" % self.tmpdir)
        self.assertTrue(os.path.isdir(dirname))

    def test_Symlink(self):
        pathname = os.path.join(self.tmpdir, 'subdir', 'symlink')
        Builder.Symlink('/dev/null').build(pathname, self.builder)
        self.assertEqual(self.stdout.getvalue(),
                         "Created %s/subdir/symlink\n" % self.tmpdir)
        self.assertTrue(os.path.islink(pathname))
        self.assertEqual(os.readlink(pathname), '/dev/null')

    def test_Symlink_skips(self):
        pathname = os.path.join(self.tmpdir, 'subdir', 'symlink')
        self.builder.skip.append(pathname)
        Builder.Symlink('/dev/null').build(pathname, self.builder)
        self.assertEqual(self.stdout.getvalue(),
                         "Skipping %s/subdir/symlink\n" % self.tmpdir)
        self.assertFalse(os.path.exists(pathname))

    def test_Template(self):
        pathname = os.path.join(self.tmpdir, 'subdir', 'index.html')
        Builder.Template('test.html.in').build(pathname, self.builder)
        with open(pathname, 'rb') as f:
            self.assertEqual(f.read(),
                             HTML_MARKER + b'\n<p>This is a test template.\n')
        self.assertEqual(self.stdout.getvalue(),
                         "Created %s/subdir/index.html\n" % self.tmpdir)

    def test_Template_with_extra_vars(self):
        pathname = os.path.join(self.tmpdir, 'subdir', 'index.html')
        Builder.Template('test-vars.html.in').build(pathname, self.builder,
                                                    extra_vars=dict(pi='3.14'))
        with open(pathname, 'rb') as f:
            self.assertEqual(f.read(),
                             HTML_MARKER + b'\n<p>pi ~= 3.14\n')
        self.assertEqual(self.stdout.getvalue(),
                         "Created %s/subdir/index.html\n" % self.tmpdir)


class TestDiskUsageBuilderHelpers(unittest.TestCase):

    def setUp(self):
        self.builder = Builder.DiskUsage()
        self.builder.collectd_hostname = 'frog.example.com'
        self.builder.hostname = 'frog'

    def test_location_name(self):
        location_name = self.builder.location_name
        self.assertEqual(location_name('/var/log'), 'var-log')
        self.assertEqual(location_name('/apps'), 'apps')
        self.assertEqual(location_name('/root'), 'root')
        self.assertEqual(location_name('/'), 'root')

    def test_disk_graph_url_when_v5_exists(self):
        disk_graph_url = self.builder.disk_graph_url
        disk_graph_url_v5 = self.builder.disk_graph_url_v5
        self.builder.has_disk_graph_v4 = lambda location: False
        self.builder.has_disk_graph_v5 = lambda location: True
        self.assertEqual(disk_graph_url('/var/log', 'week'),
                         disk_graph_url_v5('/var/log', 'week'))

    def test_disk_graph_url_when_v5_does_not_exist(self):
        disk_graph_url = self.builder.disk_graph_url
        disk_graph_url_v4 = self.builder.disk_graph_url_v4
        self.builder.has_disk_graph_v4 = lambda location: True
        self.builder.has_disk_graph_v5 = lambda location: False
        self.assertEqual(disk_graph_url('/var/log', 'week'),
                         disk_graph_url_v4('/var/log', 'week'))

    def test_disk_graph_url_v4(self):
        disk_graph_url = self.builder.disk_graph_url_v4
        self.assertEqual(disk_graph_url('/var/log', 'week'),
                         '/stats/frog?action=show_graph;host=frog.example.com;'
                         'plugin=df;type=df;type_instance=var-log;timespan=week')

    def test_disk_graph_url_v5(self):
        disk_graph_url = self.builder.disk_graph_url_v5
        self.assertEqual(disk_graph_url('/var/log', 'week'),
                         '/stats/frog?action=show_graph;host=frog.example.com;'
                         'plugin=df;type=df_complex;plugin_instance=var-log;timespan=week')

    def test_has_disk_graph_when_v4_exists(self):
        has_disk_graph = self.builder.has_disk_graph
        self.builder.has_disk_graph_v4 = lambda location: True
        self.builder.has_disk_graph_v5 = lambda location: False
        self.assertTrue(has_disk_graph('/var/log'))

    def test_has_disk_graph_when_v5_exists(self):
        has_disk_graph = self.builder.has_disk_graph
        self.builder.has_disk_graph_v4 = lambda location: False
        self.builder.has_disk_graph_v5 = lambda location: True
        self.assertTrue(has_disk_graph('/var/log'))

    def test_has_disk_graph_when_neither_exists(self):
        has_disk_graph = self.builder.has_disk_graph
        self.builder.has_disk_graph_v4 = lambda location: False
        self.builder.has_disk_graph_v5 = lambda location: False
        self.assertFalse(has_disk_graph('/var/log'))

    def test_has_disk_graph_v4(self):
        with mock.patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True
            self.assertTrue(self.builder.has_disk_graph_v4('/var/log'))
            mock_exists.assert_called_with(
                '/var/lib/collectd/rrd/frog.example.com/df/df-var-log.rrd')

    def test_has_disk_graph_v5(self):
        with mock.patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True
            self.assertTrue(self.builder.has_disk_graph_v5('/var/log'))
            mock_exists.assert_called_with(
                '/var/lib/collectd/rrd/frog.example.com/df-var-log/df_complex-used.rrd')

    def test_get_all_locations_real_df(self):
        locations = self.builder.get_all_locations()
        if '/' not in locations:
            # dear pytest please show this to me on failures:
            df_output = os.popen("df -PT --local -x debugfs").readlines()
            print(''.join(df_output))
            if len(df_output) == 2 and df_output[1].endswith('/dev/shm\n'):
                self.skipTest('no filesystems mounted in chroot')
        self.assertIn('/', locations)

    @mock.patch('os.popen')
    def test_get_all_locations_filtering(self, mock_popen):
        mock_popen().readlines.return_value = [
            "Failų sistema     Tipas    1024-blokų      Naud  Laisva Capacity Prijungta prie\n",
            "udev              devtmpfs    4010348   4010348       0     100% /dev\n",
            "tmpfs             tmpfs        805544     77484  728060      10% /run\n",
            "/dev/sda1         ext4      145561176 133199300 4944688      97% /\n",
            "tmpfs             tmpfs       4027704     66472 3961232       2% /dev/shm\n",
            "tmpfs             tmpfs          5120         4    5116       1% /run/lock\n",
            "tmpfs             tmpfs       4027704         0 4027704       0% /sys/fs/cgroup\n",
            "tmpfs             tmpfs        805544        16  805528       1% /run/user/120\n",
            "tmpfs             tmpfs        805544        88  805456       1% /run/user/1000\n",
            "/home/mg/.Private ecryptfs  145561176 133199300 4944688      97% /home/mg/Private\n",
            "pond:/files       nfs        12345678   1234567 1234567      12% /mnt/pub\n",
        ]
        locations = self.builder.get_all_locations()
        self.assertEqual(locations, ['/'])

    def test_parse_none(self):
        parse = Builder.DiskUsage.parse
        self.assertEqual(parse(''), [])

    def test_parse_some(self):
        parse = Builder.DiskUsage.parse
        self.assertEqual(parse('/ /srv /var/log'), ['/', '/srv', '/var/log'])

    @mock.patch.object(Builder.DiskUsage, 'get_all_locations',
                       return_value=['/', '/var'])
    def test_parse_all(self, *mocks):
        parse = Builder.DiskUsage.parse
        locations = parse('all')
        self.assertTrue('/' in locations, locations)
        self.assertFalse('all' in locations, locations)

    def test_files_to_keep(self):
        keep = Builder.DiskUsage.files_to_keep
        files = [
            '/var/www/example.com/du/var/du-2013-01-01.gz',
            '/var/www/example.com/du/var/du-2013-01-02.gz',
            '/var/www/example.com/du/var/du-2013-01-03.gz',
            '/var/www/example.com/du/var/du-2013-02-01.gz',
            '/var/www/example.com/du/var/du-2013-02-02.gz',
            '/var/www/example.com/du/var/du-2013-03-05.gz',
            '/var/www/example.com/du/var/du-2013-04-01.gz',
            '/var/www/example.com/du/var/du-2013-05-01.gz',
            '/var/www/example.com/du/var/du-2013-05-02.gz',
            '/var/www/example.com/du/var/du-2013-05-03.gz',
            '/var/www/example.com/du/var/du-2013-05-04.gz',
        ]
        random.shuffle(files)  # glob doesn't guarantee ordering
        kept = keep(files, keep_daily=0)
        self.assertEqual(kept, set([]))
        kept = keep(files, keep_daily=2)
        self.assertEqual(kept, set([
            '/var/www/example.com/du/var/du-2013-05-03.gz', # daily 2
            '/var/www/example.com/du/var/du-2013-05-04.gz', # daily 1
        ]))
        kept = keep(files, keep_monthly=3)
        self.assertEqual(kept, set([
            '/var/www/example.com/du/var/du-2013-03-05.gz', # monthly 3
            '/var/www/example.com/du/var/du-2013-04-01.gz', # monthly 2
            '/var/www/example.com/du/var/du-2013-05-01.gz', # monthly 1
        ]))
        kept = keep(files, keep_yearly=4)
        self.assertEqual(kept, set([
            '/var/www/example.com/du/var/du-2013-01-01.gz', # yearly 1
        ]))
        kept = keep(files, keep_daily=2, keep_monthly=3, keep_yearly=4)
        self.assertEqual(kept, set([
            '/var/www/example.com/du/var/du-2013-01-01.gz', # yearly 1
            '/var/www/example.com/du/var/du-2013-03-05.gz', # monthly 3
            '/var/www/example.com/du/var/du-2013-04-01.gz', # monthly 2
            '/var/www/example.com/du/var/du-2013-05-01.gz', # monthly 1
            '/var/www/example.com/du/var/du-2013-05-03.gz', # daily 2
            '/var/www/example.com/du/var/du-2013-05-04.gz', # daily 1
        ]))
        kept = keep(files, keep_daily=5, keep_monthly=5, keep_yearly=4)
        self.assertEqual(kept, set([
            '/var/www/example.com/du/var/du-2013-01-01.gz', # yearly 1, monthly 5
            '/var/www/example.com/du/var/du-2013-02-01.gz', # monthly 4
            '/var/www/example.com/du/var/du-2013-03-05.gz', # monthly 3
            '/var/www/example.com/du/var/du-2013-04-01.gz', # monthly 2, daily 5
            '/var/www/example.com/du/var/du-2013-05-01.gz', # monthly 1, daily 4
            '/var/www/example.com/du/var/du-2013-05-02.gz', # daily 3
            '/var/www/example.com/du/var/du-2013-05-03.gz', # daily 2
            '/var/www/example.com/du/var/du-2013-05-04.gz', # daily 1
        ]))


class TestDiskUsageBuilder(BuilderTests):

    def setUp(self):
        super(TestDiskUsageBuilder, self).setUp()
        self.builder.file_readable_to = lambda f, u, g: True
        self.builder._compute_derived()

    def test_build_none(self):
        self.builder.vars['DISK_USAGE_LIST'] = []
        Builder.DiskUsage().build(self.tmpdir, self.builder)
        self.assertEqual(self.stdout.getvalue(), "")

    def test_build_quick(self):
        self.builder.vars['DISK_USAGE_LIST'] = ['/pond']
        self.builder.quick = True
        Builder.DiskUsage().build(self.tmpdir, self.builder)
        self.assertNotIn('Deleting old snapshots', self.stdout.getvalue())
        self.assertNotIn('du.js', self.stdout.getvalue())

    @mock.patch('pov_server_page.update_server_page.pipeline')
    @mock.patch('pov_server_page.update_server_page.newer')
    @mock.patch('os.path.exists')
    def test_build_up_to_date(self, mock_exists, mock_newer, mock_pipeline):
        mock_exists.return_value = True
        mock_newer.return_value = False
        self.builder.vars['DISK_USAGE_LIST'] = ['/frog', '/pond']
        Builder.DiskUsage().build(os.path.join(self.tmpdir, 'du'), self.builder)
        self.assertEqual(
            self.stdout.getvalue().replace(self.tmpdir, '/var/www/frog.example.com'),
            "Created /var/www/frog.example.com/du/index.html\n"
            "Created /var/www/frog.example.com/du/webtreemap\n"
            "Deleting old snapshots in /var/www/frog.example.com/du/frog\n"
            "Created /var/www/frog.example.com/du/frog/index.html\n"
            "Deleting old snapshots in /var/www/frog.example.com/du/pond\n"
            "Created /var/www/frog.example.com/du/pond/index.html\n"
        )
        self.assertEqual(mock_pipeline.call_count, 0)

    @mock.patch('time.strftime', lambda fmt: '2015-11-01')
    @mock.patch('pov_server_page.update_server_page.pipeline')
    @mock.patch('os.path.exists')
    def test_build_fresh(self, mock_exists, mock_pipeline):
        mock_exists.return_value = False
        self.builder.vars['DISK_USAGE_LIST'] = ['/frog']
        self.builder.vars['DISK_USAGE_DELETE_OLD'] = False
        Builder.DiskUsage().build(os.path.join(self.tmpdir, 'du'), self.builder)
        self.assertEqual(
            self.stdout.getvalue().replace(self.tmpdir, '/var/www/frog.example.com'),
            "Created /var/www/frog.example.com/du/index.html\n"
            "Created /var/www/frog.example.com/du/webtreemap\n"
            "Creating /var/www/frog.example.com/du/frog/du-2015-11-01.gz\n"
            "Creating /var/www/frog.example.com/du/frog/du.js\n"
            "Created /var/www/frog.example.com/du/frog/index.html\n"
        )
        self.assertEqual(mock_pipeline.call_count, 2)

    @mock.patch('time.strftime', lambda fmt: '2015-11-01')
    @mock.patch('pov_server_page.update_server_page.pipeline')
    @mock.patch('os.path.exists', lambda what: what == '/usr/bin/ionice')
    def test_build_fresh_ionice(self, mock_pipeline):
        self.builder.vars['DISK_USAGE_LIST'] = ['/frog']
        self.builder.vars['DISK_USAGE_DELETE_OLD'] = False
        Builder.DiskUsage().build(os.path.join(self.tmpdir, 'du'), self.builder)
        self.assertEqual(
            self.stdout.getvalue().replace(self.tmpdir, '/var/www/frog.example.com'),
            "Created /var/www/frog.example.com/du/index.html\n"
            "Created /var/www/frog.example.com/du/webtreemap\n"
            "Creating /var/www/frog.example.com/du/frog/du-2015-11-01.gz\n"
            "Creating /var/www/frog.example.com/du/frog/du.js\n"
            "Created /var/www/frog.example.com/du/frog/index.html\n"
        )
        self.assertEqual(mock_pipeline.call_count, 2)

    @mock.patch('os.unlink')
    @mock.patch('glob.glob')
    def test_delete_old_files(self, mock_glob, mock_unlink):
        mock_glob.return_value = ['du-2015-11-03.gz', 'du-2015-11-02.gz']
        Builder.DiskUsage().delete_old_files(self.tmpdir, keep_daily=1, keep_monthly=0, keep_yearly=0)
        mock_unlink.assert_called_once_with('du-2015-11-02.gz')


class TestBuilderConstruction(unittest.TestCase):

    def test_Builder(self):
        Builder() # should not raise

    def test_Builder_from_config_all_defaults(self):
        cp = Builder.ConfigParser()
        Builder.from_config(cp) # should not raise


class TestBuilderParseHelpers(unittest.TestCase):

    def test_parse_pairs(self):
        parse_pairs = Builder().parse_pairs
        self.assertEqual(parse_pairs(""), [])
        self.assertEqual(parse_pairs("a=b"), [("a", "b")])
        self.assertEqual(parse_pairs(" a = b "), [("a", "b")])
        self.assertEqual(parse_pairs("a=b\nc = d"), [("a", "b"), ("c", "d")])

    def test_parse_pairs_ignore_everything_else(self):
        parse_pairs = Builder().parse_pairs
        self.assertEqual(parse_pairs("a=b\n# c\nd = e"),
                         [("a", "b"), ("d", "e")])

    def test_parse_pairs_embedded_equals(self):
        parse_pairs = Builder().parse_pairs
        self.assertEqual(parse_pairs("a = b = c"), [("a", "b = c")])
        self.assertEqual(parse_pairs("a=b = c"), [("a=b", "c")])
        self.assertEqual(parse_pairs("a = b=c"), [("a", "b=c")])
        self.assertEqual(parse_pairs("a=b=c"), [("a", "b=c")])

    def test_parse_map(self):
        parse_map = Builder().parse_map
        self.assertEqual(parse_map("a = b\nc = d"), {'a': 'b', 'c': 'd'})


class TestBuilderMotd(unittest.TestCase):

    def test_get_motd(self):
        get_motd = Builder().get_motd
        self.assertEqual(get_motd("/dev/null"), "")
        self.assertIsNone(get_motd("/no-such-file"))


class TestBuilderWithStdout(unittest.TestCase):

    def setUp(self):
        patcher = mock.patch('sys.stdout', StringIO())
        self.stdout = patcher.start()
        self.addCleanup(patcher.stop)

    @mock.patch('datetime.datetime')
    def test_compute_derived(self, mock_datetime):
        mock_datetime.now().__str__.return_value = '2015-11-01 14:35:03'
        builder = Builder({
            'HOSTNAME': 'frog.example.com',
            'SERVER_ALIASES': 'frog frog.lan',
            'DISK_USAGE': '/frog /pond',
            'EXTRA_LINKS': '/foo=also foo\n/bar=also bar',
        })
        builder.file_readable_to = lambda fn, u, g: True
        builder._compute_derived()
        self.assertEqual(builder.vars['SHORTHOSTNAME'], 'frog')
        self.assertEqual(builder.vars['TIMESTAMP'], '2015-11-01 14:35:03')
        self.assertEqual(builder.vars['SERVER_ALIAS_LIST'], ['frog', 'frog.lan'])
        self.assertEqual(builder.vars['EXTRA_LINKS_MAP'],
                         [('/foo', 'also foo'), ('/bar', 'also bar')])
        self.assertEqual(builder.vars['CHANGELOG2HTML_SCRIPT'], CHANGELOG2HTML_SCRIPT)
        self.assertTrue(builder.vars['CHANGELOG'])

    def test_compute_derived_warns_about_unreadable_changelog(self):
        builder = Builder()
        builder.verbose = True
        builder.file_readable_to = lambda fn, u, g: False
        builder._compute_derived()
        self.assertFalse(builder.vars['CHANGELOG'])
        self.assertEqual(self.stdout.getvalue(),
                         "Skipping changelog view since /root/Changelog is not readable by user www-data\n")


class TestBuilderFileReadability(unittest.TestCase):

    me = getpass.getuser()
    mygroup = grp.getgrgid(os.getgid()).gr_name

    def test_file_readable_to(self):
        builder = Builder()
        builder.can_read = lambda fn, u, g: True
        builder.can_execute = lambda fn, u, g: True
        file_readable_to = builder.file_readable_to
        self.assertTrue(file_readable_to(__file__, self.me, self.mygroup))

    def test_file_readable_to_bad_user(self):
        builder = Builder()
        builder.can_read = lambda fn, u, g: True
        builder.can_execute = lambda fn, u, g: True
        file_readable_to = builder.file_readable_to
        self.assertTrue(file_readable_to(__file__, 'no-such-user', self.mygroup))

    def test_file_readable_to_bad_group(self):
        builder = Builder()
        builder.can_read = lambda fn, u, g: True
        builder.can_execute = lambda fn, u, g: True
        file_readable_to = builder.file_readable_to
        self.assertTrue(file_readable_to(__file__, self.me, 'no-such-group'))

    def test_file_readable_when_not_readable(self):
        builder = Builder()
        builder.can_read = lambda fn, u, g: False
        file_readable_to = builder.file_readable_to
        self.assertFalse(file_readable_to(__file__, 'www-data', 'www-data'))

    def test_file_readable_when_parent_not_executable(self):
        builder = Builder()
        builder.can_execute = lambda fn, u, g: False
        file_readable_to = builder.file_readable_to
        self.assertFalse(file_readable_to(__file__, 'www-data', 'www-data'))

    @mock.patch('os.stat')
    def test_can_read_user_allows(self, mock_stat):
        mock_stat.return_value.st_uid = 1000
        mock_stat.return_value.st_gid = 1000
        mock_stat.return_value.st_mode = 0o100644
        can_read = Builder().can_read
        self.assertTrue(can_read('/root/Changelog', 1000, 100))

    @mock.patch('os.stat')
    def test_can_read_group_allows(self, mock_stat):
        mock_stat.return_value.st_uid = 0
        mock_stat.return_value.st_gid = 100
        mock_stat.return_value.st_mode = 0o100644
        can_read = Builder().can_read
        self.assertTrue(can_read('/root/Changelog', 1000, 100))

    @mock.patch('os.stat')
    def test_can_read_other_allows(self, mock_stat):
        mock_stat.return_value.st_uid = 0
        mock_stat.return_value.st_gid = 0
        mock_stat.return_value.st_mode = 0o100644
        can_read = Builder().can_read
        self.assertTrue(can_read('/root/Changelog', 1000, 100))

    @mock.patch('os.stat')
    def test_can_read_haha_cant(self, mock_stat):
        mock_stat.return_value.st_uid = 0
        mock_stat.return_value.st_gid = 100
        mock_stat.return_value.st_mode = 0o100600
        can_read = Builder().can_read
        self.assertFalse(can_read('/root/Changelog', 1000, 100))

    @mock.patch('os.stat')
    def test_can_read_haha_cant_even(self, mock_stat):
        mock_stat.side_effect = OSError("nope")
        can_read = Builder().can_read
        self.assertFalse(can_read('/root/Changelog', 1000, 100))

    @mock.patch('os.stat')
    def test_can_execute_user_allows(self, mock_stat):
        mock_stat.return_value.st_uid = 1000
        mock_stat.return_value.st_gid = 0
        mock_stat.return_value.st_mode = 0o040755
        can_execute = Builder().can_execute
        self.assertTrue(can_execute('/root', 1000, 100))

    @mock.patch('os.stat')
    def test_can_execute_group_allows(self, mock_stat):
        mock_stat.return_value.st_uid = 0
        mock_stat.return_value.st_gid = 100
        mock_stat.return_value.st_mode = 0o040755
        can_execute = Builder().can_execute
        self.assertTrue(can_execute('/root', 1000, 100))

    @mock.patch('os.stat')
    def test_can_execute_other_allows(self, mock_stat):
        mock_stat.return_value.st_uid = 0
        mock_stat.return_value.st_gid = 0
        mock_stat.return_value.st_mode = 0o040755
        can_execute = Builder().can_execute
        self.assertTrue(can_execute('/root', 1000, 100))

    @mock.patch('os.stat')
    def test_can_execute_haha_cant(self, mock_stat):
        mock_stat.return_value.st_uid = 0
        mock_stat.return_value.st_gid = 100
        mock_stat.return_value.st_mode = 0o040700
        can_execute = Builder().can_execute
        self.assertFalse(can_execute('/root', 1000, 100))

    @mock.patch('os.stat')
    def test_can_execute_haha_cant_even(self, mock_stat):
        mock_stat.side_effect = OSError("nope")
        can_execute = Builder().can_execute
        self.assertFalse(can_execute('/root', 1000, 100))


class TestBuilderWithFilesystem(BuilderTests):

    maxDiff = None

    def test_replace_file_with_explicit_marker(self):
        fn = os.path.join(self.tmpdir, 'subdir', 'file.txt')
        self.builder.replace_file(fn, b'@MARKER@', b'content with @MARKER@')
        with open(fn, 'rb') as f:
            self.assertEqual(f.read(), b'content with @MARKER@')

    def test_replace_file_with_implicit_marker(self):
        fn = os.path.join(self.tmpdir, 'subdir', 'file.txt')
        self.builder.replace_file(fn, b'@MARKER@', b'content')
        with open(fn, 'rb') as f:
            self.assertEqual(f.read(), b'@MARKER@\ncontent')

    def test_replace_file_verbose(self):
        fn = os.path.join(self.tmpdir, 'subdir', 'file.txt')
        self.builder.replace_file(fn, b'@MARKER@', b'content')
        self.assertEqual(self.stdout.getvalue(),
                         "Created %s/subdir/file.txt\n" % self.tmpdir)

    @mock.patch('pov_server_page.update_server_page.replace_file', lambda d, m, n: True)
    def test_replace_file_apache_reload(self):
        self.builder.replace_file('/etc/apache2/test.conf', b'@MARKER@', b'content')
        self.assertTrue(self.builder.needs_apache_reload)

    def test_build(self):
        self.builder.vars['SKIP'] = '{tmpdir}/var/www/frog.example.com/du\n{tmpdir}/var/www/frog.example.com/ports/index.html'.format(tmpdir=self.tmpdir)
        self.builder.vars['REDIRECT'] = '{tmpdir}/var/www/frog.example.com/index.html = {tmpdir}/var/www/frog.example.com/frontpage.html'.format(tmpdir=self.tmpdir)
        self.builder.vars['DISK_USAGE'] = 'all'
        self.builder.vars['MOTD_FILE'] = '/dev/null'
        self.builder.vars['APACHE_EXTRA_CONF'] = '<Location /foo>\nRequire all granted\n</Location>'
        self.builder.vars['EXTRA_LINKS'] = 'foo = <script>alert("hi")</script>'
        self.builder.file_readable_to = lambda f, u, g: True
        self.builder.build(verbose=True, quick=True)
        self.assertMultiLineEqual(
            self.stdout.getvalue().replace(self.tmpdir, ''),
            "Created /var/www/frog.example.com/frontpage.html\n"
            "Skipping /var/www/frog.example.com/ports/index.html\n"
            "Created /var/www/frog.example.com/ssh/index.html\n"
            "Created /var/www/frog.example.com/info/machine-summary.txt\n"
            "Created /var/www/frog.example.com/info/disk-inventory.txt\n"
            "Created /var/www/frog.example.com/info/index.html\n"
            "Skipping /var/www/frog.example.com/du\n"
            "Created /var/log/apache2/frog.example.com/\n"
            "Created /etc/apache2/sites-available/frog.example.com.conf\n"
        )
        fn = os.path.join(self.tmpdir, 'var/www/frog.example.com/frontpage.html')
        with open(fn, 'r') as f:
            self.assertIn('&lt;script&gt;', f.read())
        fn = os.path.join(self.tmpdir, 'etc/apache2/sites-available/frog.example.com.conf')
        with open(fn, 'r') as f:
            self.assertIn('<Location /foo>', f.read())

    def test_check(self):
        self.builder.needs_apache_reload = True
        self.builder.check()


class TestMain(FilesystemTests):

    def setUp(self):
        super(TestMain, self).setUp()
        self.real_stdout = sys.stdout
        self.stdout = self.patch('sys.stdout', StringIO())
        self.stderr = self.patch('sys.stderr', StringIO())
        self.config_file = os.path.join(self.tmpdir, 'config')

    def run_main(self, *args):
        orig_sys_argv = sys.argv
        try:
            sys.argv = [
                'pov-update-server-page',
                '-c', self.config_file,
                '--destdir', self.tmpdir,
            ] + list(args)
            main()
        except SystemExit as e:
            return e
        finally:
            sys.argv = orig_sys_argv

    def test_main_no_config_file(self):
        e = self.run_main()
        self.assertEqual(str(e), "Could not read %s/config" % self.tmpdir)

    def test_main_blank_config_file(self):
        self.run_main('-c', '/dev/null', '-v')
        self.assertEqual(self.stdout.getvalue(),
                         "Disabled in the config file, quitting.\n")

    def test_main_smoke_test(self):
        self.run_main('-c', '/dev/null', '-v', 'enabled=true')

    def test_main_error_handling(self):
        dirname = os.path.join(self.tmpdir, 'var/www', get_fqdn())
        os.makedirs(dirname)
        with open(os.path.join(dirname, 'index.html'), 'w') as f:
            f.write('Preexisting file with no marker')
        e = self.run_main('-c', '/dev/null', '-v', 'enabled=true')
        self.assertEqual(str(e), "Refusing to overwrite %s/var/www/%s/index.html" % (self.tmpdir, get_fqdn()))

    @pytest.mark.xfail(
        sys.version_info >= (3, 13),
        reason="traceback formatter in 3.13 shows only the first line of code",
    )
    def test_main_exception_handling(self):
        self.patch('pov_server_page.utils.to_unicode',
                   side_effect=Exception('induced failure'))
        e = self.run_main('-c', '/dev/null', '-v', 'enabled=true')
        print(self.stderr.getvalue(), file=self.real_stdout)  # so pytest will show it on failure
        self.assertIn('__M_writer', self.stderr.getvalue())
        self.assertEqual(e.args[0], 1)
