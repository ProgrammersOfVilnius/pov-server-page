import textwrap
import unittest

import pov_server_page.disk_inventory as di
from . import PatchMixin, Symlink, Directory, NativeStringIO


def test_fmt_size_decimal():
    assert di.fmt_size_decimal(0) == '0.0 B'
    assert di.fmt_size_decimal(1) == '1.0 B'
    assert di.fmt_size_decimal(10) == '10.0 B'
    assert di.fmt_size_decimal(1000) == '1.0 KB'
    assert di.fmt_size_decimal(1200) == '1.2 KB'
    assert di.fmt_size_decimal(1200*10**3) == '1.2 MB'
    assert di.fmt_size_decimal(1200*10**6) == '1.2 GB'
    assert di.fmt_size_decimal(1200*10**9) == '1.2 TB'
    assert di.fmt_size_decimal(1200*10**12) == '1.2 PB'


def test_fmt_size_si():
    assert di.fmt_size_si(0) == '0.0 B'
    assert di.fmt_size_si(1) == '1.0 B'
    assert di.fmt_size_si(10) == '10.0 B'
    assert di.fmt_size_si(1024) == '1.0 KiB'
    assert di.fmt_size_si(1200) == '1.2 KiB'
    assert di.fmt_size_si(1200*1024) == '1.2 MiB'
    assert di.fmt_size_si(1200*1024**2) == '1.2 GiB'
    assert di.fmt_size_si(1200*1024**3) == '1.2 TiB'
    assert di.fmt_size_si(1200*1024**4) == '1.2 PiB'


class TestCase(PatchMixin, unittest.TestCase):
    module_under_test = di

    def setUp(self):
        self.info = di.LinuxDiskInfo()


class TestCanonicalDeviceName(TestCase):

    def test_cciss(self):
        self.assertEqual(self.info._canonical_device_name('/dev/cciss/c0p0'),
                         'cciss!c0p0')


class TestSwap(TestCase):

    def test_openvz_container(self):
        self.patch_files({
            '/proc/swaps': (
                'Filename				Type		Size	Used	Priority\n'
                '/dev/null                               partition	2097152	0	-1\n'
            ),
        })
        self.assertEqual(self.info.list_swap_devices(), ['null'])

    def test_devmapper(self):
        self.patch_files({
            '/proc/swaps': (
                'Filename				Type		Size	Used	Priority\n'
                '/dev/dm-2                               partition	8269820	0	-1\n'
            ),
            '/dev/mapper/platonas-swap_1': Symlink('../dm-2'),
        })
        self.assertEqual(self.info.list_swap_devices(), ['mapper/platonas-swap_1'])


class TestFilesystems(TestCase):

    def test(self):
        self.patch_commands({
            'df -P --local --print-type -x debugfs': NativeStringIO(textwrap.dedent('''\
                Filesystem                Type     1024-blocks      Used Available Capacity Mounted on
                udev                      devtmpfs     8124044         0   8124044       0% /dev
                tmpfs                     tmpfs        1630584     19392   1611192       2% /run
                /dev/mapper/platonas-root ext4       471950640 143870928 304082888      33% /
                tmpfs                     tmpfs        8152920     22436   8130484       1% /dev/shm
                tmpfs                     tmpfs           5120         4      5116       1% /run/lock
                tmpfs                     tmpfs        8152920         0   8152920       0% /sys/fs/cgroup
                /dev/loop0                squashfs       10112     10112         0     100% /snap/kubectl/250
                /dev/sda1                 ext2          482922    143130    314858      32% /boot
                tmpfs                     tmpfs        1630584        16   1630568       1% /run/user/121
                tmpfs                     tmpfs        1630584      7328   1623256       1% /run/user/1000
            ''')),
        })
        self.assertEqual(self.info.list_filesystems(), [
            ('mapper/platonas-root', '/', 'ext4', 471950640, 143870928, 304082888),
            ('loop0', '/snap/kubectl/250', 'squashfs', 10112, 10112, 0),
            ('sda1', '/boot', 'ext2', 482922, 143130, 314858),
        ])


class TestPhysicalDisks(TestCase):

    def test(self):
        self.patch_files({
            '/sys/block/dm-0': Symlink('../devices/virtual/block/dm-0'),
            '/sys/block/loop0': Symlink('../devices/virtual/block/loop0'),
            '/sys/block/sda': Symlink('../devices/pci0000:00/0000:00:1f.2/ata1/host0/target0:0:0/0:0:0:0/block/sda'),
        })
        self.assertEqual(self.info.list_physical_disks(), ['sda'])

    def test_cannot_list(self):
        self.patch_files({})
        self.patch('sys.stderr', NativeStringIO())
        self.assertEqual(self.info.list_physical_disks(), [])


