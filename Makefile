source := $(shell dpkg-parsechangelog | awk '$$1 == "Source:" { print $$2 }')
version := $(shell dpkg-parsechangelog | awk '$$1 == "Version:" { print $$2 }')
date := $(shell dpkg-parsechangelog | grep ^Date: | cut -d: -f 2- | date --date="$$(cat)" +%Y-%m-%d)
target_distribution := $(shell dpkg-parsechangelog | awk '$$1 == "Distribution:" { print $$2 }')

manpage = pov-update-server-page.rst

# change this to the lowest supported Ubuntu LTS
TARGET_DISTRO := trusty

# for testing in vagrant:
#   mkdir -p ~/tmp/vagrantbox && cd ~/tmp/vagrantbox
#   vagrant init ubuntu/trusty64
#   vagrant ssh-config --host vagrantbox >> ~/.ssh/config
# now you can 'make vagrant-test-install', then 'ssh vagrantbox' and play
# with the package
VAGRANT_DIR = ~/tmp/vagrantbox
VAGRANT_SSH_ALIAS = vagrantbox


.PHONY: all
all: pov-update-server-page.8 webtreemap webtreemap-du

%.8: %.rst
	rst2man $< > $@

webtreemap webtreemap-du:
	git submodule update --init

.PHONY: test check
test check: check-version
	nosetests

.PHONY: coverage
coverage:
	coverage erase
	detox -e coverage,coverage3
	coverage combine
	coverage report -m

.PHONY: diff-cover
diff-cover: coverage
	coverage xml
	diff-cover coverage.xml

.PHONY: checkversion
check-version:
	@grep -q ":Version: $(version)" $(manpage) || { \
	    echo "Version number in $(manpage) doesn't match debian/changelog ($(version))" 2>&1; \
	    echo "Run make update-version" 2>&1; \
	    exit 1; \
	}
	@grep -q ":Date: $(date)" $(manpage) || { \
	    echo "Date in $(manpage) doesn't match debian/changelog ($(date))" 2>&1; \
	    echo "Run make update-version" 2>&1; \
	    exit 1; \
	}

.PHONY: update-version
update-version:
	sed -i -e 's/^:Version: .*/:Version: $(version)/' $(manpage)
	sed -i -e 's/^:Date: .*/:Date: $(date)/' $(manpage)

.PHONY: check-target
check-target:
	@test "$(target_distribution)" = "$(TARGET_DISTRO)" || { \
	    echo "Distribution in debian/changelog should be '$(TARGET_DISTRO)'" 2>&1; \
	    echo 'Run dch -r -D $(TARGET_DISTRO) ""' 2>&1; \
	    exit 1; \
	}

.PHONY: install
install:
	install -m 644 server-page.conf $(DESTDIR)/etc/pov/server-page.conf
	install update_server_page.py $(DESTDIR)/usr/sbin/pov-update-server-page
	install update_ports_html.py $(DESTDIR)/usr/lib/pov-server-page/update-ports
	install changelog2html.py $(DESTDIR)/usr/lib/pov-server-page/changelog2html
	install dudiff2html.py $(DESTDIR)/usr/lib/pov-server-page/dudiff2html
	install collection.cgi $(DESTDIR)/usr/lib/pov-server-page/collection.cgi
	install webtreemap-du/du2webtreemap.py $(DESTDIR)/usr/lib/pov-server-page/du2webtreemap
	install -m 644 webtreemap/webtreemap.css $(DESTDIR)/usr/share/pov-server-page/webtreemap/
	install -m 644 webtreemap/webtreemap.js $(DESTDIR)/usr/share/pov-server-page/webtreemap/
	cd templates/ && for f in *.in; do install -m 644 $$f $(DESTDIR)/usr/share/pov-server-page/; done
	cd static/css && for f in *.css *.map; do install -m 644 $$f $(DESTDIR)/usr/share/pov-server-page/static/css/; done
	cd static/fonts && for f in *.eot *.svg *.ttf *.woff *.woff2; do install -m 644 $$f $(DESTDIR)/usr/share/pov-server-page/static/fonts/; done
	cd static/js && for f in *.js; do install -m 644 $$f $(DESTDIR)/usr/share/pov-server-page/static/js/; done
	install cron_daily.sh $(DESTDIR)/etc/cron.daily/pov-update-server-page


VCS_STATUS = git status --porcelain

.PHONY: clean-build-tree
clean-build-tree:
	@test -z "`$(VCS_STATUS) 2>&1`" || { \
	    echo; \
	    echo "Your working tree is not clean; please commit and try again" 1>&2; \
	    $(VCS_STATUS); \
	    echo 'E.g. run git commit -am "Release $(version)"' 1>&2; \
	    exit 1; }
	git pull -r
	rm -rf pkgbuild/$(source)
	git archive --format=tar --prefix=pkgbuild/$(source)/ HEAD | tar -xf -
	(cd webtreemap && git archive --format=tar --prefix=pkgbuild/$(source)/webtreemap/ HEAD) | tar -xf -
	(cd webtreemap-du && git archive --format=tar --prefix=pkgbuild/$(source)/webtreemap-du/ HEAD) | tar -xf -

.PHONY: source-package
source-package: clean-build-tree test check-target
	cd pkgbuild/$(source) && debuild -S -i -k$(GPGKEY)

.PHONY: upload-to-ppa release
release upload-to-ppa: source-package
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
	ssh $(VAGRANT_SSH_ALIAS) 'sudo DEBIAN_FRONTEND=noninteractive dpkg -i /vagrant/$(source)_$(version)_all.deb; sudo apt-get install -f -y && sudo pov-update-server-page -v'

.PHONY: pbuilder-test-build
pbuilder-test-build: source-package
	# NB: you need to periodically run pbuilder-dist $(TARGET_DISTRO) update
	pbuilder-dist $(TARGET_DISTRO) build pkgbuild/$(source)_$(version).dsc
	@echo
	@echo "Look for the package in ~/pbuilder/$(TARGET_DISTRO)/"
