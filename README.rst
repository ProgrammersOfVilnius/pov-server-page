PoV server page
===============

.. image:: https://github.com/ProgrammersOfVilnius/pov-server-page/actions/workflows/build.yml/badge.svg?branch=master
    :target: https://github.com/ProgrammersOfVilnius/pov-server-page/actions

This script sets up a web page for your server, listing the following
information:

- basic system information
- contents of /root/Changelog
- graphs for collectd
- open TCP and UDP ports
- SSH host key fingerprints
- disk usage treemaps (if configured)

This information is refreshed automatically from a couple of cron scripts
(daily and hourly).  It's disabled by the default in /etc/pov/server-page.conf.

This package also ships a number of helper scripts you can use from the command
line, if you prefer that to browsing web pages:

- machine-summary_: prints a short description of this machine (as
  ReStructuredText)
- disk-inventory_: prints an overview of your disks and partitions
- du-diff_: compares two disk usage snapshots (as produced by `du`)


Requirements
------------

- Ubuntu
- Apache + mod_wsgi
- Perl
- Python
- collectd
- an Apache password file

And if you want this publically accessible (as opposed to localhost-only):

- an SSL certificate (you can get one from letsencrypt.org)


Usage
-----

::

    add-apt-repository ppa:pov
    apt-get update
    apt-get install pov-update-server-page
    vim /etc/pov/server-page.conf
      at the very least uncomment 'enable = 1'
      you'll also need to make sure some SSL certificate is available
      OR set 'loopback_only = 1'
      I also recommend 'disk_usage = all'
    chmod +x /root  # make /root/Changelog readable by www-data
    pov-update-server-page -v
      # this prints what it does and then tells you what you should do,
      # which is basically
    a2enmod rewrite ssl wsgi cgid headers
    a2ensite $(hostname -f).conf
    htpasswd -c ...
    service apache2 reload


machine-summary
---------------

Pokes around in `/proc` and `/sys` and emits a bit of ReStructuredText to
summarize this machine::

    $ machine-summary
    platonas
    ========

    :CPU: 4 × Intel(R) Core(TM) i5-2520M CPU @ 2.50GHz
    :RAM: 8 GiB
    :Disks: sda - 160.0 GB (model INTEL SSDSA2M160)
    :Network: eth0 - MAC: xx:xx:xx:xx:xx:xx,
            wlan0 - MAC: xx:xx:xx:xx:xx:xx
    :IP: 192.168.99.196/24
    :OS: Ubuntu 14.10 (x86_64)


disk-inventory
--------------

Pokes around in `/proc` and `/sys` and emits a summary of the storage
situation on this machine::

    $ disk-inventory
    sda: ST1000NM0011 (1.0 TB)
      sda1:        2.0 GB  swap
      sda2:        1.0 GB  md0 ext3 /                        271.0 MB free
      sda5:       15.0 GB  md1 ext4 /var                     977.8 MB free
      sda6:        5.0 GB  md2 ext4 /usr                     706.8 MB free
      sda7:      230.0 GB  md3 ext4 /home                     41.0 GB free
      sda8:      247.1 GB  md4 ext4 /stuff                    21.5 GB free
      sda9:      500.1 GB  LVM: fridge dm-0 dm-1 dm-2
    sdb: ST3500320AS (500.1 GB)
      sdb1:        2.0 GB  swap
      sdb2:        1.0 GB  md0 ext3 /                        271.0 MB free
      sdb5:       15.0 GB  md1 ext4 /var                     977.8 MB free
      sdb6:        5.0 GB  md2 ext4 /usr                     706.8 MB free
      sdb7:      230.0 GB  md3 ext4 /home                     41.0 GB free
      sdb8:      247.1 GB  md4 ext4 /stuff                    21.5 GB free
    fridge: LVM (500.1 GB)
      tmp:        21.5 GB  ext4 /tmp                          19.8 GB free
      jenkins:    21.5 GB  ext4 /var/lib/jenkins              10.9 GB free
      buildbot:   42.9 GB  ext4 /var/lib/buildbot             13.7 GB free
      free:      414.2 GB

Supports RAID (md-raid) and LVM.  May need root access to provide full
information.


du-diff
-------

Compares two disk usage snapshots produced by `du`.  Can transparently read
gzipped files.  Sorts the output by difference.  Example::

    $ du /var | gzip > du-$(date +%Y-%m-%d).gz
    # wait a day or a week
    $ du /var | gzip > du-$(date +%Y-%m-%d).gz
    $ du-diff du-2013-08-21.gz du-2013-08-22.gz
    -396536 /var/lib/hudson.obsolete/cache
    -396536 /var/lib/hudson.obsolete
    -395704 /var/lib
    -345128 /var
    -290680 /var/lib/hudson.obsolete/cache/buildout-eggs
    ...
    -8      /var/lib/hudson.obsolete/cache/buildout-eggs/PasteScript-1.7.3-py2.5.egg/EGG-INFO/scripts
    +4      /var/lib/nagios3/spool/checkresults
    +4      /var/lib/nagios3/spool
    ...
    +740    /var/lib/svn
    +1688   /var/mail
    +4224   /var/log/ConsoleKit
    +4876   /var/log/apache2
    +19840  /var/log
    +28832  /var/www

