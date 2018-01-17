Working on pov-server-page
==========================

This is a collection of scripts:

- changelog2html.py -- a WSGI script that renders the system changelog
- collection.cgi -- a CGI script that renders collectd graphs
  (forked from collectd upstream)
- dudiff2html.py -- a WSGI script that renders disk usage difference
  pages
- update_ports_html.py -- a standalone script that generates
  the list of open network ports (not CGI/WSGI because it runs as root
  to get all the desired information)
- cron_daily.sh -- a cron script that runs pov-update-server-page every day
- cron_hourly.sh -- a cron script that runs pov-update-server-page -q every hour
- update_server_page.py -- the main pov-update-server-page script
  that generates the Apache configuration, static HTML files in /var/www,
  and computes daily disk usage.


dudiff2html
===========

Testing manually
----------------

Suppose you're looking at a du-diff page and want to fix something in it.
Assume https://example.com/du/diff/backup/2016-02-16..2016-03-14 is the URL.
Then you can ::

    mkdir -p /tmp/du/backup
    cd /tmp/du/backup
    wget https://example.com/du/backup/du-2016-02-16.gz
    wget https://example.com/du/backup/du-2016-03-14.gz
    cd ~/src/pov-server-page/
    ./dudiff2html.py /tmp/du
    # now open http://localhost:8080/backup/2016-02-16..2016-03-14

Replace "example.com" with the real server name, and "backup" with the
real mountpoint label.  And replace the dates, of course.  You'll probably
also have to download the .gz files with your browser instead of wget
because of HTTP auth.

When you run dudiff2html.py manually this way, it reloads its own source
code on every request, so you can edit the code and reload the browser
page for a quick development loop.
