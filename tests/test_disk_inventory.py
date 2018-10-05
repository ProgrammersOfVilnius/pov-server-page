from __future__ import print_function

import functools
import os
import textwrap
import unittest

import pov_server_page.disk_inventory as di
from . import PatchMixin, Symlink, Directory, NativeStringIO


# TODO: switch from nose to pytest and replace with @pytest.mark.parametrize
def parametrize(args, values):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper():
            for testcase in values:
                fn(**dict(zip(args, testcase)))
        return wrapper
    return decorator


def test_once_decorator():
    class Foo(object):
        @di.once
        def compute(self):
            computations.append(1)
            return 42
    computations = []
    foo = Foo()
    assert foo.compute == 42
    assert foo.compute == 42
    assert len(computations) == 1
    bar = Foo()
    assert bar.compute == 42
    assert bar.compute == 42
    assert len(computations) == 2


def test_cache_decorator():
    class Foo(object):
        @di.cache
        def compute(self):
            computations.append(1)
            return 42
    computations = []
    foo = Foo()
    assert foo.compute() == 42
    assert foo.compute() == 42
    assert len(computations) == 1
    bar = Foo()
    assert bar.compute() == 42
    assert bar.compute() == 42
    assert len(computations) == 2


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


@parametrize(
    ['fs_avail_kb', 'pv_free_kb', 'total_kb', 'used', 'expected'],
    [
        (1200, None, 3000, False, '1.2 MB free'),
        (1200, None, 3000, True, '1.8 MB used'),
        (None, 1300, 3000, False, '1.3 MB free'),
        (None, 1300, 3000, True, '1.7 MB used'),
    ],
)
def test_fmt_free_space(fs_avail_kb, pv_free_kb, total_kb, used, expected):
    fsinfo = fs_avail_kb and di.FilesystemInfo(
        'sda1', '/', 'ext4', total_kb, total_kb - fs_avail_kb, fs_avail_kb,
    )
    pvinfo = pv_free_kb and di.PVInfo('sda2', 'ubuntu', pv_free_kb)
    actual = di.fmt_free_space(
        fsinfo=fsinfo, pvinfo=pvinfo, partition_size_bytes=total_kb * 1024,
        fmt_size=di.fmt_size_decimal, show_used_instead_of_free=used)
    assert actual == expected, vars()


class TestCase(PatchMixin, unittest.TestCase):
    module_under_test = di

    def setUp(self):
        self.info = di.LinuxDiskInfo()
        self.patch_files({})
        self.patch_commands({})


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
            'df -P --local --print-type -x debugfs': textwrap.dedent('''\
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
            '''),
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

    def test_openvz(self):
        self.patch_files({
            '/dev/simfs': 'character device actually',
        })
        self.assertEqual(self.info.list_physical_disks(), ['simfs'])


class TestDeviceMapper(TestCase):

    def test_list_device_mapper(self):
        self.patch_commands({
            'dmsetup -c --noheadings info': textwrap.dedent('''\
                platonas-swap_1:253:2:L--w:2:1:0:LVM-blahblah
                platonas-root:253:1:L--w:1:1:0:LVM-blahblah
                sda5_crypt:253:0:L--w:2:1:0:CRYPT-LUKS1-blah-sda5_crypt
            '''),
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
            'vgdisplay -c 2>/dev/null': (
                '  platonas:r/w:772:-1:0:2:2:-1:0:1:1:487878656:4096:119111:119111:0:jzd3VL-RR7v-44tD-O8zO-9sSI-qFEs-hpmnPE\n'
            ),
        })
        self.assertEqual(self.info.list_lvm_volume_groups(), [
            ('platonas', 487878656, 487878656, 0),
        ])

    def test_list_pvs(self):
        self.patch_commands({
            'pvdisplay -c 2>/dev/null': (
                '  /dev/mapper/sda5_crypt:platonas:975765504:-1:8:8:-1:4096:119111:0:119111:mRMbR0-4xMf-IuXS-cx20-gXJW-r6MG-QewhqEn\n'
                '  "/dev/sdc2" is a new physical volume of "231.95 GiB"\n'
            ),
        })
        self.assertEqual(self.info.list_lvm_physical_volumes(), [
            ('mapper/sda5_crypt', 'platonas', 0),
        ])

    def test_list_lvm_logical_volumes(self):
        self.patch_commands({
            'lvs --separator=: --units=b --nosuffix --noheadings -o lv_name,vg_name,lv_size,lv_dm_path,lv_role,devices,metadata_devices,lv_device_open --all 2>/dev/null': (
                '  root:platonas:491119443968:/dev/mapper/platonas-root:public:/dev/mapper/sda5_crypt(0)::open\n'
                '  swap_1:platonas:8468299776:/dev/mapper/platonas-swap_1:public:/dev/mapper/sda5_crypt(117092)::open\n'
            ),
        })
        self.assertEqual(self.info.list_lvm_logical_volumes(), [
            ('root', 'platonas', 491119443968, 'mapper/platonas-root', 'public', {'/dev/mapper/sda5_crypt'}, True),
            ('swap_1', 'platonas', 8468299776, 'mapper/platonas-swap_1', 'public', {'/dev/mapper/sda5_crypt'}, True),
        ])


class TestKVM(TestCase):

    def test(self):
        self.patch_files({
            '/dev/fridge/box': Symlink('../dm-34'),
            '/dev/mapper/fridge-box': Symlink('../dm-34'),
            '/etc/libvirt/qemu/box.xml': '''
                <domain type='kvm'>
                  <name>box</name>
                  ...
                  <devices>
                    <emulator>/usr/bin/kvm</emulator>
                    <disk type='file' device='disk'>
                      <driver name='qemu' type='raw'/>
                      <source file='/dev/fridge/box'/>
                      <target dev='vda' bus='virtio'/>
                      ...
                    </disk>
                    ...
                  </devices>
                </domain>
            '''
        })
        self.patch_commands({
            'dmsetup -c --noheadings info': textwrap.dedent('''\
                fridge-box_rimage_1:252:33:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2xMjyUUhS8GSQvnw8d7TgQvbEYIffzihX
                fridge-box_rimage_0:252:31:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2ksxmomSjYZM3NJnWGwapZXVxBoM6IL2n
                fridge-box_rmeta_1:252:32:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2t8tbRWsEM2co6FdzpO9tiT3xqqPvOmR4
                fridge-box_rmeta_0:252:30:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2zXVgjP5sBfkdQ0zMl7pTbK8AXxYTlge4
                fridge-box:252:34:L--w:0:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2gClj1O6U8a1x70slRyUyFFmhRCUC1gsY
            '''),
        })
        self.assertEqual(self.info.list_kvm_vms(), [
            ('box', 'mapper/fridge-box'),
        ])


