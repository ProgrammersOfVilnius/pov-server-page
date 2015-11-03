import os
import random
import shutil
import tempfile
import unittest
import time
import errno

import mock
from nose.tools import assert_equal

from update_server_page import Builder, newer


class TestFilesystem(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='pov-update-server-page-test-')
        self.addCleanup(shutil.rmtree, self.tmpdir)
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
            raise OSError(errno.EACCES, 'cannot access parent directory')
        else:
            return self.real_stat(filename)

    def test_newer_file2_raises_some_error(self):
        with mock.patch('os.stat', self._fake_stat):
            with self.assertRaises(OSError):
                self.assertTrue(newer(self.file1, self.file2))


def test_Builder_from_config_all_defaults():
    cp = Builder.ConfigParser()
    Builder.from_config(cp) # should not raise


def test_DiskUsage_files_to_keep():
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
    assert_equal(kept, set([]))
    kept = keep(files, keep_daily=2)
    assert_equal(kept, set([
        '/var/www/example.com/du/var/du-2013-05-03.gz', # daily 2
        '/var/www/example.com/du/var/du-2013-05-04.gz', # daily 1
    ]))
    kept = keep(files, keep_monthly=3)
    assert_equal(kept, set([
        '/var/www/example.com/du/var/du-2013-03-05.gz', # monthly 3
        '/var/www/example.com/du/var/du-2013-04-01.gz', # monthly 2
        '/var/www/example.com/du/var/du-2013-05-01.gz', # monthly 1
    ]))
    kept = keep(files, keep_yearly=4)
    assert_equal(kept, set([
        '/var/www/example.com/du/var/du-2013-01-01.gz', # yearly 1
    ]))
    kept = keep(files, keep_daily=2, keep_monthly=3, keep_yearly=4)
    assert_equal(kept, set([
        '/var/www/example.com/du/var/du-2013-01-01.gz', # yearly 1
        '/var/www/example.com/du/var/du-2013-03-05.gz', # monthly 3
        '/var/www/example.com/du/var/du-2013-04-01.gz', # monthly 2
        '/var/www/example.com/du/var/du-2013-05-01.gz', # monthly 1
        '/var/www/example.com/du/var/du-2013-05-03.gz', # daily 2
        '/var/www/example.com/du/var/du-2013-05-04.gz', # daily 1
    ]))
    kept = keep(files, keep_daily=5, keep_monthly=5, keep_yearly=4)
    assert_equal(kept, set([
        '/var/www/example.com/du/var/du-2013-01-01.gz', # yearly 1, monthly 5
        '/var/www/example.com/du/var/du-2013-02-01.gz', # monthly 4
        '/var/www/example.com/du/var/du-2013-03-05.gz', # monthly 3
        '/var/www/example.com/du/var/du-2013-04-01.gz', # monthly 2, daily 5
        '/var/www/example.com/du/var/du-2013-05-01.gz', # monthly 1, daily 4
        '/var/www/example.com/du/var/du-2013-05-02.gz', # daily 3
        '/var/www/example.com/du/var/du-2013-05-03.gz', # daily 2
        '/var/www/example.com/du/var/du-2013-05-04.gz', # daily 1
    ]))
