#!/usr/bin/python
"""
Produce a disk inventory for a system:

  - how many hard disks and how large
  - how are they partitioned
  - how are the RAID devices defined
  - where are they mounted
  - how much space is used and how much is free

Written by Marius Gedminas <marius@pov.lt>
"""

from __future__ import print_function

import collections
import functools
import optparse
import os
import sys
from xml.etree import ElementTree as ET

try:
    from html import escape
except ImportError:
    from cgi import escape


__author__ = 'Marius Gedminas <marius@gedmin.as>'
__version__ = '1.6.4'
__date__ = '2022-02-22'


FilesystemInfo = collections.namedtuple(
    'FilesystemInfo', 'device mountpoint fstype size_kb used_kb avail_kb')

PVInfo = collections.namedtuple('PVInfo', 'device vgname free_kb')

VGInfo = collections.namedtuple('VGInfo', 'name size_kb used_kb free_kb')

LVInfo = collections.namedtuple('LVInfo', 'name vgname size_bytes device role located_on is_open')

DMInfo = collections.namedtuple('LVInfo', 'name major minor')

DMName = collections.namedtuple('LVInfo', 'name number')

KVMInfo = collections.namedtuple('KVMInfo', 'name device')


class once(object):
    """Property that is computed once, on 1st access, and then cached."""

    def __init__(self, fn):
        self.fn = fn
        self.name = fn.__name__

    def __get__(self, instance, owner):
        value = self.fn(instance)
        setattr(instance, self.name, value)
        return value


def cache(fn):
    """Decorator that caches a function's return value on first run."""
    @functools.wraps(fn)
    def wrapper(self):
        if not hasattr(self, cache_name):
            setattr(self, cache_name, fn(self))
        return getattr(self, cache_name)
    cache_name = '_{}_cache'.format(fn.__name__)
    return wrapper


