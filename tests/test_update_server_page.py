# -*- coding: utf-8 -*-
import errno
import os
import random
import shutil
import tempfile
import time
import unittest

try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

import mock

from update_server_page import (
    Builder, Error, newer, mkdir_with_parents, symlink, replace_file,
    pipeline, HTML_MARKER, CHANGELOG2HTML_SCRIPT,
)


class FilesystemTests(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='pov-update-server-page-test-')
        self.addCleanup(shutil.rmtree, self.tmpdir)

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
        with mock.patch('update_server_page.open', self.raise_ioerror):
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
        patcher = mock.patch('sys.stdout', StringIO())
        self.stdout = patcher.start()
        self.addCleanup(patcher.stop)
        self.builder = Builder({'foo': 'two', 'HOSTNAME': 'frog.example.com'})
        self.builder.verbose = True
        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
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

    def test_ScriptOutput(self):
        pathname = os.path.join(self.tmpdir, 'subdir', 'index.html')
        Builder.ScriptOutput('printf "%s\n" one {foo}').build(pathname, self.builder)
        with open(pathname, 'rb') as f:
            self.assertEqual(f.read(),
                             HTML_MARKER + b'\none\ntwo\n')
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
        self.assertTrue('/' in locations, locations)

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

    def test_parse_all(self):
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
        self.builder._compute_derived()

    def test_build_none(self):
        self.builder.vars['DISK_USAGE_LIST'] = []
        Builder.DiskUsage().build(self.tmpdir, self.builder)
        self.assertEqual(self.stdout.getvalue(), "")

    def test_build_quick(self):
        self.builder.vars['DISK_USAGE_LIST'] = ['/pond']
        self.builder.quick = True
        Builder.DiskUsage().build(self.tmpdir, self.builder)
        self.assertEqual(self.stdout.getvalue(), "Skipping disk usage\n")

    @mock.patch('update_server_page.pipeline')
    @mock.patch('update_server_page.newer')
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
    @mock.patch('update_server_page.pipeline')
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

    def test_file_readable_to(self):
        file_readable_to = Builder().file_readable_to
        self.assertTrue(file_readable_to(__file__, 'root', 'root'))

    def test_file_readable_to_bad_user(self):
        file_readable_to = Builder().file_readable_to
        self.assertTrue(file_readable_to(__file__, 'no-such-user', 'root'))

    def test_file_readable_to_bad_group(self):
        file_readable_to = Builder().file_readable_to
        self.assertTrue(file_readable_to(__file__, 'root', 'no-such-group'))

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
