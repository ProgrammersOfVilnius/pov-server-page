PoV server page
===============

This script sets up web page for your server, listing the following
information:

  - graphs for collectd
  - open TCP ports


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

Crib for enabling a self-signed SSL certificate in Apache (don't use this in
production please)::

    SSLCertificateFile /etc/ssl/certs/ssl-cert-snakeoil.pem
    SSLCertificateKeyFile /etc/ssl/private/ssl-cert-snakeoil.key


Future plans
------------

Add a treemap showing disk usage of specified partitions.
