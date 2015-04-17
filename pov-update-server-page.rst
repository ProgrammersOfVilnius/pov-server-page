======================
pov-update-server-page
======================

-------------------------------------------------
set up an administrative web page for your server
-------------------------------------------------

:Author: Marius Gedminas <marius@gedmin.as>
:Date: 2015-04-17
:Version: 0.21.0
:Manual section: 8


SYNOPSIS
========

**pov-update-server-page** [options] [*var*\ =\ *value* ...]

**pov-update-server-page** **-h** | **--help**


DESCRIPTION
===========

This script sets up web page for your server, listing the following
information:

  - contents of /root/Changelog
  - graphs for collectd
  - open TCP ports
  - SSH host key fingerprints
  - disk usage treemaps (if configured)
  - last entries in /root/Changelog (if readable by www-data)

There's an accompanying cron script that updates the open ports list
and disk usage numbers once a day.



OPTIONS
=======

-h, --help          Print a help message and exit.
-v, --verbose       Verbose output: show what files are being created.
--quick             Skip expensive build steps (disk usage pages).
-c FILENAME, --config-file=FILENAME
                    Use the specified config file instead of
                    ``/etc/pov/server-page.conf``.
--no-checks         Skip checks for suggestions of things that need to be done
                    manually (such as enabling Apache modules, sites, or
                    creating missing htpasswd files).
--destdir=PATH      Prepend *PATH* in front of all files to be created.
                    Useful for testing purposes.

You can override any config file options by specifying them on the command
line.


HOW IT WORKS
============

More specifically, it creates a number of files under ``/var/www/``\ *HOSTNAME*
and an Apache site in ``/etc/apache2/sites-available/``\ *HOSTNAME*\ ``.conf``.  It also
creates a directory for Apache logs under ``/var/log/apache2/``\ *HOSTNAME*.
Then it tells you what commands you need to run to enable that site (usually
something like ``a2enmod ssl rewrite; a2ensite`` *HOSTNAME*\ ``.conf; htpasswd -c``
*PASSWDFILE*).

It is private: the site configuration will require SSL and password
authentication.  You're expected to provide the SSL certificate and the Apache
password file yourself.

It is safe: it won't touch anything on disk if you do not explicitly enable
it in the config file (set ``enabled = 1``), so the daily cron script that's
installed by default won't start playing havoc with your fine-tuned Apache.

It also won't overwrite any files unless it finds a generated file marker it
puts into any files it generates.  So any changes due to you editing the
config file will be reflected, but any pre-existing websites won't be
destroyed.

Any changes you made to generated files will be overwritten when the daily
cron script next runs.  To avoid that, use the ``skip`` or ``redirect``
options.


CONFIGURATION FILE
==================

``/etc/pov/server-page.conf`` is an INI file that should start with ::

    [pov-server-page]

Lines beginning with a ``#`` are treated as comments.  Configuration values
are separated from names with a ``=``.  Option values can be wrapped, as long
as all non-blank continuation lines start with whitespace.

The following options are defined:

**enabled** (default value: 0)

    If set to 0, or not set at all, running ``pov-update-server-page`` won't
    do anything at all, quietly.  In verbose mode it will print a message
    explaining why it is disabled.

**auth_user_file** (default value: ``/etc/pov/fridge.passwd``)

    Location of the Apache password file.  Used in the generated Apache
    site configuration.  You'll need to create this file yourself before you
    can access the site.

**hostname** (default: determined by running ``hostname -f``)

    Desired virtual host name.  Used in the ``ServerName`` Apache directive,
    as well as in filesystem locations under ``/var/www`` and
    ``/var/log/apache2``.

    Note: if you change the hostname, **pov-update-server-page** will not clean
    up old files under the old location.

**server_aliases** (default: empty)

    Additional server host name aliases.  Used in the ``ServerAlias``
    Apache directive.

    Note: accessing the server page using any of the aliases will redirect
    to the canonical hostname.

**canonical_redirect** (default: true)

    Generate rewrite rules to redirect to the canonical hostname.

    Turn this off if you need to test the apache configuration in
    a machine you can't access directly and need to use SSH port
    forwarding.

**include** (default: empty)

    Add an ``Include`` *FILENAME* directive in the generated Apache
    configuration.

    You need to use this (or **apache_extra_conf**) to specify the SSL
    certificate.

    Example::

        include = /etc/apache2/my-ssl-cert.conf

**apache_extra_conf** (default: empty)

    Insert the value into the middle of the generated Apache configuration.

    Note: all leading whitespace will be normalized.

    You need to use this (or **include**) to specify the SSL certificate.

    Example::

        apache_extra_conf =
          SSLCertificateFile /etc/ssl/certs/ssl-cert-snakeoil.pem
          SSLCertificateKeyFile /etc/ssl/private/ssl-cert-snakeoil.key

**extra_links** (default: empty)

    A list of additional links to include on the front page.  Separate the
    URL from the link title with a ``=``.  If you need to use ``=`` inside
    the URL, you can do so, as long as it doesn't have spaces around it,
    if you have spaces around the real separator.  Separate multiple links
    with newlines.

    Useful to add links to other bits of the website you may have created
    manually in ``/var/www/``\ *HOSTNAME*, or configured with
    **apache_extra_conf** or **include**.

    Example::

        extra_links =
            supervisor = Supervisor
            /sentry = Sentry
            awstats.pl?config=website1 = Web stats for website1
            http://www.google.com/ = Google search

**disk_usage** (default: empty)

    This is either a list of directory names (space or newline separated), or
    the word ``all`` meaning "all mounted partitions backed by disk devices".
    All the directories listed here will have their disk usage measured with
    **du**\ (1) every day, with the gzipped snapshots archived in
    ``/var/www/``\ *HOSTNAME*\ ``/du/``, with the last snapshot displayed
    visually as a treemap.

    Note: running **du**\ (1) can take a long time.

    Note: if you remove a directory from this list, it will be removed
    from the links, but old snapshots will not be cleaned up.

    Example::

        disk_usage = all

**disk_usage_delete_old** (default: true)

    Should old disk usage snapshots be cleaned up?

**disk_usage_keep_daily** (default: 60)

    When deleting old disk usage snapshot keep the last N.

**disk_usage_keep_monthly** (default: 12)

    When deleting old disk usage snapshot keep at least one for each of
    the last N months.

**disk_usage_keep_yearly** (default: 5)

    When deleting old disk usage snapshot keep at least one for each of
    the last N years.

**skip** (default: empty)

    A space or newline separated list of files you do not want to generate.

    Use this when you want to supply a manually hand-crafted version of a file
    instead of the one **pov-update-server-page** generates.

    All filenames should be absolute.

    Example::

        skip =
          /var/www/foo.example.com/index.html
          /var/www/foo.example.com/ssh/index.html
          /var/www/foo.example.com/du

**redirect** (default: empty)

    A newline-separate list of files you want to generate with alternative
    names/locations.

    Use this when you want to supply a manually hand-crafted version of a file
    instead of the one **pov-update-server-page** generates, but you also
    want the generated file to be available for comparison purposes.

    All filenames should be absolute.

    Example::

        redirect =
          /var/www/foo.example.com/index.html = /var/www/foo.example.com/admin.html


BUGS
====

If you specify ``disk_usage = / /root``, **pov-update-server-page** will try
to store both snapshots in the same ``/var/www/``\ *HOSTNAME*\ ``/root``
directory.

You cannot skip individual files or subdirectories under
``/var/www/``\ *HOSTNAME*\ ``/du/``.

Report bugs at https://github.com/ProgrammersOfVilnius/pov-server-page/issues/
