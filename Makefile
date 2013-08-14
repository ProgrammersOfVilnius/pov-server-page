.PHONY: all
all:

.PHONY: install
install:
	install -m 644 server-page.conf $(DESTDIR)/etc/pov/server-page.conf
	install update_server_page.py $(DESTDIR)/usr/sbin/pov-update-server-page
	install collection.cgi $(DESTDIR)/usr/lib/pov-server-page/collection.cgi
	install -m 644 apache.conf.in $(DESTDIR)/usr/share/pov-server-page/
	install -m 644 index.html.in $(DESTDIR)/usr/share/pov-server-page/

.PHONY: source-package
source-package:
	debuild -S -i -k$(GPGKEY)

.PHONY: upload-to-ppa
upload-to-ppa: source-package
	dput ppa:pov/ppa ../$(source)_$(version)_source.changes
	git tag $(version)

.PHONY: binary-package
binary-package:
	debuild -i -k$(GPGKEY)
