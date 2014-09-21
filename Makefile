source := $(shell dpkg-parsechangelog | awk '$$1 == "Source:" { print $$2 }')
version := $(shell dpkg-parsechangelog | awk '$$1 == "Version:" { print $$2 }')
date := $(shell dpkg-parsechangelog | grep ^Date: | cut -d: -f 2- | date --date="$$(cat)" +%Y-%m-%d)

manpage = pov-update-server-page.rst

# for testing in vagrant:
#   vagrant box add precise64 http://files.vagrantup.com/precise64.box
#   mkdir -p ~/tmp/vagrantbox && cd ~/tmp/vagrantbox
#   vagrant init precise64
#   vagrant ssh-config --host vagrantbox >> ~/.ssh/config
# now you can 'make vagrant-test-install', then 'ssh vagrantbox' and play
# with the package
VAGRANT_DIR = ~/tmp/vagrantbox
VAGRANT_SSH_ALIAS = vagrantbox


.PHONY: all
all: pov-update-server-page.8

%.8: %.rst
	rst2man $< > $@

.PHONY: test check
test check: check-version
	nosetests

.PHONY: checkversion
check-version:
	@grep -q ":Version: $(version)" $(manpage) || { \
	    echo "Version number in $(manpage) doesn't match debian/changelog ($(version))" 2>&1; \
	    exit 1; \
	}
	@grep -q ":Date: $(date)" $(manpage) || { \
	    echo "Date in $(manpage) doesn't match debian/changelog ($(date))" 2>&1; \
	    exit 1; \
	}

.PHONY: install
install:
	install -m 644 server-page.conf $(DESTDIR)/etc/pov/server-page.conf
	install update_server_page.py $(DESTDIR)/usr/sbin/pov-update-server-page
	install update_tcp_ports_html.py $(DESTDIR)/usr/lib/pov-server-page/update-ports
	install changelog2html.py $(DESTDIR)/usr/lib/pov-server-page/changelog2html
	install collection.cgi $(DESTDIR)/usr/lib/pov-server-page/collection.cgi
	install webtreemap-du/du2webtreemap.py $(DESTDIR)/usr/lib/pov-server-page/du2webtreemap
	install -m 644 templates/apache.conf.in $(DESTDIR)/usr/share/pov-server-page/
	install -m 644 templates/index.html.in $(DESTDIR)/usr/share/pov-server-page/
	install -m 644 templates/du.html.in $(DESTDIR)/usr/share/pov-server-page/
	install -m 644 templates/du-page.html.in $(DESTDIR)/usr/share/pov-server-page/
	install -m 644 webtreemap/webtreemap.css $(DESTDIR)/usr/share/pov-server-page/webtreemap/
	install -m 644 webtreemap/webtreemap.js $(DESTDIR)/usr/share/pov-server-page/webtreemap/
	install cron_daily.sh $(DESTDIR)/etc/cron.daily/pov-update-server-page


VCS_STATUS = git status --porcelain

.PHONY: clean-build-tree
clean-build-tree:
	@test -z "`$(VCS_STATUS) 2>&1`" || { echo; echo "Your working tree is not clean; please commit and try again" 1>&2; $(VCS_STATUS); exit 1; }
	rm -rf pkgbuild/$(source)
	git archive --format=tar --prefix=pkgbuild/$(source)/ HEAD | tar -xf -
	(cd webtreemap && git archive --format=tar --prefix=pkgbuild/$(source)/webtreemap/ HEAD) | tar -xf -
	(cd webtreemap-du && git archive --format=tar --prefix=pkgbuild/$(source)/webtreemap-du/ HEAD) | tar -xf -

.PHONY: source-package
source-package: clean-build-tree test
	cd pkgbuild/$(source) && debuild -S -i -k$(GPGKEY)

.PHONY: upload-to-ppa
upload-to-ppa: source-package
	dput ppa:pov/ppa pkgbuild/$(source)_$(version)_source.changes
	git tag $(version)
	git push
	git push --tags

.PHONY: binary-package
binary-package: clean-build-tree
	cd pkgbuild/$(source) && debuild -i -k$(GPGKEY)
	@echo
	@echo "Built pkgbuild/$(source)_$(version)_all.deb"

.PHONY: vagrant-test-install
vagrant-test-install: binary-package
	cp pkgbuild/$(source)_$(version)_all.deb $(VAGRANT_DIR)/
	cd $(VAGRANT_DIR) && vagrant up
	ssh $(VAGRANT_SSH_ALIAS) 'sudo DEBIAN_FRONTEND=noninteractive dpkg -i /vagrant/$(source)_$(version)_all.deb; sudo apt-get install -f'

.PHONY: pbuilder-test-build
pbuilder-test-build: source-package
	pbuilder-dist precise build pkgbuild/$(source)_$(version).dsc
	echo "Look for the package in ~/pbuilder/precise_result/"
