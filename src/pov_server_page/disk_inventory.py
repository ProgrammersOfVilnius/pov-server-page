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

import collections
import optparse
import os
import sys


__version__ = '1.2.2'


FilesystemInfo = collections.namedtuple('FilesystemInfo',
                        'device mountpoint fstype size_kb used_kb avail_kb')

PVInfo = collections.namedtuple('PVInfo', 'device vgname')

VGInfo = collections.namedtuple('VGInfo', 'name size_kb used_kb free_kb')

LVInfo = collections.namedtuple('LVInfo', 'name vgname size_sectors device')

DMInfo = collections.namedtuple('LVInfo', 'name major minor')

DMName = collections.namedtuple('LVInfo', 'name number')


class LinuxDiskInfo(object):

    _swap_devices_cache = None
    _filesystems_cache = None
    _filesystems_by_device_cache = None
    _lvm_pvs_cache = None
    _dm_cache = None
    _dm_name_cache = None

    @property
    def _swap_devices(self):
        if self._swap_devices_cache is None:
            self._swap_devices_cache = self.list_swap_devices()
        return self._swap_devices_cache

    @property
    def _filesystems(self):
        if self._filesystems_cache is None:
            self._filesystems_cache = self.list_filesystems()
        return self._filesystems_cache

    @property
    def _filesystems_by_device(self):
        if self._filesystems_by_device_cache is None:
            self._filesystems_by_device_cache = dict(
                (r.device, r) for r in self._filesystems)
        return self._filesystems_by_device_cache

    @property
    def _lvm_pvs(self):
        if self._lvm_pvs_cache is None:
            self._lvm_pvs_cache = dict(
                (pv.device, pv) for pv in self.list_lvm_physical_volumes())
        return self._lvm_pvs_cache

    @property
    def _dms(self):
        if self._dm_cache is None:
            self._dm_cache = dict(
                (dm.name, dm) for dm in self.list_device_mapper())
        return self._dm_cache

    @property
    def _dm_names(self):
        if self._dm_name_cache is None:
            self._dm_name_cache = dict(
                (dm.number, dm.name) for dm in self.list_device_mapper_names())
        return self._dm_name_cache

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
            name = self._dm_names.get(name)
        return name

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

    def list_physical_disks(self):
        """Return physical disk names such as ['sda', 'sdb'].

        Limitations: only handles ATA/SATA/SCSI disks; no RAID or whatnot.
        """
        if not os.path.exists('/sys/block'):
            print >> sys.stderr, "disk-inventory: cannot discover block devices: /sys/block is missing"
            return []
        return sorted(name for name in os.listdir('/sys/block')
                      if name.startswith(('sd', 'xvd', 'cciss')))

    def list_device_mapper(self):
        """Return a list of DMInfo tuples."""
        res = []
        with os.popen('dmsetup -c --noheadings info') as f:
            for line in f:
                # name, major, minor, attr, open, segments,  events,  uuid.
                name, major, minor, _, _, _, _, _ = line.split(':')
                res.append(DMInfo(name, int(major), int(minor)))
        return res

    def list_device_mapper_names(self):
        """Return a list of DMName tuples."""
        # XXX: I could construct this from self._dms, using self.get_dm_for()
        res = []
        try:
            for name in os.listdir('/dev/mapper'):
                if not os.path.islink('/dev/mapper/' + name):
                    continue
                number = os.readlink('/dev/mapper/' + name).split('/')[-1]
                res.append(DMName('mapper/' + name, number))
        except IOError:
            pass
        return res

    def list_lvm_volume_groups(self):
        """Return volume groups names."""
        res = []
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
                except ValueError:
                    # Could be something like a
                    #    "/dev/sdc2" is a new physical volume of "231.95 GiB"
                    # which shows up when you pvcreate but don't vgextend.
                    pass
                else:
                    if device.startswith('/dev/'):
                        res.append(PVInfo(device[len('/dev/'):], vgname))
        return res

    def list_lvm_logical_volumes(self):
        res = []
        with os.popen('lvdisplay -c 2>/dev/null') as f:
            for line in f:
                # columns:
                # - logical volume name
                # - volume group name
                # - logical volume access
                # - logical volume status
                # - internal logical volume number
                # - open count of logical volume
                # - logical volume size in sectors
                # - current logical extents associated to logical volume
                # - allocated logical extents of logical volume
                # - allocation policy of logical volume
                # - read ahead sectors of logical volume
                # - major device number of logical volume
                # - minor device number of logical volume
                (name, vgname, _, _, _, _, size_sectors, cur_extents,
                 alloc_extents, _, _, _, _) = line.strip().split(':')
                lvname = name.rpartition('/')[-1] # /dev/{vgname}/{lvname}
                device = 'mapper/{vgname}-{lvname}'.format(
                    vgname=vgname.replace('-', '--'),
                    lvname=lvname.replace('-', '--'),
                )
                res.append(LVInfo(lvname, vgname, int(size_sectors), device))
        return res

    def get_disk_size_sectors(self, disk_name):
        return self._read_int('/sys/block/%s/size' % disk_name)

    def get_disk_size_bytes(self, disk_name):
        # Experiments show that the kernel always reports 512-byte sectors,
        # even when the disk uses 4KiB sectors.
        return self.get_disk_size_sectors(disk_name) * 512

    def get_disk_model(self, disk_name):
        if disk_name.startswith('xvd'):
            return 'Xen virtual disk'
        return self._read_string('/sys/block/%s/device/model' % disk_name)

    def get_disk_firmware_rev(self, disk_name):
        if disk_name.startswith('xvd'):
            return 'N/A'
        return self._read_string('/sys/block/%s/device/rev' % disk_name)

    def list_partitions(self, disk_name):
        """Return partition names such as ['sda1', ...].

        Includes primary, extended and logical partition names.
        """
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
        return self.get_partition_size_sectors(partition_name) * 512

    def get_partition_offset_sectors(self, partition_name):
        sysdir = self.get_sys_dir_for_partition(partition_name)
        return self._read_int(sysdir + '/start')

    def get_partition_offset_bytes(self, partition_name):
        return self.get_partition_offset_sectors(partition_name) * 512

    def list_partition_holders(self, partition_name):
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

    def get_partition_usage(self, partition_name):
        users = []
        raid_devices = self.partition_raid_devices(partition_name)
        for md in raid_devices:
            users.append(md + ':')
        pv = self.get_partition_lvm_pv(partition_name)
        if pv:
            users.append('LVM: ' + pv.vgname)
        if partition_name in self._swap_devices:
            users.append('swap')
        fsinfo = self.get_partition_fsinfo(partition_name)
        if fsinfo is not None:
            users.append(fsinfo.fstype)
            users.append(fsinfo.mountpoint)
        return ' '.join(users)


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



