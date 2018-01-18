PoV server page
===============

This script sets up a web page for your server, listing the following
information:

- contents of /root/Changelog
- graphs for collectd
- open TCP and UDP ports
- SSH host key fingerprints
- disk usage treemaps (if configured)


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

