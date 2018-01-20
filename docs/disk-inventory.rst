==============
disk-inventory
==============

----------------------------------------------
print an overview of your disks and partitions
----------------------------------------------

:Author: Marius Gedminas <marius@gedmin.as>
:Date: 2017-03-13
:Version: 1.2.2
:Manual section: 8


SYNOPSIS
========

**disk-inventory**


DESCRIPTION
===========

Produce a disk inventory for a system:

- how many hard disks and how large
- how are they partitioned
- how are the RAID and LVM devices defined
- where are they mounted
- how much space is used and how much is free

Needs root access to figure out details about LVM.


BUGS
====

It has seen relatively little testing and so may get confused by strange
device names, some kinds of hardware RAID, encrypted devices, etc.
