PoV server page
===============

This script sets up web page for your server, listing the following
information:

  - contents of /root/Changelog
  - graphs for collectd
  - open TCP ports
  - SSH host key fingerprints
  - disk usage treemaps (if configured)


Requirements
------------

- Ubuntu
- Apache + mod_wsgi
- Perl
- Python
- collectd


Usage
-----

::

    apt-get install pov-update-server-page
    vim /etc/pov/server-page.conf
      at the very least uncomment enable = 1
      you'll also need to make sure some SSL certificate is available
    chmod +x /root  # make /root/Changelog readable by www-data
    pov-update-server-page -v
    a2enmod rewrite ssl wsgi cgid
    a2ensite $(hostname -f).conf
    service apache2 reload