def main():
    parser = optparse.OptionParser(usage='%prog [options]', version=__version__)
    parser.add_option('-v', '--verbose', action='count', dest='verbose',
                      default=1)
    parser.add_option('--decimal', help='use decimal units (1 KB = 1000 B)',
                      action='store_const', dest='fmt_size',
                      const=fmt_size_decimal)
    parser.add_option('--si', help='use SI units (1 KiB = 1024 B)',
                      action='store_const', dest='fmt_size',
                      const=fmt_size_si)
    parser.set_defaults(fmt_size=fmt_size_decimal)
    opts, args = parser.parse_args()
    fmt_size = opts.fmt_size
    name_width = 8
    usage_width = 30
    info = LinuxDiskInfo()
    for disk in info.list_physical_disks():
        for partition in info.list_partitions(disk):
            name_width = max(name_width, len(partition) + 1)
            usage_width = max(usage_width, len(info.get_partition_usage(partition)))
    for vgroup in info.list_lvm_volume_groups():
        for lv in info.list_lvm_logical_volumes():
            name_width = max(name_width, len(lv.name) + 1)
            usage_width = max(usage_width, len(info.get_partition_usage(lv.device)))
    for disk in info.list_physical_disks():
        disk_size_bytes = info.get_disk_size_bytes(disk)
        template = "{disk}: {model} ({size})"
        if opts.verbose >= 2:
            template += ', firmware revision {fwrev}'
        print template.format(
            disk=disk,
            model=info.get_disk_model(disk),
            size=fmt_size(disk_size_bytes),
            fwrev=info.get_disk_firmware_rev(disk),
        )
        unallocated = disk_size_bytes
        partition = None
        last_partition_end = 0
        for partition in info.list_partitions(disk):
            partition_size_bytes = info.get_partition_size_bytes(partition)
            if partition_size_bytes <= 1024*1024 and opts.verbose < 2:
                # all extended partitions I've seen show up as being 2 sectors
                # big. maybe they would become bigger if I had more logical
                # partitions?
                continue
            usage = info.get_partition_usage(partition)
            fsinfo = info.get_partition_fsinfo(partition)
            print "  {name:{nw}} {size:>10}  {usage:{uw}}  {free_space:>15}".format(
                name=partition + ':', nw=name_width,
                usage=usage, uw=usage_width,
                size=fmt_size(partition_size_bytes),
                free_space=fmt_size(fsinfo.avail_kb * 1024) + ' free' if fsinfo
                           else '',
            ).rstrip()
            unallocated -= partition_size_bytes
            partition_start = info.get_partition_offset_bytes(partition)
            partition_end = partition_start + partition_size_bytes
            last_partition_end = max(last_partition_end, partition_end)
        free_space_at_end = disk_size_bytes - last_partition_end
        if free_space_at_end and (opts.verbose >= 2
                                  or free_space_at_end > 100*1000**2): # megs
            print "  {spacing:{nw}} {size:>10} (unused)".format(
                spacing='', nw=name_width,
                size=fmt_size(free_space_at_end),
            )
            unallocated -= free_space_at_end
        if unallocated and opts.verbose >= 2:
            print "  {spacing:{nw}} {size:>10} (metadata/internal fragmentation)".format(
                spacing='', nw=name_width,
                size=fmt_size(unallocated),
            )
    for vgroup in info.list_lvm_volume_groups():
        template = "{vgroup}: LVM ({size})"
        print template.format(
            vgroup=vgroup.name,
            size=fmt_size(vgroup.size_kb * 1024),
        )
        for lv in info.list_lvm_logical_volumes():
            if lv.vgname != vgroup.name:
                continue
            usage = info.get_partition_usage(lv.device)
            fsinfo = info.get_partition_fsinfo(lv.device)
            print "  {name:{nw}} {size:>10}  {usage:{uw}}  {free_space:>15}".format(
                name=lv.name+':', nw=name_width,
                usage=usage, uw=usage_width,
                size=fmt_size(lv.size_sectors * 512),
                free_space=fmt_size(fsinfo.avail_kb * 1024) + ' free' if fsinfo
                           else '',
            ).rstrip()
        if vgroup.free_kb >= 1024 or opts.verbose >= 2:
            print "  {name:{nw}} {size:>10}".format(
                name='free:', nw=name_width,
                size=fmt_size(vgroup.free_kb * 1024),
            )


if __name__ == '__main__':
    main()
