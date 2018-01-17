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
    a2enmod rewrite ssl wsgi cgid
    a2ensite $(hostname -f).conf
    htpasswd -c ...
    service apache2 reload


Usage with Python 3
-------------------

Exactly like the above, only replace the `apt-get install` line with ::

    apt-get install pov-update-server-page libapache2-mod-wsgi-py3

This is needed when your Apache needs to use libapache2-mod-wsgi-py3, which
conflicts with libapache2-mod-wsgi.