class TestDiskInfo(TestCase):

    def test_get_disk_size(self):
        self.patch_files({
            '/sys/block/sda/size': '976773168\n',
        })
        self.assertEqual(self.info.get_disk_size_bytes('sda'), 500107862016)

    def test_get_disk_size_openvz(self):
        self.patch_files({
            '/dev/simfs': 'character device actually',
        })
        self.patch('os.statvfs', lambda fs: os.statvfs_result(
            (4096, 4096, 20971520, 17750785, 17750785, 1600000, 1275269, 1275269, 4096, 255)
        ))
        self.assertEqual(self.info.get_disk_size_bytes('simfs'), 85899345920)

    def test_get_disk_model(self):
        self.patch_files({
            '/sys/block/sda/device/model': 'Samsung SSD 850\n',
        })
        self.assertEqual(self.info.get_disk_model('sda'), 'Samsung SSD 850')

    def test_get_disk_model_xen(self):
        self.patch_files({})
        self.assertEqual(self.info.get_disk_model('xvda'), 'Xen virtual disk')
        self.assertEqual(self.info.get_disk_model('xvdb'), 'Xen virtual disk')

    def test_get_disk_model_kvm(self):
        self.patch_files({})
        self.assertEqual(self.info.get_disk_model('vda'), 'KVM virtual disk')
        self.assertEqual(self.info.get_disk_model('vdb'), 'KVM virtual disk')

    def test_get_disk_model_simfs(self):
        self.patch_files({
            '/dev/simfs': 'character device actually',
        })
        self.assertEqual(self.info.get_disk_model('simfs'),
                         'OpenVZ virtual filesystem')

    def test_get_disk_firmware_rev(self):
        self.patch_files({
            '/sys/block/sda/device/rev': '2B6Q\n',
        })
        self.assertEqual(self.info.get_disk_firmware_rev('sda'), '2B6Q')

    def test_get_disk_firmware_rev_xen(self):
        self.patch_files({})
        self.assertEqual(self.info.get_disk_firmware_rev('xvda'), 'N/A')
        self.assertEqual(self.info.get_disk_firmware_rev('xvdb'), 'N/A')

    def test_get_disk_firmware_rev_kvm(self):
        self.patch_files({})
        self.assertEqual(self.info.get_disk_firmware_rev('vda'), 'N/A')
        self.assertEqual(self.info.get_disk_firmware_rev('vdb'), 'N/A')

    def test_is_disk_an_ssd_simfs(self):
        self.patch_files({})
        self.assertFalse(self.info.is_disk_an_ssd('simfs'))


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

    def test_list_partitions_openvz(self):
        self.assertEqual(self.info.list_partitions('simfs'),
                         ['simfs'])

    def test_get_sys_dir_for_partition(self):
        self.patch_commands({
            'dmsetup -c --noheadings info': (
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

    def test_get_partition_size_openvz(self):
        self.patch('os.statvfs', lambda fs: os.statvfs_result(
            (4096, 4096, 20971520, 17750785, 17750785, 1600000, 1275269, 1275269, 4096, 255)
        ))
        self.assertEqual(self.info.get_partition_size_bytes('simfs'),
                         85899345920)

    def test_get_partition_offset(self):
        self.patch_files({
            '/sys/block/sda/sda1/start': '2048\n',
        })
        self.assertEqual(self.info.get_partition_offset_bytes('sda1'),
                         1048576)

    def test_get_partition_offset_openvz(self):
        self.assertEqual(self.info.get_partition_offset_bytes('simfs'), 0)

    def test_list_partition_holders(self):
        self.patch_files({
            '/sys/block/sda/sda5/holders/dm-0': Symlink('../../../../../../../../../../virtual/block/dm-0'),
        })
        self.assertEqual(self.info.list_partition_holders('sda5'),
                         ['dm-0'])

    def test_list_partition_holders_simfs(self):
        self.assertEqual(self.info.list_partition_holders('simfs'), [])

    def test_partition_raid_devices(self):
        self.patch_files({
            '/sys/block/sda/sda5/holders/md0': Symlink('../../../../../../../../../../virtual/block/dm-0'),
        })
        self.assertEqual(self.info.partition_raid_devices('sda5'),
                         ['md0'])

    def test_partition_dm_devices(self):
        self.patch_files({
            '/sys/block/sda/sda5/holders/dm-0': Symlink('../../../../../../../../../../virtual/block/dm-0'),
            '/sys/block/dm-0/holders': Directory(),
        })
        self.assertEqual(self.info.partition_dm_devices('sda5'),
                         ['dm-0'])

    def test_get_partition_fsinfo(self):
        self.patch_files({
            '/dev/mapper/platonas-root': Symlink('../dm-1'),
            '/dev/mapper/sda5_crypt': Symlink('../dm-0'),
            '/sys/block/dm-0/holders/dm-1': Symlink('../../dm-1'),
            '/sys/block/dm-0/holders/dm-2': Symlink('../../dm-2'),
            '/sys/block/sda/sda1/holders': Directory(),
            '/sys/block/sda/sda2/holders': Directory(),
            '/sys/block/sda/sda5/holders/dm-0': Symlink('../../../../../../../../../../virtual/block/dm-0'),
        })
        self.patch_commands({
            'dmsetup -c --noheadings info': textwrap.dedent('''\
                platonas-swap_1:253:2:L--w:2:1:0:LVM-blahblah
                platonas-root:253:1:L--w:1:1:0:LVM-blahblah
                sda5_crypt:253:0:L--w:2:1:0:CRYPT-LUKS1-blah-sda5_crypt
            '''),
            'df -P --local --print-type -x debugfs': textwrap.dedent('''\
                Filesystem                Type     1024-blocks      Used Available Capacity Mounted on
                /dev/mapper/platonas-root ext4       471950640 143870928 304082888      33% /
                /dev/sda1                 ext2          482922    143130    314858      32% /boot
            '''),
        })
        self.assertEqual(self.info.get_partition_fsinfo('sda1'),
                         ('sda1', '/boot', 'ext2', 482922, 143130, 314858))
        self.assertIsNone(self.info.get_partition_fsinfo('sda2'))
        self.assertIsNone(self.info.get_partition_fsinfo('sda5'))

    def test_get_partition_lvm_pv(self):
        self.patch_files({
            '/dev/mapper/platonas-root': Symlink('../dm-1'),
            '/dev/mapper/sda5_crypt': Symlink('../dm-0'),
            '/sys/block/dm-0/holders/dm-1': Symlink('../../dm-1'),
            '/sys/block/dm-0/holders/dm-2': Symlink('../../dm-2'),
            '/sys/block/sda/sda1/holders': Directory(),
            '/sys/block/sda/sda2/holders': Directory(),
            '/sys/block/sda/sda5/holders/dm-0': Symlink('../../../../../../../../../../virtual/block/dm-0'),
        })
        self.patch_commands({
            'dmsetup -c --noheadings info': textwrap.dedent('''\
                platonas-swap_1:253:2:L--w:2:1:0:LVM-blahblah
                platonas-root:253:1:L--w:1:1:0:LVM-blahblah
                sda5_crypt:253:0:L--w:2:1:0:CRYPT-LUKS1-blah-sda5_crypt
            '''),
            'pvdisplay -c 2>/dev/null': (
                '  /dev/mapper/sda5_crypt:platonas:975765504:-1:8:8:-1:4096:119111:0:119111:mRMbR0-4xMf-IuXS-cx20-gXJW-r6MG-QewhqEn\n'
                '  "/dev/sdc2" is a new physical volume of "231.95 GiB"\n'
            ),
        })
        self.assertIsNone(self.info.get_partition_lvm_pv('sda1'))
        self.assertIsNone(self.info.get_partition_lvm_pv('sda2'))
        self.assertEqual(self.info.get_partition_lvm_pv('sda5'),
                         ('mapper/sda5_crypt', 'platonas', 0))

    def test_get_partition_kvm_vm(self):
        self.patch_files({
            '/dev/fridge/box': Symlink('../dm-34'),
            '/dev/mapper/fridge-box': Symlink('../dm-34'),
            '/etc/libvirt/qemu/box.xml': '''
                <domain type='kvm'>
                  <name>box</name>
                  ...
                  <devices>
                    <emulator>/usr/bin/kvm</emulator>
                    <disk type='file' device='disk'>
                      <driver name='qemu' type='raw'/>
                      <source file='/dev/fridge/box'/>
                      <target dev='vda' bus='virtio'/>
                      ...
                    </disk>
                    ...
                  </devices>
                </domain>
            ''',
            '/sys/block/dm-34/holders': Directory(),
        })
        self.patch_commands({
            'dmsetup -c --noheadings info': textwrap.dedent('''\
                fridge-box_rimage_1:252:33:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2xMjyUUhS8GSQvnw8d7TgQvbEYIffzihX
                fridge-box_rimage_0:252:31:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2ksxmomSjYZM3NJnWGwapZXVxBoM6IL2n
                fridge-box_rmeta_1:252:32:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2t8tbRWsEM2co6FdzpO9tiT3xqqPvOmR4
                fridge-box_rmeta_0:252:30:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2zXVgjP5sBfkdQ0zMl7pTbK8AXxYTlge4
                fridge-box:252:34:L--w:0:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2gClj1O6U8a1x70slRyUyFFmhRCUC1gsY
            '''),
        })
        self.assertEqual(self.info.get_partition_kvm_vm('mapper/fridge-box'),
                         ('box', 'mapper/fridge-box'))

    def test_get_partition_usage_kvm_vm(self):
        self.patch_files({
            '/dev/fridge/box': Symlink('../dm-34'),
            '/dev/mapper/fridge-box': Symlink('../dm-34'),
            '/etc/libvirt/qemu/box.xml': '''
                <domain type='kvm'>
                  <name>box</name>
                  ...
                  <devices>
                    <emulator>/usr/bin/kvm</emulator>
                    <disk type='file' device='disk'>
                      <driver name='qemu' type='raw'/>
                      <source file='/dev/fridge/box'/>
                      <target dev='vda' bus='virtio'/>
                      ...
                    </disk>
                    ...
                  </devices>
                </domain>
            ''',
            '/sys/block/dm-34/holders': Directory(),
            '/proc/swaps': '',
        })
        self.patch_commands({
            'pvdisplay -c 2>/dev/null': '',
            'df -P --local --print-type -x debugfs': '',
            'dmsetup -c --noheadings info': textwrap.dedent('''\
                fridge-box_rimage_1:252:33:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2xMjyUUhS8GSQvnw8d7TgQvbEYIffzihX
                fridge-box_rimage_0:252:31:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2ksxmomSjYZM3NJnWGwapZXVxBoM6IL2n
                fridge-box_rmeta_1:252:32:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2t8tbRWsEM2co6FdzpO9tiT3xqqPvOmR4
                fridge-box_rmeta_0:252:30:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2zXVgjP5sBfkdQ0zMl7pTbK8AXxYTlge4
                fridge-box:252:34:L--w:0:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2gClj1O6U8a1x70slRyUyFFmhRCUC1gsY
            '''),
        })
        self.assertEqual(self.info.get_partition_usage('mapper/fridge-box'),
                         'KVM: box')

    def test_get_partition_usage_lvm_on_mdraid(self):
        self.patch_files({
            '/proc/swaps': '',
            '/sys/block/sda/sda2/holders/md0': Symlink('../../../../../../../../../../virtual/block/md0'),
        })
        self.patch_commands({
            'dmsetup -c --noheadings info': '',
            'df -P --local --print-type -x debugfs': textwrap.dedent('''\
                Filesystem                      Type     1024-blocks      Used Available Capacity Mounted on
                /dev/md0                        ext4          948024    103740    795292      12% /boot
                /dev/md1                        ext4        14290160  11725204   1832400      87% /var
                /dev/md3                        ext4       220956716  79482580 130243504      38% /home
                /dev/md4                        ext4       237379060 189781084  45184944      81% /stuff
            '''),
            'pvdisplay -c 2>/dev/null': '',
        })
        self.assertEqual(self.info.get_partition_usage('sda2'),
                         'md0: ext4 /boot')

    def test_get_partition_usage_lvm_on_dmcrypt(self):
        self.patch_files({
            '/dev/mapper/platonas-swap_1': Symlink('../dm-2'),
            '/dev/mapper/platonas-root': Symlink('../dm-1'),
            '/dev/mapper/sda5_crypt': Symlink('../dm-0'),
            '/proc/swaps': (
                'Filename				Type		Size	Used	Priority\n'
                '/dev/dm-2                               partition	8269820	0	-1\n'
            ),
            '/sys/block/dm-0/holders/dm-1': Symlink('../../dm-1'),
            '/sys/block/dm-0/holders/dm-2': Symlink('../../dm-2'),
            '/sys/block/dm-1/holders': Directory(),
            '/sys/block/dm-2/holders': Directory(),
            '/sys/block/sda/sda1/holders': Directory(),
            '/sys/block/sda/sda2/holders': Directory(),
            '/sys/block/sda/sda5/holders/dm-0': Symlink('../../../../../../../../../../virtual/block/dm-0'),
        })
        self.patch_commands({
            'dmsetup -c --noheadings info': textwrap.dedent('''\
                platonas-swap_1:253:2:L--w:2:1:0:LVM-blahblah
                platonas-root:253:1:L--w:1:1:0:LVM-blahblah
                sda5_crypt:253:0:L--w:2:1:0:CRYPT-LUKS1-blah-sda5_crypt
            '''),
            'df -P --local --print-type -x debugfs': textwrap.dedent('''\
                Filesystem                Type     1024-blocks      Used Available Capacity Mounted on
                /dev/mapper/platonas-root ext4       471950640 143870928 304082888      33% /
                /dev/sda1                 ext2          482922    143130    314858      32% /boot
            '''),
            'pvdisplay -c 2>/dev/null': (
                '  /dev/mapper/sda5_crypt:platonas:975765504:-1:8:8:-1:4096:119111:0:119111:mRMbR0-4xMf-IuXS-cx20-gXJW-r6MG-QewhqEn\n'
            ),
        })
        self.assertEqual(self.info.get_partition_usage('sda1'),
                         'ext2 /boot')
        self.assertEqual(self.info.get_partition_usage('sda2'),
                         '')
        self.assertEqual(self.info.get_partition_usage('sda5'),
                         'LVM: platonas')
        self.assertEqual(self.info.get_partition_usage('mapper/platonas-root'),
                         'ext4 /')
        self.assertEqual(self.info.get_partition_usage('mapper/platonas-swap_1'),
                         'swap')


class TestTextReporter(TestCase):

    def test_ssd_label(self):
        result = []
        reporter = di.TextReporter(print=result.append)
        reporter.start_disk(
            disk='sda', model='Weird solid state disk', fwrev='FW42',
            disk_size_bytes=40*1000**3, is_ssd=True)
        self.assertEqual(result, [
            'sda: Weird solid state disk (40.0 GB) [SSD]',
        ])


class TestHtmlReporter(TestCase):

    def test_ssd_label(self):
        result = []
        reporter = di.HtmlReporter(print=result.append)
        reporter.start_disk(
            disk='sda', model='My good SSD', fwrev='FW42',
            disk_size_bytes=40*1000**3, is_ssd=True)
        self.assertMultiLineEqual('\n'.join(result), textwrap.dedent('''\
            <tr>
              <th colspan="4">
                sda: My good SSD (40.0 GB), firmware revision FW42
                <span class="label label-info">SSD</span>
              </th>
            </tr>
        ''').rstrip())

    def test_unused_md_device(self):
        result = []
        reporter = di.HtmlReporter(print=result.append)
        reporter.partition(
            name='sda6',
            partition_size_bytes=10*1000**3,
            usage='md3:',
            fsinfo=None,
            pvinfo=None,
            is_used=False
        )
        self.assertMultiLineEqual('\n'.join(result), textwrap.dedent('''\
            <tr class="text-muted">
              <td>
                sda6
              </td>
              <td class="text-right">
                10.0 GB
              </td>
              <td>
                md3: (unused)
              </td>
              <td class="text-right">
              </td>
            </tr>
        ''').rstrip())


class TestReport(TestCase):

    def test_lvm(self):
        self.patch_files({
            '/proc/swaps': '',
            '/sys/block/sda/size': '976773168\n',
            '/sys/block/sda/queue/rotational': '0\n',
            '/sys/block/sda/device/model': 'Samsung SSD 850\n',
            '/sys/block/sda/device/rev': '2B6Q\n',
            '/sys/block/sda/sda1/size': '997376\n',
            '/sys/block/sda/sda1/start': '2048\n',
            '/sys/block/sda/sda1/holders': Directory(),
            '/sys/block/sda/sda2/size': '2\n',
            '/sys/block/sda/sda2/start': '1001470\n',
            '/sys/block/sda/sda2/holders': Directory(),
            '/sys/block/sda/sda5/size': '975769600\n',
            '/sys/block/sda/sda5/start': '1001472\n',
            '/sys/block/sda/sda5/holders/dm-0': Symlink('../../../../../../../../../../virtual/block/dm-0'),
            '/sys/block/dm-1/holders': Directory(),
            '/sys/block/dm-2/holders': Directory(),
        })
        self.patch_commands({
            'pvdisplay -c 2>/dev/null': (
                '  /dev/mapper/sda5_crypt:platonas:975765504:-1:8:8:-1:4096:119111:0:119111:mRMbR0-4xMf-IuXS-cx20-gXJW-r6MG-QewhqEn\n'
            ),
            'vgdisplay -c 2>/dev/null': (
                '  platonas:r/w:772:-1:0:2:2:-1:0:1:1:487878656:4096:119111:119111:0:jzd3VL-RR7v-44tD-O8zO-9sSI-qFEs-hpmnPE\n'
            ),
            'lvs --separator=: --units=b --nosuffix --noheadings -o lv_name,vg_name,lv_size,lv_dm_path,lv_role,devices,metadata_devices,lv_device_open --all 2>/dev/null': (
                '  root:platonas:491119443968:/dev/mapper/platonas-root:public:/dev/mapper/sda5_crypt(0)::open\n'
                '  swap_1:platonas:8468299776:/dev/mapper/platonas-swap_1:public:/dev/mapper/sda5_crypt(117092)::open\n'
            ),
            'dmsetup -c --noheadings info': textwrap.dedent('''\
                platonas-swap_1:253:2:L--w:2:1:0:LVM-blahblah
                platonas-root:253:1:L--w:1:1:0:LVM-blahblah
                sda5_crypt:253:0:L--w:2:1:0:CRYPT-LUKS1-blah-sda5_crypt
            '''),
            'df -P --local --print-type -x debugfs': textwrap.dedent('''\
                Filesystem                Type     1024-blocks      Used Available Capacity Mounted on
                /dev/mapper/platonas-root ext4       471950640 143870928 304082888      33% /
                /dev/sda1                 ext2          482922    143130    314858      32% /boot
            '''),
        })
        self.assertMultiLineEqual(di.report_text(verbose=2) + '\n', textwrap.dedent('''\
            sda: Samsung SSD 850 (500.1 GB), firmware revision 2B6Q
              sda1:      510.7 MB  ext2 /boot                        322.4 MB free
              sda2:        1.0 KB
              sda5:      499.6 GB
                           1.1 MB (unused)
                           2.1 MB (metadata/internal fragmentation)
            platonas: LVM (499.6 GB)
              root:      491.1 GB  ext4 /                            311.4 GB free
              swap_1:      8.5 GB
              free:         0.0 B
        '''))
        # Smoke test, I'm not going to compare the HTML unless I find a regression
        di.report_html(verbose=2)

    def test_multiple_lvm_vgs(self):
        self.patch_files({
            '/dev/mapper/platonas-swap_1': Symlink('../dm-2'),
            '/dev/mapper/platonas-root': Symlink('../dm-1'),
            '/dev/mapper/sde5_crypt': Symlink('../dm-0'),
            '/proc/swaps': (
                'Filename				Type		Size	Used	Priority\n'
                '/dev/dm-2                               partition	8269820	0	-1\n'
            ),
            '/sys/block/dm-0/holders/dm-1': Symlink('../../dm-1'),
            '/sys/block/dm-0/holders/dm-2': Symlink('../../dm-2'),
            '/sys/block/dm-1/holders': Directory(),
            '/sys/block/dm-2/holders': Directory(),
            '/sys/block/dm-9/holders': Directory(),
            '/sys/block/dm-14/holders': Directory(),
            '/sys/block/dm-19/holders': Directory(),
            '/sys/block/dm-24/holders': Directory(),
            '/sys/block/dm-29/holders': Directory(),
            '/sys/block/dm-34/holders': Directory(),
            '/sys/block/dm-39/holders': Directory(),
            '/sys/block/dm-44/holders': Directory(),
            '/sys/block/dm-49/holders': Directory(),
            '/sys/block/dm-4/holders': Directory(),
            '/sys/block/dm-54/holders': Directory(),
            '/sys/block/dm-59/holders': Directory(),
            '/sys/block/dm-64/holders': Directory(),
            '/sys/block/dm-69/holders': Directory(),
            '/sys/block/sda/size': '488397168\n',
            '/sys/block/sda/device/model': 'Samsung SSD 850\n',
            '/sys/block/sda/device/rev': '2B6Q\n',
            '/sys/block/sda/queue/rotational': '0\n',
            '/sys/block/sdb/size': '488397168\n',
            '/sys/block/sdb/device/model': 'Samsung SSD 850\n',
            '/sys/block/sdb/device/rev': '2B6Q\n',
            '/sys/block/sdb/queue/rotational': '0\n',
            '/sys/block/sde/size': '976773168\n',
            '/sys/block/sde/device/model': 'Samsung SSD 850\n',
            '/sys/block/sde/device/rev': '2B6Q\n',
            '/sys/block/sde/queue/rotational': '0\n',
            '/sys/block/sde/sde1/size': '997376\n',
            '/sys/block/sde/sde1/start': '2048\n',
            '/sys/block/sde/sde1/holders': Directory(),
            '/sys/block/sde/sde2/size': '2\n',
            '/sys/block/sde/sde2/start': '1001470\n',
            '/sys/block/sde/sde2/holders': Directory(),
            '/sys/block/sde/sde5/size': '975769600\n',
            '/sys/block/sde/sde5/start': '1001472\n',
            '/sys/block/sde/sde5/holders/dm-0': Symlink('../../../../../../../../../../virtual/block/dm-0'),
        })
        self.patch_commands({
            'pvdisplay -c 2>/dev/null': (
                '  /dev/mapper/sde5_crypt:platonas:975765504:-1:8:8:-1:4096:119111:0:119111:mRMbR0-4xMf-IuXS-cx20-gXJW-r6MG-QewhqEn\n'
                '  /dev/sda9:fridge:976755038:-1:8:8:-1:4096:119232:66996:52236:cGLoDM-0HFH-u8X8-66T7-2u6k-LM13-6fyNVk\n'
                '  /dev/sdb9:fridge:976755038:-1:8:8:-1:4096:119232:66996:52236:zLNTe2-usSn-9cJC-Atqa-wjwX-dUsQ-3jtI3E\n'
                '  /dev/sdc2:fridge:486443376:-1:8:8:-1:4096:59380:33779:25601:VUA1rj-ZAdJ-VxuO-Cbb0-8DQz-B5Yf-zRuR2x\n'
                '  /dev/sdd2:fridge:486443376:-1:8:8:-1:4096:59380:33779:25601:0uEuwq-6HB5-9zqB-5fnS-K4pX-RSlH-CKOrrj\n'
            ),
            'vgdisplay -c 2>/dev/null': (
                '  platonas:r/w:772:-1:0:2:2:-1:0:1:1:487878656:4096:119111:119111:0:jzd3VL-RR7v-44tD-O8zO-9sSI-qFEs-hpmnPE\n'
                '  fridge:r/w:772:-1:0:13:10:-1:0:4:4:1463189504:4096:357224:155674:201550:vdq2Ht-m5RN-rD0v-lTEf-oqtN-LGm4-UGZDn2\n'
            ),
            'lvs --separator=: --units=b --nosuffix --noheadings -o lv_name,vg_name,lv_size,lv_dm_path,lv_role,devices,metadata_devices,lv_device_open --all 2>/dev/null': (
                '  root:platonas:491119443968:/dev/mapper/platonas-root:public:/dev/mapper/sda5_crypt(0)::open\n'
                '  swap_1:platonas:8468299776:/dev/mapper/platonas-swap_1:public:/dev/mapper/sda5_crypt(117092)::open\n'
                '  apache-logs:fridge:21474836480:/dev/mapper/fridge-apache--logs:public:apache-logs_rimage_0(0),apache-logs_rimage_1(0):apache-logs_rmeta_0(0),apache-logs_rmeta_1(0):open\n'
                '  [apache-logs_rimage_0]:fridge:21474836480:/dev/mapper/fridge-apache--logs_rimage_0:private,raid,image:/dev/sdc9(10249)::open\n'
                '  [apache-logs_rimage_1]:fridge:21474836480:/dev/mapper/fridge-apache--logs_rimage_1:private,raid,image:/dev/sdd9(34058)::open\n'
                '  [apache-logs_rmeta_0]:fridge:4194304:/dev/mapper/fridge-apache--logs_rmeta_0:private,raid,metadata:/dev/sdc9(10248)::open\n'
                '  [apache-logs_rmeta_1]:fridge:4194304:/dev/mapper/fridge-apache--logs_rmeta_1:private,raid,metadata:/dev/sdd9(34057)::open\n'
                '  cache:fridge:10737418240:/dev/mapper/fridge-cache:public:cache_rimage_0(0),cache_rimage_1(0):cache_rmeta_0(0),cache_rmeta_1(0):open\n'
                '  [cache_rimage_0]:fridge:10737418240:/dev/mapper/fridge-cache_rimage_0:private,raid,image:/dev/sdc9(20480)::open\n'
                '  [cache_rimage_1]:fridge:10737418240:/dev/mapper/fridge-cache_rimage_1:private,raid,image:/dev/sdd9(15366)::open\n'
                '  [cache_rmeta_0]:fridge:4194304:/dev/mapper/fridge-cache_rmeta_0:private,raid,metadata:/dev/sdc9(10244)::open\n'
                '  [cache_rmeta_1]:fridge:4194304:/dev/mapper/fridge-cache_rmeta_1:private,raid,metadata:/dev/sdd9(15365)::open\n'
                '  home-ssd:fridge:107374182400:/dev/mapper/fridge-home--ssd:public:home-ssd_rimage_0(0),home-ssd_rimage_1(0):home-ssd_rmeta_0(0),home-ssd_rmeta_1(0):open\n'
                '  [home-ssd_rimage_0]:fridge:107374182400:/dev/mapper/fridge-home--ssd_rimage_0:private,raid,image:/dev/sda2(1)::open\n'
                '  [home-ssd_rimage_1]:fridge:107374182400:/dev/mapper/fridge-home--ssd_rimage_1:private,raid,image:/dev/sdb2(1)::open\n'
                '  [home-ssd_rmeta_0]:fridge:4194304:/dev/mapper/fridge-home--ssd_rmeta_0:private,raid,metadata:/dev/sda2(0)::open\n'
                '  [home-ssd_rmeta_1]:fridge:4194304:/dev/mapper/fridge-home--ssd_rmeta_1:private,raid,metadata:/dev/sdb2(0)::open\n'
                '  jenkins:fridge:21474836480:/dev/mapper/fridge-jenkins:public:jenkins_rimage_0(0),jenkins_rimage_1(0):jenkins_rmeta_0(0),jenkins_rmeta_1(0):open\n'
                '  [jenkins_rimage_0]:fridge:21474836480:/dev/mapper/fridge-jenkins_rimage_0:private,raid,image:/dev/sdc9(5120)::open\n'
                '  [jenkins_rimage_1]:fridge:21474836480:/dev/mapper/fridge-jenkins_rimage_1:private,raid,image:/dev/sdd9(10245)::open\n'
                '  [jenkins_rmeta_0]:fridge:4194304:/dev/mapper/fridge-jenkins_rmeta_0:private,raid,metadata:/dev/sdc9(10243)::open\n'
                '  [jenkins_rmeta_1]:fridge:4194304:/dev/mapper/fridge-jenkins_rmeta_1:private,raid,metadata:/dev/sdd9(10244)::open\n'
                '  mailman:fridge:10737418240:/dev/mapper/fridge-mailman:public:mailman_rimage_0(0),mailman_rimage_1(0):mailman_rmeta_0(0),mailman_rmeta_1(0):open\n'
                '  [mailman_rimage_0]:fridge:10737418240:/dev/mapper/fridge-mailman_rimage_0:private,raid,image:/dev/sdc9(25600)::open\n'
                '  [mailman_rimage_1]:fridge:10737418240:/dev/mapper/fridge-mailman_rimage_1:private,raid,image:/dev/sdd9(5123)::open\n'
                '  [mailman_rmeta_0]:fridge:4194304:/dev/mapper/fridge-mailman_rmeta_0:private,raid,metadata:/dev/sdc9(10241)::open\n'
                '  [mailman_rmeta_1]:fridge:4194304:/dev/mapper/fridge-mailman_rmeta_1:private,raid,metadata:/dev/sdd9(5122)::open\n'
                '  openerp:fridge:22548578304:/dev/mapper/fridge-openerp:public:openerp_rimage_0(0),openerp_rimage_1(0):openerp_rmeta_0(0),openerp_rmeta_1(0):open\n'
                '  openerp-xenial:fridge:22548578304:/dev/mapper/fridge-openerp--xenial:public:openerp-xenial_rimage_0(0),openerp-xenial_rimage_1(0):openerp-xenial_rmeta_0(0),openerp-xenial_rmeta_1(0):open\n'
                '  [openerp-xenial_rimage_0]:fridge:22548578304:/dev/mapper/fridge-openerp--xenial_rimage_0:private,raid,image:/dev/sda2(25601)::open\n'
                '  [openerp-xenial_rimage_1]:fridge:22548578304:/dev/mapper/fridge-openerp--xenial_rimage_1:private,raid,image:/dev/sdb2(25601)::open\n'
                '  [openerp-xenial_rmeta_0]:fridge:4194304:/dev/mapper/fridge-openerp--xenial_rmeta_0:private,raid,metadata:/dev/sda2(30977)::open\n'
                '  [openerp-xenial_rmeta_1]:fridge:4194304:/dev/mapper/fridge-openerp--xenial_rmeta_1:private,raid,metadata:/dev/sdb2(30977)::open\n'
                '  [openerp_rimage_0]:fridge:22548578304:/dev/mapper/fridge-openerp_rimage_0:private,raid,image:/dev/sdc9(28160)::open\n'
                '  [openerp_rimage_1]:fridge:22548578304:/dev/mapper/fridge-openerp_rimage_1:private,raid,image:/dev/sdd9(17927)::open\n'
                '  [openerp_rmeta_0]:fridge:4194304:/dev/mapper/fridge-openerp_rmeta_0:private,raid,metadata:/dev/sdc9(10245)::open\n'
                '  [openerp_rmeta_1]:fridge:4194304:/dev/mapper/fridge-openerp_rmeta_1:private,raid,metadata:/dev/sdd9(17926)::open\n'
                '  precise64:fridge:22548578304:/dev/mapper/fridge-precise64:public:precise64_rimage_0(0),precise64_rimage_1(0):precise64_rmeta_0(0),precise64_rmeta_1(0):open\n'
                '  [precise64_rimage_0]:fridge:22548578304:/dev/mapper/fridge-precise64_rimage_0:private,raid,image:/dev/sdc9(38912)::open\n'
                '  [precise64_rimage_1]:fridge:22548578304:/dev/mapper/fridge-precise64_rimage_1:private,raid,image:/dev/sdd9(28681)::open\n'
                '  [precise64_rmeta_0]:fridge:4194304:/dev/mapper/fridge-precise64_rmeta_0:private,raid,metadata:/dev/sdc9(10247)::open\n'
                '  [precise64_rmeta_1]:fridge:4194304:/dev/mapper/fridge-precise64_rmeta_1:private,raid,metadata:/dev/sdd9(28680)::open\n'
                '  root:fridge:21474836480:/dev/mapper/fridge-root:public:root_rimage_0(0),root_rimage_1(0):root_rmeta_0(0),root_rmeta_1(0):open\n'
                '  [root_rimage_0]:fridge:21474836480:/dev/mapper/fridge-root_rimage_0:private,raid,image:/dev/sda2(30979)::open\n'
                '  [root_rimage_1]:fridge:21474836480:/dev/mapper/fridge-root_rimage_1:private,raid,image:/dev/sdb2(30979)::open\n'
                '  [root_rmeta_0]:fridge:4194304:/dev/mapper/fridge-root_rmeta_0:private,raid,metadata:/dev/sda2(30978)::open\n'
                '  [root_rmeta_1]:fridge:4194304:/dev/mapper/fridge-root_rmeta_1:private,raid,metadata:/dev/sdb2(30978)::open\n'
                '  supybot:fridge:10737418240:/dev/mapper/fridge-supybot:public:supybot_rimage_0(0),supybot_rimage_1(0):supybot_rmeta_0(0),supybot_rmeta_1(0):open\n'
                '  [supybot_rimage_0]:fridge:10737418240:/dev/mapper/fridge-supybot_rimage_0:private,raid,image:/dev/sda2(36099)::open\n'
                '  [supybot_rimage_1]:fridge:10737418240:/dev/mapper/fridge-supybot_rimage_1:private,raid,image:/dev/sdb2(36099)::open\n'
                '  [supybot_rmeta_0]:fridge:4194304:/dev/mapper/fridge-supybot_rmeta_0:private,raid,metadata:/dev/sda2(38659)::open\n'
                '  [supybot_rmeta_1]:fridge:4194304:/dev/mapper/fridge-supybot_rmeta_1:private,raid,metadata:/dev/sdb2(38659)::open\n'
                '  tmp:fridge:21474836480:/dev/mapper/fridge-tmp:public:tmp_rimage_0(0),tmp_rimage_1(0):tmp_rmeta_0(0),tmp_rmeta_1(0):open\n'
                '  [tmp_rimage_0]:fridge:21474836480:/dev/mapper/fridge-tmp_rimage_0:private,raid,image:/dev/sdc9(0)::open\n'
                '  [tmp_rimage_1]:fridge:21474836480:/dev/mapper/fridge-tmp_rimage_1:private,raid,image:/dev/sdd9(0)::open\n'
                '  [tmp_rmeta_0]:fridge:4194304:/dev/mapper/fridge-tmp_rmeta_0:private,raid,metadata:/dev/sdc9(10240)::open\n'
                '  [tmp_rmeta_1]:fridge:4194304:/dev/mapper/fridge-tmp_rmeta_1:private,raid,metadata:/dev/sdd9(5121)::open\n'
                '  trusty64:fridge:22548578304:/dev/mapper/fridge-trusty64:public:trusty64_rimage_0(0),trusty64_rimage_1(0):trusty64_rmeta_0(0),trusty64_rmeta_1(0):open\n'
                '  [trusty64_rimage_0]:fridge:22548578304:/dev/mapper/fridge-trusty64_rimage_0:private,raid,image:/dev/sdc9(33536)::open\n'
                '  [trusty64_rimage_1]:fridge:22548578304:/dev/mapper/fridge-trusty64_rimage_1:private,raid,image:/dev/sdd9(23304)::open\n'
                '  [trusty64_rmeta_0]:fridge:4194304:/dev/mapper/fridge-trusty64_rmeta_0:private,raid,metadata:/dev/sdc9(10246)::open\n'
                '  [trusty64_rmeta_1]:fridge:4194304:/dev/mapper/fridge-trusty64_rmeta_1:private,raid,metadata:/dev/sdd9(23303)::open\n'
                '  www:fridge:10737418240:/dev/mapper/fridge-www:public:www_rimage_0(0),www_rimage_1(0):www_rmeta_0(0),www_rmeta_1(0):open\n'
                '  [www_rimage_0]:fridge:10737418240:/dev/mapper/fridge-www_rimage_0:private,raid,image:/dev/sda2(38661)::open\n'
                '  [www_rimage_1]:fridge:10737418240:/dev/mapper/fridge-www_rimage_1:private,raid,image:/dev/sdb2(38661)::open\n'
                '  [www_rmeta_0]:fridge:4194304:/dev/mapper/fridge-www_rmeta_0:private,raid,metadata:/dev/sda2(38660)::open\n'
                '  [www_rmeta_1]:fridge:4194304:/dev/mapper/fridge-www_rmeta_1:private,raid,metadata:/dev/sdb2(38660)::open\n'
                '  xenial64:fridge:22548578304:/dev/mapper/fridge-xenial64:public:xenial64_rimage_0(0),xenial64_rimage_1(0):xenial64_rmeta_0(0),xenial64_rmeta_1(0):open\n'
                '  [xenial64_rimage_0]:fridge:22548578304:/dev/mapper/fridge-xenial64_rimage_0:private,raid,image:/dev/sdc9(44289)::open\n'
                '  [xenial64_rimage_1]:fridge:22548578304:/dev/mapper/fridge-xenial64_rimage_1:private,raid,image:/dev/sdd9(39179)::open\n'
                '  [xenial64_rmeta_0]:fridge:4194304:/dev/mapper/fridge-xenial64_rmeta_0:private,raid,metadata:/dev/sdc9(44288)::open\n'
                '  [xenial64_rmeta_1]:fridge:4194304:/dev/mapper/fridge-xenial64_rmeta_1:private,raid,metadata:/dev/sdd9(39178)::open\n'
            ),
            'dmsetup -c --noheadings info': textwrap.dedent('''\
                platonas-swap_1:253:2:L--w:2:1:0:LVM-blahblah
                platonas-root:253:1:L--w:1:1:0:LVM-blahblah
                sde5_crypt:253:0:L--w:2:1:0:CRYPT-LUKS1-blah-sde5_crypt
                fridge-precise64_rmeta_1:252:42:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2wVDxoyO1ey0Nl94FSk7WSpC5j0H1ZzQI
                fridge-trusty64_rimage_1:252:38:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2jRwdcCkzuzRnzZstcBFueIM0JPdg6TwZ
                fridge-apache--logs_rimage_1:252:48:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2LL0Rw3wiVRURGAivNdA4pcMQ8IjZzzyJ
                fridge-tmp_rmeta_0:252:5:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2Hfc33iWdSn9N06Q0xPyzNDvz9prbZKuE
                fridge-xenial64_rmeta_1:252:67:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2luNaFdQPqonUV0QWi9f901GtpJXauiYt
                fridge-trusty64:252:39:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2sD2oxRES8SmvHA0gc0HD5gF7mA54Lok7
                fridge-precise64_rmeta_0:252:40:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn20MBeyN6uOzF2Nqw5F2in2K2g1SoSZlpR
                fridge-trusty64_rimage_0:252:36:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2f7iHwVlPoby3DqTAoyoZ88sJLUkzSqQV
                fridge-openerp_rimage_1:252:33:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2xMjyUUhS8GSQvnw8d7TgQvbEYIffzihX
                fridge-apache--logs_rimage_0:252:46:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2ulQdkpl3Ke9SwaDyLB7gbdGNXKdkBVVH
                fridge-xenial64_rmeta_0:252:65:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2YmFOfmqNJr1cxYQKmdO5nPuHl8K30VXL
                fridge-openerp--xenial_rimage_1:252:63:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2OO5qr7x4Fn8ior8J6QdjhJzLXdXgTwNn
                fridge-openerp_rimage_0:252:31:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2ksxmomSjYZM3NJnWGwapZXVxBoM6IL2n
                fridge-mailman:252:29:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2IMafMeWyxqcEVeurfqMeeZX6AvDQJg1I
                fridge-cache:252:19:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2OAo093QsrETFEbGXO5HxerdYQOBmpxST
                fridge-openerp--xenial_rimage_0:252:61:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2ypFN8dlIqGn1ir5FVo5QjyRi3ViTjIfl
                fridge-www_rimage_1:252:23:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn20aAVwKKKO3vOVvYq7oHm5rCnQ3gQTcFh
                fridge-xenial64_rimage_1:252:68:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2tsCDyRirdO7r0SXeL033Fhk5qO3K2ss1
                fridge-apache--logs_rmeta_1:252:47:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2s7T0Tk56t7bhZW0jWtieR7shXpMycaUX
                fridge-tmp:252:9:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2m3LMrLqpX33hpCNreoBDNfk2aqaKuDxg
                fridge-www_rimage_0:252:21:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn21VGsjYOmJgJrtJPAdWkqpTZ6qr7LZ64W
                fridge-precise64:252:44:L--w:0:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2cw0trvk4Bgq3kyOxQveXYs7gGuVI8oSr
                fridge-xenial64_rimage_0:252:66:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2N3q1qN0gxmq5clIBb4ZwnVEGI2IeEAiV
                fridge-cache_rmeta_1:252:17:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2M0g2fnzl0U4Yy2AAf0l6j0fgpwsH45wl
                fridge-mailman_rimage_1:252:28:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn26cyRAraeD07BFMTPEL7w2Q81fV32uaWs
                fridge-apache--logs_rmeta_0:252:45:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2d62bEVHkjzwBzpi2JJY1Tq7cImPyYB4D
                fridge-xenial64:252:69:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2E0gHem31V535f3Zu2jOOO8w9fpT3elmI
                fridge-supybot:252:54:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2qVxudNxbBorSjvC1DqRZ57CMIB7z17Fq
                fridge-cache_rmeta_0:252:15:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn29tlHmFFR3yp1FTRk7YTAqXuIsfnzOjlm
                fridge-mailman_rimage_0:252:26:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2BKcuJlb2ffpZ7fsmkoR6kNwZpixBnfT7
                fridge-jenkins:252:14:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2U9xpzqqryOM0V85cesJdWTY88AslytGX
                fridge-root:252:4:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2xzffFsRpeKxq5couqMvF2ddsNZCKKYXa
                fridge-www_rmeta_1:252:22:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn276ZhVeFCFc0dwT050G6hEF6IRuxOnn2B
                fridge-openerp_rmeta_1:252:32:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2t8tbRWsEM2co6FdzpO9tiT3xqqPvOmR4
                fridge-www_rmeta_0:252:20:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn234O9XrQWdafP6Kskywrn1wk8Gtrj04A5
                fridge-jenkins_rimage_1:252:13:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2d6RlumxXZ01oHIKUTbbX7qqsPhNK8JiJ
                fridge-root_rimage_1:252:3:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2OUguRdOCBgArX3swA9PliFMj9Ew9MF4o
                fridge-home--ssd_rmeta_1:252:57:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2WteaKeVVq9f91BHkc6p0AlpZKWVnvHAa
                fridge-supybot_rmeta_1:252:52:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2v8D3LKvYvpCwSNMaa1z5fngbFt1fAdf5
                fridge-openerp_rmeta_0:252:30:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2zXVgjP5sBfkdQ0zMl7pTbK8AXxYTlge4
                fridge-precise64_rimage_1:252:43:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2Rnb5djJzIWtGnWJCfJ8xMR5nQpuIetU0
                fridge-jenkins_rmeta_1:252:12:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2jJTlIINdASml8QMmVHYGROJKTGNkO1mP
                fridge-root_rmeta_1:252:2:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2dEkrz0ULzZ6rSDySXN2pSgDTJUK06RSv
                fridge-jenkins_rimage_0:252:11:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2EFtaS5TH1e25xA0vhXK5E1VEM78rcaN2
                fridge-root_rimage_0:252:1:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2u3LCQzNe5HgftW1klPvC2dHzfYI43Ezo
                fridge-home--ssd_rmeta_0:252:55:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2UfRymlJ1RSuN11lgFDFxFYCP9XkCklA1
                fridge-supybot_rmeta_0:252:50:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2lvD4xoHG2INDREfWC765D1g7CptszrZS
                fridge-apache--logs:252:49:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2FDm2WJHEITXpQzBF1rnzIfDA93Pk6GLp
                fridge-precise64_rimage_0:252:41:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2etXaBFpMRMECJTGMzynBxCtvU9nWmkDg
                fridge-jenkins_rmeta_0:252:10:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2F2yHQlmhiodo0j4qeQT7WK6fvh4kGwCS
                fridge-root_rmeta_0:252:0:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2U7JDZ0RG4CRHeUyeJZjgXks4O4WtqL7W
                fridge-supybot_rimage_1:252:53:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn23GlAb6LpZekABgkumLZuKIIhRz0DE0ut
                fridge-trusty64_rmeta_1:252:37:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2iwOjzl2CMYTFE3CxhGIbpTeUB9nj2PqV
                fridge-openerp--xenial:252:64:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn23YHFuSzt5gUzF7W4kfE564Asgg2uoreF
                fridge-tmp_rimage_1:252:8:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2udEp4QPNcAqz6cbDaPBZ51Ozo8IHwHEv
                fridge-home--ssd_rimage_1:252:58:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn20QyYfJkw4WHtMNj3sv1NgR4A0jCIcGwu
                fridge-supybot_rimage_0:252:51:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2xTIv3B0iY8a4bGtgT2jEBwTYcXzRms3T
                fridge-trusty64_rmeta_0:252:35:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2K2HqB2rhGMl0D5qA1rmCz2498dmPVzKT
                fridge-cache_rimage_1:252:18:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2i24iv3o3R32FZQinY3bfqNWikkLEgzyQ
                fridge-www:252:24:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn29qGwS4YYlWpXafUm2pTB51cq9e5v4clX
                fridge-tmp_rimage_0:252:6:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn20vVj5xO5bmY7f5KlZwhfiK4eJfAiarfT
                fridge-openerp:252:34:L--w:0:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2gClj1O6U8a1x70slRyUyFFmhRCUC1gsY
                fridge-mailman_rmeta_1:252:27:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2EIFowTAgICsPWaEWaVNnNqJcb9bdqvxo
                fridge-home--ssd_rimage_0:252:56:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn28ncHsoBVONvt20RIOv0aKWQR5ukgThME
                fridge-cache_rimage_0:252:16:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2nk1b2nX4ahLnNPP9Jtir6IlQZyUtwhfE
                fridge-openerp--xenial_rmeta_1:252:62:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2QgajEtcGbd42OEcyzYeMflgqy8SBPYuI
                fridge-home--ssd:252:59:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2vB6CnTbSixH8y9OSVcChK3liRKjD9z0O
                fridge-mailman_rmeta_0:252:25:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2WS6zkzjs7e6Xjz5CYF7DoWOWZ003ps6a
                fridge-openerp--xenial_rmeta_0:252:60:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2QuTJWBrTe3dKqKRl28T2TiDORlGATe9S
                fridge-tmp_rmeta_1:252:7:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2qmBiBIWDAUTV09fMpC0xGKebam9pluqd
                fridge-precise64_rmeta_1:252:42:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2wVDxoyO1ey0Nl94FSk7WSpC5j0H1ZzQI
                fridge-trusty64_rimage_1:252:38:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2jRwdcCkzuzRnzZstcBFueIM0JPdg6TwZ
                fridge-apache--logs_rimage_1:252:48:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2LL0Rw3wiVRURGAivNdA4pcMQ8IjZzzyJ
                fridge-tmp_rmeta_0:252:5:L--w:1:1:0:LVM-vdq2Htm5RNrD0vlTEfoqtNLGm4UGZDn2Hfc33iWdSn9N06Q0xPyzNDvz9prbZKuE
            '''),
            'df -P --local --print-type -x debugfs': textwrap.dedent('''\
                Filesystem                Type     1024-blocks      Used Available Capacity Mounted on
            '''),
        })
        self.assertMultiLineEqual(di.report_text() + '\n', textwrap.dedent('''\
            sda: Samsung SSD 850 (250.1 GB)
                                250.1 GB (unused)
            sdb: Samsung SSD 850 (250.1 GB)
                                250.1 GB (unused)
            sde: Samsung SSD 850 (500.1 GB)
              sde1:             510.7 MB
              sde5:             499.6 GB  LVM: platonas                        0.0 B free
            platonas: LVM (499.6 GB)
              root:             491.1 GB
              swap_1:             8.5 GB  swap
            fridge: LVM (1.5 TB)
              apache-logs:       21.5 GB
              cache:             10.7 GB
              home-ssd:         107.4 GB
              jenkins:           21.5 GB
              mailman:           10.7 GB
              openerp:           22.5 GB
              openerp-xenial:    22.5 GB
              precise64:         22.5 GB
              root:              21.5 GB
              supybot:           10.7 GB
              tmp:               21.5 GB
              trusty64:          22.5 GB
              www:               10.7 GB
              xenial64:          22.5 GB
              free:             845.4 GB
        '''))
        # Smoke test
        di.report_text(verbose=2)
        # Smoke test, I'm not going to compare the HTML unless I find a regression
        di.report_html(verbose=2)


class TestMain(TestCase):

    def run_main(self, *args):
        self.patch('sys.argv', ['disk-inventory'] + list(args))
        di.main()

    def test_main(self):
        self.patch('sys.stdout', NativeStringIO())
        self.patch_files({
            '/sys/block': Directory(),
        })
        self.patch_commands({
            'vgdisplay -c 2>/dev/null': '',
        })
        self.run_main()

    def test_main_html(self):
        self.patch('sys.stdout', NativeStringIO())
        self.patch_files({
            '/sys/block': Directory(),
        })
        self.patch_commands({
            'vgdisplay -c 2>/dev/null': '',
        })
        self.run_main('--html')