class LinuxDiskInfo(object):

    @once
    def _swap_devices(self):
        return self.list_swap_devices()

    @once
    def _filesystems(self):
        return self.list_filesystems()

    @once
    def _filesystems_by_device(self):
        return {r.device: r for r in self._filesystems}

    @once
    def _lvm_pvs(self):
        return {pv.device: pv for pv in self.list_lvm_physical_volumes()}

    @once
    def _lvm_lvs(self):
        return {(lv.vgname, lv.name): lv for lv in self.list_lvm_all_logical_volumes()}

    @once
    def _kvm_vms(self):
        return {vm.device: vm for vm in self.list_kvm_vms()}

    @once
    def _dms(self):
        return {dm.name: dm for dm in self.list_device_mapper()}

    @property
    def _dm_names(self):
        return {dm.number: dm.name for dm in self.list_device_mapper_names()}

    def _read_string(self, filename):
        with open(filename) as f:
            return f.read().strip()

    def _read_int(self, filename):
        return int(self._read_string(filename))

    def _canonical_device_name(self, device):
        if not device.startswith('/dev/'):
            return None
        name = device[len('/dev/'):]
        if name.startswith('cciss/'):
            name = name.replace('/', '!')
        if name.startswith('dm-'):
            name = self._dm_names.get(name, name)
        if '/' in name and not name.startswith('mapper/'):
            try:
                target = os.readlink(device)
            except OSError:
                pass
            else:
                if target.startswith('../dm-'):
                    name = self._dm_names.get(target[len('../'):], name)
        return name

    def warn(self, message):
        print(message, file=sys.stderr)

    @cache
    def list_swap_devices(self):
        """Return short device names such as ['sda1']"""
        res = []
        with open('/proc/swaps') as f:
            f.readline() # skip header
            for line in f:
                filename = line.split()[0]
                name = self._canonical_device_name(filename)
                if name:
                    res.append(name)
        return res

    @cache
    def list_filesystems(self):
        """Return a list of FilesystemInfo tuples."""
        res = []
        with os.popen('df -P --local --print-type -x debugfs') as f:
            f.readline() # skip header
            for line in f:
                device, fstype, size_kb, used_kb, avail_kb, use_percent, mountpoint = line.split()
                name = self._canonical_device_name(device)
                if name:
                    res.append(FilesystemInfo(name, mountpoint, fstype, int(size_kb), int(used_kb), int(avail_kb)))
        return res

    @cache
    def list_physical_disks(self):
        """Return physical disk names such as ['sda', 'sdb'].

        Limitations: only handles ATA/SATA/SCSI disks; no RAID or whatnot.
        """
        if os.path.exists('/sys/block'):
            return sorted(name for name in os.listdir('/sys/block')
                          if name.startswith(('sd', 'cciss', 'xvd', 'vd', 'nvme')))
            # XXX: maybe also list mmcblk in case somebody runs this on a
            # Raspberry Pi or something
            # XXX: maybe I should filter out non-disk devices like loop and dm and md
            # instead of recognizing actual drives
        elif os.path.exists('/dev/simfs'):
            # OpenVZ container
            return ['simfs']
        else:
            self.warn("disk-inventory: cannot discover block devices: /sys/block is missing")
            return []

    @cache
    def list_device_mapper(self):
        """Return a list of DMInfo tuples."""
        res = []
        with os.popen('dmsetup -c --noheadings info') as f:
            for line in f:
                # name, major, minor, attr, open, segments,  events,  uuid.
                name, major, minor, _, _, _, _, _ = line.split(':')
                res.append(DMInfo(name, int(major), int(minor)))
        return res

    @cache
    def list_device_mapper_names(self):
        """Return a list of DMName tuples."""
        # XXX: I could construct this from self._dms, using self.get_dm_for()
        res = []
        try:
            for name in os.listdir('/dev/mapper'):
                try:
                    number = os.readlink('/dev/mapper/' + name).split('/')[-1]
                except OSError:
                    continue
                res.append(DMName('mapper/' + name, number))
        except OSError:
            pass
        return res

    @cache
    def list_lvm_volume_groups(self):
        """Return volume groups names."""
        res = []
        if os.getuid() != 0:
            self.warn("disk-inventory: cannot list LVM devices: running as non-root")
        with os.popen('vgdisplay -c 2>/dev/null') as f:
            for line in f:
                # columns:
                # 1  volume group name
                # 2  volume group access
                # 3  volume group status
                # 4  internal volume group number
                # 5  maximum number of logical volumes
                # 6  current number of logical volumes
                # 7  open count of all logical volumes in this volume group
                # 8  maximum logical volume size
                # 9  maximum number of physical volumes
                # 10 current number of physical volumes
                # 11 actual number of physical volumes
                # 12 size of volume group in kilobytes
                # 13 physical extent size
                # 14 total number of physical extents for this volume group
                # 15 allocated number of physical extents for this volume group
                # 16 free number of physical extents for this volume group
                # 17 uuid of volume group
                (vgname, _, _, _, _, _, _, _, _, _, _, size_kb, extent_size_kb,
                 n_extents, used_extents, free_extents,
                 uuid) = line.strip().split(':')
                res.append(VGInfo(vgname, int(size_kb),
                                  int(used_extents) * int(extent_size_kb),
                                  int(free_extents) * int(extent_size_kb)))
        return res

    @cache
    def list_lvm_physical_volumes(self):
        """Return a list of PVInfo tuples."""
        res = []
        with os.popen('pvdisplay -c 2>/dev/null') as f:
            for line in f:
                # the "wtf" column is "physical volume (not) allocatable"
                # the _ column is "internal physical volume number (obsolete)"
                try:
                    (device, vgname, size_kb, _, status, wtf, n_volumes,
                     extent_size_kb, n_extents, free_extents,
                     used_extents, uuid) = line.strip().split(':')
                    extent_size_kb = int(extent_size_kb)
                    free_extents = int(free_extents)
                except ValueError:
                    # Could be something like a
                    #    "/dev/sdc2" is a new physical volume of "231.95 GiB"
                    # which shows up when you pvcreate but don't vgextend.
                    pass
                else:
                    if device.startswith('/dev/'):
                        res.append(PVInfo(device[len('/dev/'):], vgname,
                                          free_extents * extent_size_kb))
        return res

    @cache
    def list_lvm_all_logical_volumes(self):
        res = []
        columns = 'lv_name,vg_name,lv_size,lv_dm_path,lv_role,devices,metadata_devices,lv_device_open'
        with os.popen('lvs --separator=: --units=b --nosuffix --noheadings -o {} --all 2>/dev/null'.format(columns)) as f:
            for line in f:
                (lvname, vgname, lv_size_bytes, lv_dm_path, lv_role, devices,
                 meta_devices, device_open) = line.strip().split(':')
                assert lv_dm_path.startswith('/dev/mapper/')
                device = lv_dm_path[len('/dev/'):]
                located_on = {d.partition('(')[0] for d in devices.split(',') + meta_devices.split(',') if d}
                res.append(LVInfo(lvname, vgname, int(lv_size_bytes), device, lv_role, located_on, bool(device_open)))
        return res

    @cache
    def list_lvm_logical_volumes(self):
        return [lv for lv in self.list_lvm_all_logical_volumes()
                if lv.role == 'public']

    @cache
    def list_kvm_vms(self):
        libvirt_dir = '/etc/libvirt/qemu'
        if not os.path.exists(libvirt_dir):
            return []
        res = []
        for filename in os.listdir(libvirt_dir):
            if filename.endswith('.xml'):
                name = filename[:-len('.xml')]
                try:
                    t = ET.parse(os.path.join(libvirt_dir, filename))
                except IOError:  # nocover: difficult to test
                    # if you're not root, you'll get permission denied
                    # from reading these
                    continue
                for source in t.findall('.//disk/source'):
                    disk_file = source.get('file') or source.get('dev')
                    if disk_file and disk_file.startswith('/dev/'):
                        dev = self._canonical_device_name(disk_file)
                        res.append(KVMInfo(name, dev))
        return res

    def get_disk_size_sectors(self, disk_name):
        return self._read_int('/sys/block/%s/size' % disk_name)

    def get_disk_size_bytes(self, disk_name):
        if disk_name == 'simfs':
            # iv.lt VPSes have no /sys/block; they mount /dev/simfs on /
            r = os.statvfs('/')
            return r.f_blocks * r.f_bsize
        # Experiments show that the kernel always reports 512-byte sectors,
        # even when the disk uses 4KiB sectors.  This is apparently by design,
        # although it isn't currently documented.
        return self.get_disk_size_sectors(disk_name) * 512

    def get_disk_model(self, disk_name):
        if disk_name.startswith('xvd'):
            return 'Xen virtual disk'
        if disk_name.startswith('vd'):
            return 'KVM virtual disk'
        if disk_name == 'simfs':
            return 'OpenVZ virtual filesystem'
        return self._read_string('/sys/block/%s/device/model' % disk_name)

    def get_disk_firmware_rev(self, disk_name):
        if disk_name.startswith(('xvd', 'vd', 'simfs')):
            return 'N/A'
        filename = '/sys/block/%s/device/firmware_rev' % disk_name
        if not os.path.exists(filename):
            filename = '/sys/block/%s/device/rev' % disk_name
        return self._read_string(filename)

    def is_disk_an_ssd(self, disk_name):
        if disk_name == 'simfs':
            return False
        try:
            rot = self._read_string('/sys/block/%s/queue/rotational' % disk_name)
        except IOError:
            # could be a devmapper thing, e.g. dm-crypt
            return False
        return rot.strip() == '0'

    def list_partitions(self, disk_name):
        """Return partition names such as ['sda1', ...].

        Includes primary, extended and logical partition names.
        """
        if disk_name == 'simfs':
            # OpenVZ container
            return ['simfs']
        return sorted(name for name in os.listdir('/sys/block/%s' % disk_name)
                      if name.startswith(disk_name))

    def get_dm_for(self, name):
        """Find device mapper with a given name."""
        return 'dm-%d' % self._dms[name].minor

    def get_sys_dir_for_partition(self, partition_name):
        """Find /sys directory name from partition name (e.g. 'sda1')."""
        if partition_name.startswith('mapper/'):
            name = partition_name[len('mapper/'):]
            return '/sys/block/%s' % self.get_dm_for(name)
        disk_name = partition_name.rstrip('0123456789')
        if disk_name.endswith('p'):
            disk_name = disk_name[:-1]
        return '/sys/block/%s/%s' % (disk_name, partition_name)

    def get_partition_size_sectors(self, partition_name):
        sysdir = self.get_sys_dir_for_partition(partition_name)
        return self._read_int(sysdir + '/size')

    def get_partition_size_bytes(self, partition_name):
        if partition_name == 'simfs':
            return self.get_disk_size_bytes('simfs')
        return self.get_partition_size_sectors(partition_name) * 512

    def get_partition_offset_sectors(self, partition_name):
        if partition_name == 'simfs':
            return 0
        sysdir = self.get_sys_dir_for_partition(partition_name)
        return self._read_int(sysdir + '/start')

    def get_partition_offset_bytes(self, partition_name):
        return self.get_partition_offset_sectors(partition_name) * 512

    def list_partition_holders(self, partition_name):
        if partition_name == 'simfs':
            return []
        sysdir = self.get_sys_dir_for_partition(partition_name)
        return sorted(os.listdir(sysdir + '/holders'))

    def partition_raid_devices(self, partition_name):
        holders = self.list_partition_holders(partition_name)
        raid_devices = [d for d in holders if d.startswith('md')]
        return raid_devices

    def partition_dm_devices(self, partition_name):
        holders = self.list_partition_holders(partition_name)
        return [self._dm_names.get(d, d)
                for d in holders if d.startswith('dm-')]

    def get_partition_fsinfo(self, partition_name):
        raid_devices = self.partition_raid_devices(partition_name)
        dm_devices = self.partition_dm_devices(partition_name)
        for dev in [partition_name] + raid_devices + dm_devices:
            fsinfo = self._filesystems_by_device.get(dev)
            if fsinfo is not None:
                return fsinfo
        return None

    def get_partition_lvm_pv(self, partition_name):
        raid_devices = self.partition_raid_devices(partition_name)
        dm_devices = self.partition_dm_devices(partition_name)
        for dev in [partition_name] + raid_devices + dm_devices:
            pv = self._lvm_pvs.get(dev)
            if pv:
                return pv
        return None

    def get_partition_kvm_vm(self, partition_name):
        raid_devices = self.partition_raid_devices(partition_name)
        dm_devices = self.partition_dm_devices(partition_name)
        for dev in [partition_name] + raid_devices + dm_devices:
            vm = self._kvm_vms.get(dev)
            if vm:
                return vm
        return None

    def get_partition_usage(self, partition_name):
        users = []
        raid_devices = self.partition_raid_devices(partition_name)
        for md in raid_devices:
            users.append(md + ':')
        pv = self.get_partition_lvm_pv(partition_name)
        if pv:
            users.append('LVM: ' + pv.vgname)
        vm = self.get_partition_kvm_vm(partition_name)
        if vm:
            users.append('KVM: ' + vm.name)
        if partition_name in self._swap_devices:
            users.append('swap')
        fsinfo = self.get_partition_fsinfo(partition_name)
        if fsinfo is not None:
            users.append(fsinfo.fstype)
            users.append(fsinfo.mountpoint)
        return ' '.join(users)

    def is_partition_used(self, partition_name):
        pv = self.get_partition_lvm_pv(partition_name)
        vm = self.get_partition_kvm_vm(partition_name)
        swap = partition_name in self._swap_devices
        fsinfo = self.get_partition_fsinfo(partition_name)
        return bool(pv or vm or swap or fsinfo)

    def get_disks_of_lv(self, lv):
        disks = set()
        for device in lv.located_on:
            if device.startswith('/dev/'):
                partition_name = device[len('/dev/'):]
                disk_name = partition_name.rstrip('0123456789')
                disks.add(disk_name)
                continue
            nested = self._lvm_lvs.get((lv.vgname, '[{}]'.format(device)))
            if nested:
                disks.update(self.get_disks_of_lv(nested))
                continue
            disks.add(device)  # nocover: shrug, shouldn't happen probably
        return disks


