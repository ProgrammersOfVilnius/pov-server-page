from __future__ import print_function

import os
import textwrap
import unittest

import pov_server_page.machine_summary as ms
from . import PatchMixin, NativeStringIO


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


class TestCase(PatchMixin, unittest.TestCase):
    module_under_test = ms


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


class TestIpAddresses(TestCase):

    def test(self):
        self.patch('os.popen', lambda cmd: NativeStringIO(textwrap.dedent('''\
            1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default 
                link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
                inet 127.0.0.1/8 scope host lo
                   valid_lft forever preferred_lft forever
                inet6 ::1/128 scope host 
                   valid_lft forever preferred_lft forever
            2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP group default qlen 1000
                link/ether d4:ae:52:c8:70:d5 brd ff:ff:ff:ff:ff:ff
                inet 151.236.45.231 peer 151.236.45.193/32 brd 151.236.45.231 scope global eth0
                   valid_lft forever preferred_lft forever
                inet6 2a02:af8:6:1200::1:2586/128 scope global 
                   valid_lft forever preferred_lft forever
                inet6 fe80::d6ae:52ff:fec8:70d5/64 scope link 
                   valid_lft forever preferred_lft forever
            3: eth1: <BROADCAST,MULTICAST> mtu 1500 qdisc noop state DOWN group default qlen 1000
                link/ether d4:ae:52:c8:70:d6 brd ff:ff:ff:ff:ff:ff
        ''')))
        self.assertEqual(ms.get_ip_addresses(), [
            ('151.236.45.231', 'eth0'),
            ('2a02:af8:6:1200::1:2586', 'eth0'),
        ])


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


class TestReport(TestCase):

    def test(self):
        ms.report(print=[].append)


class TestMain(TestCase):

    def run_main(self, *args):
        self.patch('sys.argv', ['machine-summary'] + list(args))
        ms.main()

    def test_cgi(self):
        self.patch('sys.stdout', NativeStringIO())
        self.patch('os.getenv', {'RUN_AS_CGI': '1'}.get)
        self.run_main()
