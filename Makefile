source := $(shell dpkg-parsechangelog | awk '$$1 == "Source:" { print $$2 }')
version := $(shell dpkg-parsechangelog | awk '$$1 == "Version:" { print $$2 }')
date := $(shell dpkg-parsechangelog | grep ^Date: | cut -d: -f 2- | date --date="$$(cat)" +%Y-%m-%d)
target_distribution := $(shell dpkg-parsechangelog | awk '$$1 == "Distribution:" { print $$2 }')

manpage = pov-update-server-page.rst
mainscript = src/pov_server_page/update_server_page.py

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

.PHONY: test
test:
	tox -e py27 --devel

.PHONY: check
check: test check-version

.PHONY: coverage
coverage:
	coverage erase
	tox -e coverage,coverage3
	coverage combine
	coverage report -m --fail-under=100

.PHONY: diff-cover
diff-cover: coverage
	coverage xml
	diff-cover coverage.xml

.PHONY: check-version
check-version:
	@grep -qF ":Version: $(version)" $(manpage) || { \
	    echo "Version number in $(manpage) doesn't match debian/changelog ($(version))" 2>&1; \
	    echo "Run make update-version" 2>&1; \
	    exit 1; \
	}
	@grep -qF ":Date: $(date)" $(manpage) || { \
	    echo "Date in $(manpage) doesn't match debian/changelog ($(date))" 2>&1; \
	    echo "Run make update-version" 2>&1; \
	    exit 1; \
	}
	@grep -qF "__version__ = '$(version)'" $(mainscript) || { \
	    echo "Version number in $(mainscript) doesn't match debian/changelog ($(version))" 2>&1; \
	    echo "Run make update-version" 2>&1; \
	    exit 1; \
	}
	@grep -qF "__date__ = '$(date)'" $(mainscript) || { \
	    echo "Date in $(mainscript) doesn't match debian/changelog ($(date))" 2>&1; \
	    echo "Run make update-version" 2>&1; \
	    exit 1; \
	}

.PHONY: update-version
update-version:
	sed -i -e 's/^:Version: .*/:Version: $(version)/' $(manpage)
	sed -i -e 's/^:Date: .*/:Date: $(date)/' $(manpage)
	sed -i -e "s/^__version__ = '.*'/__version__ = '$(version)'/" $(mainscript)
	sed -i -e "s/^__date__ = '.*'/__date__ = '$(date)'/" $(mainscript)

.PHONY: check-target
check-target:
	@test "$(target_distribution)" = "$(TARGET_DISTRO)" || { \
	    echo "Distribution in debian/changelog should be '$(TARGET_DISTRO)'" 2>&1; \
	    echo "Run make update-target" 2>&1; \
	    exit 1; \
	}

.PHONY: update-target
update-target:
	dch -r -D $(TARGET_DISTRO) ""

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
source-package: check check-target clean-build-tree
	cd pkgbuild/$(source) && debuild -S -i -k$(GPGKEY)
	rm -rf pkgbuild/$(source)
	@echo
	@echo "Built pkgbuild/$(source)_$(version)_source.changes"

.PHONY: upload-to-ppa release
release upload-to-ppa: source-package
	dput ppa:pov/ppa pkgbuild/$(source)_$(version)_source.changes
	git tag $(version)
	git push
	git push --tags

.PHONY: binary-package
binary-package: clean-build-tree
	cd pkgbuild/$(source) && debuild -i -k$(GPGKEY)
	rm -rf pkgbuild/$(source)
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
