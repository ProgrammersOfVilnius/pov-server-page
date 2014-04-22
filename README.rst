PoV server page
===============

This script sets up web page for your server, listing the following
information:

  - graphs for collectd
  - open TCP ports
  - disk usage treemaps (if configured)
  - last entries in /root/Changelog (if readable by www-data)


Requirements
------------

- Ubuntu
- Apache + mod_wsgi
- Perl
- collectd


Usage
-----

::

    apt-get install pov-update-server-page
    vim /etc/pov/server-page.conf
      at the very least uncomment enable=1
      you'll also need to make sure some SSL certificate is available
    chmod +x /root  # make /root/Changelog readable by www-data
    pov-update-server-page -v
    a2enmod rewrite ssl wsgi
    a2ensite $(hostname -f).conf
    apache2ctl configtest && apache2ctl graceful

