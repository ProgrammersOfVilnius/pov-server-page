PoV server page
===============

This script sets up web page for your server, listing the following
information:

  - graphs for collectd


Requirements
------------

- Ubuntu
- Apache
- Perl
- collectd


Usage
-----

::

    apt-get install pov-update-server-page
    vim /etc/pov/server-page.conf
      at the very least uncomment enable=1
    pov-update-server-page
    a2enmod rewrite ssl
    a2ensite $(hostname -f)
    apache2ctl configtest && apache2ctl graceful


Future plans
------------

Add a list of open TCP ports with service names etc.

Add a treemap showing disk usage of specified partitions.

Add a cron script to update these nightly.