class TestDeviceMapper(TestCase):

    def test_list_device_mapper(self):
        self.patch_commands({
            'dmsetup -c --noheadings info': NativeStringIO(
                'platonas-swap_1:253:2:L--w:2:1:0:LVM-blahblah\n'
                'platonas-root:253:1:L--w:1:1:0:LVM-blahblah\n'
                'sda5_crypt:253:0:L--w:2:1:0:CRYPT-LUKS1-blah-sda5_crypt\n'
            ),
        })
        self.assertEqual(self.info.list_device_mapper(), [
            ('platonas-swap_1', 253, 2),
            ('platonas-root', 253, 1),
            ('sda5_crypt', 253, 0),
        ])

    def test_list_device_mapper_names(self):
        self.patch_files({
            '/dev/mapper/control': 'not symlink (should be chardev TBH)',
            '/dev/mapper/platonas-root': Symlink('../dm-1'),
            '/dev/mapper/platonas-swap_1': Symlink('../dm-2'),
            '/dev/mapper/sda5_crypt': Symlink('../dm-0'),
        })
        self.assertEqual(self.info.list_device_mapper_names(), [
            ('mapper/platonas-root', 'dm-1'),
            ('mapper/platonas-swap_1', 'dm-2'),
            ('mapper/sda5_crypt', 'dm-0'),
        ])

    def test_list_device_mapper_names_no_devmapper(self):
        self.patch_files({})
        self.assertEqual(self.info.list_device_mapper_names(), [])


class TestLVM(TestCase):

    def test_list_vgs(self):
        self.patch_commands({
            'vgdisplay -c 2>/dev/null': NativeStringIO(
                '  platonas:r/w:772:-1:0:2:2:-1:0:1:1:487878656:4096:119111:119111:0:jzd3VL-RR7v-44tD-O8zO-9sSI-qFEs-hpmnPE\n'
            ),
        })
        self.assertEqual(self.info.list_lvm_volume_groups(), [
            ('platonas', 487878656, 487878656, 0),
        ])

    def test_list_pvs(self):
        self.patch_commands({
            'pvdisplay -c 2>/dev/null': NativeStringIO(
                '  /dev/mapper/sda5_crypt:platonas:975765504:-1:8:8:-1:4096:119111:0:119111:mRMbR0-4xMf-IuXS-cx20-gXJW-r6MG-QewhqEn\n'
                '  "/dev/sdc2" is a new physical volume of "231.95 GiB"\n'
            ),
        })
        self.assertEqual(self.info.list_lvm_physical_volumes(), [
            ('mapper/sda5_crypt', 'platonas'),
        ])

    def test_list_lvm_logical_volumes(self):
        self.patch_commands({
            'lvdisplay -c 2>/dev/null': NativeStringIO(
                '  /dev/platonas/root:platonas:3:1:-1:1:959217664:117092:-1:0:-1:253:1\n'
                '  /dev/platonas/swap_1:platonas:3:1:-1:2:16539648:2019:-1:0:-1:253:2\n'
            ),
        })
        self.assertEqual(self.info.list_lvm_logical_volumes(), [
            ('root', 'platonas', 959217664, 'mapper/platonas-root'),
            ('swap_1', 'platonas', 16539648, 'mapper/platonas-swap_1'),
        ])


class TestDiskInfo(TestCase):

    def test_get_disk_size(self):
        self.patch_files({
            '/sys/block/sda/size': '976773168\n'
        })
        self.assertEqual(self.info.get_disk_size_bytes('sda'), 500107862016)

    def test_get_disk_model(self):
        self.patch_files({
            '/sys/block/sda/device/model': 'Samsung SSD 850\n'
        })
        self.assertEqual(self.info.get_disk_model('sda'), 'Samsung SSD 850')

    def test_get_disk_model_xen(self):
        self.patch_files({})
        self.assertEqual(self.info.get_disk_model('xvda'), 'Xen virtual disk')

    def test_get_disk_firmware_rev(self):
        self.patch_files({
            '/sys/block/sda/device/rev': '2B6Q\n'
        })
        self.assertEqual(self.info.get_disk_firmware_rev('sda'), '2B6Q')

    def test_get_disk_firmware_rev_xen(self):
        self.patch_files({})
        self.assertEqual(self.info.get_disk_firmware_rev('xvda'), 'N/A')


class TestPartitions(TestCase):

    def test_list_partitions(self):
        self.patch_files({
            '/sys/block/sda/dev': '8:0\n',
            '/sys/block/sda/sda1': Directory(),
            '/sys/block/sda/sda2': Directory(),
            '/sys/block/sda/sda5': Directory(),
        })
        self.assertEqual(self.info.list_partitions('sda'),
                         ['sda1', 'sda2', 'sda5'])

    def test_get_sys_dir_for_partition(self):
        self.patch_commands({
            'dmsetup -c --noheadings info': NativeStringIO(
                'sda5_crypt:253:0:L--w:2:1:0:CRYPT-LUKS1-blah-sda5_crypt\n'
            ),
        })
        self.assertEqual(self.info.get_sys_dir_for_partition('sda1'),
                         '/sys/block/sda/sda1')
        self.assertEqual(self.info.get_sys_dir_for_partition('mapper/sda5_crypt'),
                         '/sys/block/dm-0')
        self.assertEqual(self.info.get_sys_dir_for_partition('cciss!c0d0p7'),
                         '/sys/block/cciss!c0d0/cciss!c0d0p7')

    def test_get_partition_size(self):
        self.patch_files({
            '/sys/block/sda/sda1/size': '997376\n',
        })
        self.assertEqual(self.info.get_partition_size_bytes('sda1'),
                         510656512)


class TestMain(TestCase):

    def run_main(self, *args):
        self.patch('sys.argv', ['disk-inventory'] + list(args))
        di.main()

    def test_main(self):
        self.patch('sys.stdout', NativeStringIO())
        self.run_main()
