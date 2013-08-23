source := $(shell dpkg-parsechangelog | awk '$$1 == "Source:" { print $$2 }')
version := $(shell dpkg-parsechangelog | awk '$$1 == "Version:" { print $$2 }')

.PHONY: all
all: pov-update-server-page.8

%.8: %.rst
	rst2man $< > $@

.PHONY: install
install:
	install -m 644 server-page.conf $(DESTDIR)/etc/pov/server-page.conf
	install update_server_page.py $(DESTDIR)/usr/sbin/pov-update-server-page
	install update_tcp_ports_html.py $(DESTDIR)/usr/lib/pov-server-page/update-ports
	install collection.cgi $(DESTDIR)/usr/lib/pov-server-page/collection.cgi
	install webtreemap-du/du2webtreemap.py $(DESTDIR)/usr/lib/pov-server-page/du2webtreemap
	install -m 644 templates/apache.conf.in $(DESTDIR)/usr/share/pov-server-page/
	install -m 644 templates/index.html.in $(DESTDIR)/usr/share/pov-server-page/
	install -m 644 templates/du.html.in $(DESTDIR)/usr/share/pov-server-page/
	install -m 644 templates/du-page.html.in $(DESTDIR)/usr/share/pov-server-page/
	install -m 644 webtreemap/webtreemap.css $(DESTDIR)/usr/share/pov-server-page/webtreemap/
	install -m 644 webtreemap/webtreemap.js $(DESTDIR)/usr/share/pov-server-page/webtreemap/
	install cron_daily.sh $(DESTDIR)/etc/cron.daily/pov-update-server-page

.PHONY: clean-build-tree
clean-build-tree:
	rm -rf pkgbuild/$(source)
	git archive --format=tar --prefix=pkgbuild/$(source)/ HEAD | tar -xf -
	(cd webtreemap && git archive --format=tar --prefix=pkgbuild/$(source)/webtreemap/ HEAD) | tar -xf -
	(cd webtreemap-du && git archive --format=tar --prefix=pkgbuild/$(source)/webtreemap-du/ HEAD) | tar -xf -

.PHONY: source-package
source-package: clean-build-tree
	cd pkgbuild/$(source) && debuild -S -i -k$(GPGKEY)

.PHONY: upload-to-ppa
upload-to-ppa: source-package
	dput ppa:pov/ppa pkgbuild/$(source)_$(version)_source.changes
	git tag $(version)

.PHONY: binary-package
binary-package: clean-build-tree
	cd pkgbuild/$(source) && debuild -i -k$(GPGKEY)