def fmt_size_si(bytes):
    size, units = bytes, 'B'
    for prefix in 'KiB', 'MiB', 'GiB', 'TiB', 'PiB':
        if size >= 1024:
            size, units = size / 1024., prefix
    return '%.1f %s' % (size, units)


def fmt_size_decimal(bytes):
    size, units = bytes, 'B'
    for prefix in 'KB', 'MB', 'GB', 'TB', 'PB':
        if size >= 1000:
            size, units = size / 1000., prefix
    return '%.1f %s' % (size, units)


def fmt_free_space(fsinfo, pvinfo, partition_size_bytes,
                   fmt_size, show_used_instead_of_free):
    free_bytes = (
        fsinfo.avail_kb * 1024 if fsinfo else
        pvinfo.free_kb * 1024 if pvinfo else
        None
    )
    if free_bytes is None:
        return ''
    if show_used_instead_of_free:
        used_bytes = partition_size_bytes - free_bytes
        return fmt_size(used_bytes) + ' used'
    else:
        return fmt_size(free_bytes) + ' free'


class Reporter:

    def __init__(self, verbose=1, fmt_size=fmt_size_decimal, print=print,
                 name_width=8, usage_width=30, show_used_instead_of_free=False):
        self.verbose = verbose
        self.fmt_size = fmt_size
        self.print = print
        self.name_width = name_width
        self.usage_width = usage_width
        self.show_used_instead_of_free = show_used_instead_of_free

    def start_report(self):
        pass

    def end_report(self):
        pass

    def start_disk(self, disk, model, disk_size_bytes, fwrev, is_ssd):
        pass

    def end_disk(self, unallocated, free_space_at_end):
        pass

    def partition(self, name, partition_size_bytes, usage, fsinfo, pvinfo, is_used):
        pass

    def start_vg(self, vgroup):
        pass

    def end_vg(self, vgroup):
        pass

    def lv(self, lv, usage, fsinfo, is_ssd):
        pass


