all:

install:
	install update_server_page.py $(DESTDIR)/usr/sbin/pov-update-server-page
	install collection.cgi $(DESTDIR)/usr/lib/pov-server-page/collection.cgi
	install apache.conf.in $(DESTDIR)/usr/share/pov-server-page/
	install index.html.in $(DESTDIR)/usr/share/pov-server-page/
