===============
machine-summary
===============

-----------------------------------------
print some basic facts about this machine
-----------------------------------------

:Author: Marius Gedminas <marius@gedmin.as>
:Date: 2016-09-21
:Version: 0.7.1
:Manual section: 8


SYNOPSIS
========

**machine-summary** [**-n** | **--no-title**]

**machine-summary** **-h** | **--help**


DESCRIPTION
===========

Produce a short summary of the basic facts about this machine, in
ReStructuredText format:

- Hostname
- Number and models of CPUs
- Amount of RAM
- Sizes and models of hard disks
- Names and MAC addresses of network cards
- IP addresses
- Name and version of the operating system


OPTIONS
=======

-h, --help      show this help message and exit
--version       print version number and exit
-n, --no-title  skip the title heading


CGI MODE
========

You can use machine-summary as a CGI script, if you set an environment
variable **RUN_AS_CGI** to a non-blank value.  Example Apache
configuration::

    ScriptAlias /machine-summary.rst /usr/sbin/machine-summary
    <Location /machine-summary.rst>
      SetEnv RUN_AS_CGI "1"
    </Location>


BUGS
====

Assumes UTF-8.  (Is this really a bug in the 21st century?)

It has seen relatively little testing and so may get confused by strange
device names, unfamiliar OSes, etc.

It tries to round up the RAM size to produce pretty numbers, and might get
it wrong.