class TextReporter(Reporter):

    def start_disk(self, disk, model, disk_size_bytes, fwrev, is_ssd):
        template = "{disk}: {model} ({size})"
        if self.verbose >= 2:
            template += ', firmware revision {fwrev}'
        if is_ssd and 'SSD' not in model:
            template += ' [SSD]'
        self.print(template.format(
            disk=disk,
            model=model,
            size=self.fmt_size(disk_size_bytes),
            fwrev=fwrev,
        ))

    def end_disk(self, unallocated, free_space_at_end):
        if free_space_at_end and (self.verbose >= 2 or free_space_at_end > 100*1000**2): # megs
            self.print("  {spacing:{nw}} {size:>10} (unused)".format(
                spacing='', nw=self.name_width,
                size=self.fmt_size(free_space_at_end),
            ))
            unallocated -= free_space_at_end
        if unallocated and self.verbose >= 2:
            self.print("  {spacing:{nw}} {size:>10} (metadata/internal fragmentation)".format(
                spacing='', nw=self.name_width,
                size=self.fmt_size(unallocated),
            ))

    def partition(self, name, partition_size_bytes, usage, fsinfo, pvinfo, is_used,
                  is_ssd=False):
        if is_ssd and self.verbose >= 2:
            usage += ' [SSD]'
        self.print("  {name:{nw}} {size:>10}  {usage:{uw}}  {free_space:>15}".format(
            name=name + ':', nw=self.name_width,
            usage=usage, uw=self.usage_width,
            size=self.fmt_size(partition_size_bytes),
            free_space=fmt_free_space(
                fsinfo=fsinfo, pvinfo=pvinfo,
                partition_size_bytes=partition_size_bytes,
                fmt_size=self.fmt_size,
                show_used_instead_of_free=self.show_used_instead_of_free,
            ),
        ).rstrip())

    def start_vg(self, vgroup):
        template = "{vgroup}: LVM ({size})"
        self.print(template.format(
            vgroup=vgroup.name,
            size=self.fmt_size(vgroup.size_kb * 1024),
        ))

    def end_vg(self, vgroup):
        if vgroup.free_kb >= 1024 or self.verbose >= 2:
            self.print("  {name:{nw}} {size:>10}".format(
                name='free:', nw=self.name_width,
                size=self.fmt_size(vgroup.free_kb * 1024),
            ))

    def lv(self, lv, usage, fsinfo, is_ssd):
        self.partition(lv.name, lv.size_bytes, usage, fsinfo, pvinfo=None,
                       is_used=lv.is_open, is_ssd=is_ssd)


