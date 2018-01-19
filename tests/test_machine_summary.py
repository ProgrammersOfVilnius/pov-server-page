import importlib
import os
import unittest
import io

import pov_server_page.machine_summary as ms


NativeStringIO = io.BytesIO if str is bytes else io.StringIO


def test_fmt_with_units():
    assert ms.fmt_with_units(12.5, 'megs') == '12.5 megs'
    assert ms.fmt_with_units(12.75, 'megs') == '12.8 megs'
    assert ms.fmt_with_units(12.0, 'megs') == '12 megs'


def test_fmt_size_decimal():
    assert ms.fmt_size_decimal(0) == '0 B'
    assert ms.fmt_size_decimal(1) == '1 B'
    assert ms.fmt_size_decimal(10) == '10 B'
    assert ms.fmt_size_decimal(1000) == '1 KB'
    assert ms.fmt_size_decimal(1200) == '1.2 KB'
    assert ms.fmt_size_decimal(1200*10**3) == '1.2 MB'
    assert ms.fmt_size_decimal(1200*10**6) == '1.2 GB'
    assert ms.fmt_size_decimal(1200*10**9) == '1.2 TB'
    assert ms.fmt_size_decimal(1200*10**12) == '1.2 PB'


def test_fmt_size_si():
    assert ms.fmt_size_si(0) == '0 B'
    assert ms.fmt_size_si(1) == '1 B'
    assert ms.fmt_size_si(10) == '10 B'
    assert ms.fmt_size_si(1024) == '1 KiB'
    assert ms.fmt_size_si(1200) == '1.2 KiB'
    assert ms.fmt_size_si(1200*1024) == '1.2 MiB'
    assert ms.fmt_size_si(1200*1024**2) == '1.2 GiB'
    assert ms.fmt_size_si(1200*1024**3) == '1.2 TiB'
    assert ms.fmt_size_si(1200*1024**4) == '1.2 PiB'


def test_round_binary():
    # these are not very realistic corner cases
    assert ms.round_binary(0) == 0
    assert ms.round_binary(1) == 1
    assert ms.round_binary(2) == 2
    # test cases from actual servers (MemTotal from /proc/meminfo)
    assert ms.round_binary(61680 * 1024) == 64 * 1024**2
    assert ms.round_binary(2061288 * 1024) == 2 * 1024**3
    assert ms.round_binary(3096712 * 1024) == 3 * 1024**3
    assert ms.round_binary(4040084 * 1024) == 4 * 1024**3
    assert ms.round_binary(8061912 * 1024) == 8 * 1024**3


class TestCase(unittest.TestCase):

    def patch(self, what, mock):
        if '.' in what:
            modname, name = what.rsplit('.', 1)
            mod = importlib.import_module(modname)
        else:
            name = what
            mod = ms
        try:
            orig_what = getattr(mod, name)
        except AttributeError:
            self.addCleanup(delattr, mod, name)
        else:
            self.addCleanup(setattr, mod, name, orig_what)
        setattr(mod, name, mock)

    def patch_files(self, files):
        if hasattr(self, '_files'):
            self._files.update(files)
        else:
            self._files = files
            self.patch('read_file', self._read_file)
            self.patch('open', self._open)
            self.patch('os.path.exists', self._exists)

    def _read_file(self, filename):
        if filename not in self._files:
            raise IOError(2, 'File not found')
        return self._files[filename]

    def _open(self, filename):
        return NativeStringIO(self._read_file(filename))

    def _exists(self, filename):
        return filename in self._files


class TestHostname(TestCase):

    def test(self):
        self.patch('socket.getfqdn', lambda: 'example.com')
        self.assertEqual(ms.get_hostname(), 'example.com')

    def test_broken_ubuntu(self):
        self.patch('socket.getfqdn', lambda: 'localhost6.localdomain6')
        self.patch('socket.gethostname', lambda: 'example')
        self.assertEqual(ms.get_hostname(), 'example')


class TestGetRamInfo(TestCase):

    def test_fallback(self):
        self.patch('get_fields', lambda *args: [])
        self.assertEqual(ms.get_ram_info(), 'n/a')


class TestGetDiskInfo(TestCase):

    def test_simfs(self):
        self.patch('os.statvfs', lambda fs: os.statvfs_result(
            (4096, 4096, 20971520, 17750785, 17750785, 1600000, 1275269, 1275269, 4096, 255)
        ))
        self.assertEqual(ms.get_disk_info('simfs'), '80 GiB')

    def test_swap(self):
        self.patch_files({
            '/proc/swaps': (
                'Filename				Type		Size	Used	Priority\n'
                '/dev/null                               partition	2097152	0	-1\n'
            ),
        })
        self.assertEqual(ms.get_disk_info('swap'), '2 GiB')

    def test_cciss(self):
        self.patch_files({
            '/sys/block/cciss!c0d0/size': '860051248\n',
            '/sys/block/cciss!c0d0/device/vendor': 'HP\n',
            '/sys/block/cciss!c0d0/device/raid_level': 'RAID 5\n',
        })
        self.assertEqual(ms.get_disk_info('cciss!c0d0'),
                         '440.3 GB (HP hardware RAID 5)')

    def test(self):
        self.patch_files({
            '/sys/block/sda/size': '976773168\n',
            '/sys/block/sda/device/model': 'Samsung SSD 850\n',
        })
        self.assertEqual(ms.get_disk_info('sda'), '500.1 GB (model Samsung SSD 850)')

    def test_no_model(self):
        self.patch_files({
            '/sys/block/sda/size': '976773168\n',
        })
        self.assertEqual(ms.get_disk_info('sda'), '500.1 GB')


class TestEnumerateDisks(TestCase):

    def test_no_sys_block(self):
        self.patch_files({})
        self.assertEqual(ms.enumerate_disks(), ['???'])

    def test_simfs(self):
        self.patch_files({'/dev/simfs': None})
        self.assertEqual(ms.enumerate_disks(), ['simfs', 'swap'])

    def test_vzfs(self):
        self.patch_files({'/dev/vzfs': None})
        self.assertEqual(ms.enumerate_disks(), ['vzfs'])


class TestOsInfo(TestCase):

    def test_lsb(self):
        self.patch_files({
            '/etc/lsb-release': 'DISTRIB_DESCRIPTION="Ubuntu 16.04 LTS"\n',
        })
        self.assertEqual(ms.get_os_info(), 'Ubuntu 16.04 LTS')

    def test_openwrt(self):
        self.patch_files({
            '/etc/openwrt_release': 'DISTRIB_DESCRIPTION="OpenWrt Attitude Adjustment r32481\n',
        })
        self.assertEqual(ms.get_os_info(), 'OpenWrt Attitude Adjustment r32481')

    def test_unknown(self):
        self.patch_files({})
        self.assertEqual(ms.get_os_info(), 'n/a')

    def test_bad_lsb(self):
        self.patch_files({
            '/etc/lsb-release': '',
        })
        self.assertEqual(ms.get_os_info(), 'n/a')
