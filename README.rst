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

    git clone https://github.com/mgedmin/pov-server-page
    cd pov-server-page
    make
    sudo make install
    sudo a2enmod rewrite
    sudo a2ensite $(hostname -f)
    sudo apache2ctl graceful


Future plans
------------

Make this a Debian package.