class HtmlReporter(Reporter):

    def start_report(self):
        self.print('<table class="disk-inventory table table-hover">')

    def end_report(self):
        self.print('</table>')

    def _heading_row(self, text, badges=()):
        self.print('<tr>')
        self.print('  <th colspan="4">')
        self.print('    {text}'.format(text=escape(text)))
        self._badges(badges)
        self.print('  </th>')
        self.print('</tr>')

    def _row(self, name, size, usage, free_space, tr_class=None, badges=()):
        self._elem('tr', tr_class, indent=0)
        self._cell(name, badges=badges)
        self._cell(size, css_class='text-right')
        self._cell(usage)
        self._cell(free_space, css_class='text-right')
        self.print('</tr>')

    def _cell(self, text, css_class=None, badges=()):
        self._elem('td', css_class)
        if text:
            self.print('    {}'.format(escape(text)))
        self._badges(badges)
        self.print('  </td>')

    def _elem(self, name, css_class=None, indent=1):
        template = ('<{name} class="{css_class}">' if css_class else '<{name}>')
        self.print('  ' * indent + template.format(name=name, css_class=css_class))

    def _badges(self, badges):
        for badge in badges:
            self.print(
                '    <span class="label label-info">{badge}</span>'.format(
                    badge=escape(badge)))

    def start_disk(self, disk, model, disk_size_bytes, fwrev, is_ssd):
        self._heading_row(
            '{disk}: {model} ({size}), firmware revision {fwrev}'.format(
                disk=disk,
                model=model,
                size=self.fmt_size(disk_size_bytes),
                fwrev=fwrev,
            ), badges=['SSD'] if is_ssd else [])

    def end_disk(self, unallocated, free_space_at_end):
        if free_space_at_end and (self.verbose >= 2 or free_space_at_end > 100*1000**2): # megs
            self._row('', self.fmt_size(free_space_at_end), '(unused)', '',
                      tr_class='text-muted')
            unallocated -= free_space_at_end
        if unallocated and self.verbose >= 2:
            self._row('', self.fmt_size(unallocated), '(metadata/internal fragmentation)', '',
                      tr_class='text-muted')

    def partition(self, name, partition_size_bytes, usage, fsinfo, pvinfo, is_used, is_ssd=False):
        if not is_used:
            if not usage:
                usage = '(unused)'
            elif usage.startswith('md'):
                usage += ' (unused)'
        self._row(
            name,
            self.fmt_size(partition_size_bytes),
            usage,
            fmt_free_space(
                fsinfo=fsinfo, pvinfo=pvinfo,
                partition_size_bytes=partition_size_bytes,
                fmt_size=self.fmt_size,
                show_used_instead_of_free=self.show_used_instead_of_free,
            ),
            tr_class='' if is_used else 'text-muted',
            badges=['SSD'] if is_ssd else [],
        )

    def start_vg(self, vgroup):
        self._heading_row(
            '{vgroup}: LVM ({size})'.format(
                vgroup=vgroup.name,
                size=self.fmt_size(vgroup.size_kb * 1024),
            ))

    def end_vg(self, vgroup):
        if vgroup.free_kb >= 1024 or self.verbose >= 2:
            self._row('free', self.fmt_size(vgroup.free_kb * 1024), '', '',
                      tr_class='text-muted')

    def lv(self, lv, usage, fsinfo, is_ssd):
        self.partition(lv.name, lv.size_bytes, usage, fsinfo, pvinfo=None,
                       is_used=lv.is_open, is_ssd=is_ssd)


