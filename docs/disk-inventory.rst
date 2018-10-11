==============
disk-inventory
==============

----------------------------------------------
print an overview of your disks and partitions
----------------------------------------------

:Author: Marius Gedminas <marius@gedmin.as>
:Date: 2018-10-11
:Version: 1.6.1
:Manual section: 8


SYNOPSIS
========

**disk-inventory** [**-v** | **--verbose**] [**--decimal** | **--si**] [**--used**] [**--html**]

**disk-inventory** **-h** | **--help**

**disk-inventory** **--version**


DESCRIPTION
===========

Produce a disk inventory for a system:

- how many hard disks and how large
- how are they partitioned
- how are the RAID and LVM devices defined
- where are they mounted
- how much space is used and how much is free

Needs root access to figure out details about LVM.


OPTIONS
=======

--version      show program's version number and exit
-h, --help     show this help message and exit
-v, --verbose
--decimal      use decimal units (1 KB = 1000 B)
--si           use SI units (1 KiB = 1024 B)
--used         show used space instead of free space
--html         produce HTML output


BUGS
====

It has seen relatively little testing and so may get confused by strange
device names, some kinds of hardware RAID, encrypted devices, etc.