def report(info=None, verbose=1, name_width=8, usage_width=30,
           fmt_size=fmt_size_decimal, print=print, warn=None,
           show_used_instead_of_free=False, reporter_class=TextReporter):
    if info is None:
        info = LinuxDiskInfo()
    if warn is not None:
        info.warn = warn
    for disk in info.list_physical_disks():
        for partition in info.list_partitions(disk):
            name_width = max(name_width, len(partition) + 1)
            usage_width = max(usage_width, len(info.get_partition_usage(partition)))
    for vgroup in info.list_lvm_volume_groups():
        for lv in info.list_lvm_logical_volumes():
            name_width = max(name_width, len(lv.name) + 1)
            usage_width = max(usage_width, len(info.get_partition_usage(lv.device)))
    reporter = reporter_class(
        verbose=verbose, fmt_size=fmt_size, print=print,
        name_width=name_width, usage_width=usage_width,
        show_used_instead_of_free=show_used_instead_of_free)
    reporter.start_report()
    for disk in info.list_physical_disks():
        disk_size_bytes = info.get_disk_size_bytes(disk)
        model = info.get_disk_model(disk)
        fwrev = info.get_disk_firmware_rev(disk)
        is_ssd = info.is_disk_an_ssd(disk)
        reporter.start_disk(disk, model, disk_size_bytes, fwrev, is_ssd)
        unallocated = disk_size_bytes
        partition = None
        last_partition_end = 0
        for partition in info.list_partitions(disk):
            partition_size_bytes = info.get_partition_size_bytes(partition)
            if partition_size_bytes <= 1024*1024 and verbose < 2:
                # all extended partitions I've seen show up as being 2 sectors
                # big. maybe they would become bigger if I had more logical
                # partitions?
                continue
            usage = info.get_partition_usage(partition)
            fsinfo = info.get_partition_fsinfo(partition)
            pvinfo = info.get_partition_lvm_pv(partition)
            is_used = info.is_partition_used(partition)
            reporter.partition(partition, partition_size_bytes, usage=usage, fsinfo=fsinfo, pvinfo=pvinfo, is_used=is_used)
            unallocated -= partition_size_bytes
            partition_start = info.get_partition_offset_bytes(partition)
            partition_end = partition_start + partition_size_bytes
            last_partition_end = max(last_partition_end, partition_end)
        free_space_at_end = disk_size_bytes - last_partition_end
        reporter.end_disk(unallocated, free_space_at_end)
    for vgroup in info.list_lvm_volume_groups():
        reporter.start_vg(vgroup)
        for lv in info.list_lvm_logical_volumes():
            if lv.vgname != vgroup.name:
                continue
            usage = info.get_partition_usage(lv.device)
            fsinfo = info.get_partition_fsinfo(lv.device)
            is_located_on_ssd = all(
                info.is_disk_an_ssd(disk) for disk in info.get_disks_of_lv(lv))
            reporter.lv(lv, usage, fsinfo, is_ssd=is_located_on_ssd)
        reporter.end_vg(vgroup)
    reporter.end_report()


def report_text(**kw):
    text = []
    report(print=text.append, warn=text.append, **kw)
    return '\n'.join(text)


def report_html(**kw):
    from markupsafe import Markup
    text = []
    warnings = []
    report(print=text.append, warn=warnings.append,
           reporter_class=HtmlReporter, **kw)
    return Markup('\n'.join(text) + '\n'.join(
        '<p class="warning">{}</p>'.format(escape(warning))
        for warning in warnings
    ))


def main():
    parser = optparse.OptionParser(usage='%prog [options]', version=__version__)
    parser.add_option('-v', '--verbose', action='count', dest='verbose',
                      default=1, help='increase verbosity (can be repeated)')
    parser.add_option('--decimal', help='use decimal units (1 KB = 1000 B)',
                      action='store_const', dest='fmt_size',
                      const=fmt_size_decimal)
    parser.add_option('--si', help='use SI units (1 KiB = 1024 B)',
                      action='store_const', dest='fmt_size',
                      const=fmt_size_si)
    parser.add_option('--used', help='show used space instead of free space',
                      action='store_true')
    parser.add_option('--html', help='produce HTML output',
                      action='store_true')
    parser.set_defaults(fmt_size=fmt_size_decimal)
    opts, args = parser.parse_args()
    report(
        verbose=opts.verbose, fmt_size=opts.fmt_size,
        show_used_instead_of_free=opts.used,
        reporter_class=HtmlReporter if opts.html else TextReporter,
    )


if __name__ == '__main__':
    main()
