source := $(shell dpkg-parsechangelog | awk '$$1 == "Source:" { print $$2 }')
version := $(shell dpkg-parsechangelog | awk '$$1 == "Version:" { print $$2 }')
date := $(shell dpkg-parsechangelog | grep ^Date: | cut -d: -f 2- | date --date="$$(cat)" +%Y-%m-%d)
target_distribution := $(shell dpkg-parsechangelog | awk '$$1 == "Distribution:" { print $$2 }')

# Version and date in these should match overall package version
manpage = docs/pov-update-server-page.rst
mainscript = src/pov_server_page/update_server_page.py

# Manual pages that need to be built
manpage_sources = $(wildcard docs/*.rst)
manpages = $(manpage_sources:%.rst=%.8)

# change this to the lowest supported Ubuntu LTS
TARGET_DISTRO := focal

# for testing in vagrant:
#   mkdir -p ~/tmp/vagrantbox && cd ~/tmp/vagrantbox
#   vagrant init ubuntu/xenial64
#   vagrant ssh-config --host vagrantbox >> ~/.ssh/config
# now you can 'make vagrant-test-install', then 'ssh vagrantbox' and play
# with the package
VAGRANT_DIR = ~/tmp/vagrantbox
VAGRANT_SSH_ALIAS = vagrantbox

.DEFAULT_GOAL := all
include help.mk
HELP_INDENT = "  "
HELP_WIDTH = 34

##: Python code development

.PHONY: all
all: $(manpages)        ##: build (man pages)

%.1: %.rst
	rst2man $< > $@

%.8: %.rst
	rst2man $< > $@

.PHONY: test
test:                   ##: run tests
	tox -e py38,py310,py312 --devel

.PHONY: check
check: test flake8      ##: run tests and linters

.PHONY: flake8
flake8:                 ##: run flake8 linter
	tox -e flake8

.PHONY: coverage
coverage:               ##: measure test coverage
	tox -e coverage3

.PHONY: diff-cover
diff-cover: coverage    ##: find untested lines of code in your changes
	coverage xml
	diff-cover coverage.xml

##:

.PHONY: update-webtreemap-du
update-webtreemap-du:   ##: pull in a new snapshot of webtreemap-du
	git subtree pull --prefix=webtreemap-du https://github.com/mgedmin/webtreemap-du master

define check_version =
	@grep -qF $1 $2 || { \
	    echo "Version number in $2 doesn't match debian/changelog ($(version))" 2>&1; \
	    echo "Run make update-version" 2>&1; \
	    exit 1; \
	}
endef
define check_date =
	@grep -qF $1 $2 || { \
	    echo "Date in $2 doesn't match debian/changelog ($(date))" 2>&1; \
	    echo "Run make update-version" 2>&1; \
	    exit 1; \
	}
endef
define check_man_version =
	@grep -qF ":Version: $3" $1 || { \
	    echo "Version number in $1 doesn't match $2 ($3)" 2>&1; \
	    echo "Run make update-version" 2>&1; \
	    exit 1; \
	}
endef


disk_inventory_version = $(shell PYTHONPATH=src python3 -m pov_server_page.disk_inventory --version)
du_diff_version = $(shell PYTHONPATH=src python3 -m pov_server_page.du_diff --version)
machine_summary_version = $(shell PYTHONPATH=src python3 -m pov_server_page.machine_summary --version)


##: Run these when `make release` tells you to, otherwise ignore them


.PHONY: check-version
check-version:          ## (internal) check if 'make update-version' is needed
	$(call check_version,":Version: $(version)",$(manpage))
	$(call check_date,":Date: $(date)",$(manpage))
	$(call check_version,"__version__ = '$(version)'",$(mainscript))
	$(call check_date,"__date__ = '$(date)'",$(mainscript))
	$(call check_version,"version='$(version)'",setup.py)
	$(call check_man_version,docs/disk-inventory.rst,src/pov_server_page/disk_inventory.py,$(disk_inventory_version))
	$(call check_man_version,docs/du-diff.rst,src/pov_server_page/du_diff.py,$(du_diff_version))
	$(call check_man_version,docs/machine-summary.rst,src/pov_server_page/machine_summary.py,$(machine_summary_version))

.PHONY: update-version
update-version:         ##: update versions in man pages and scripts (from debian/changelog)
	sed -i -e 's/^:Version: .*/:Version: $(version)/' $(manpage)
	sed -i -e 's/^:Date: .*/:Date: $(date)/' $(manpage)
	sed -i -e "s/^__version__ = '.*'/__version__ = '$(version)'/" $(mainscript)
	sed -i -e "s/^__date__ = '.*'/__date__ = '$(date)'/" $(mainscript)
	sed -i -e "s/version='.*',/version='$(version)',/" setup.py
	sed -i -e 's/^:Version: .*/:Version: $(disk_inventory_version)/' docs/disk-inventory.rst
	sed -i -e 's/^:Version: .*/:Version: $(du_diff_version)/' docs/du-diff.rst
	sed -i -e 's/^:Version: .*/:Version: $(machine_summary_version)/' docs/machine-summary.rst
	@echo "Check if you need to update dates as well!"

.PHONY: check-target
check-target:           ## (internal) check if 'make update-target' is needed
	@test "$(target_distribution)" = "$(TARGET_DISTRO)" || { \
	    echo "Distribution in debian/changelog should be '$(TARGET_DISTRO)'" 2>&1; \
	    echo "Run make update-target" 2>&1; \
	    exit 1; \
	}

.PHONY: update-target
update-target:          ##: update release target in debian/changelog
	dch -r -D $(TARGET_DISTRO) ""

VCS_STATUS = git status --porcelain

.PHONY: clean-build-tree
clean-build-tree:       ## (internal) produce a clean build tree in pkgbuild/
                        ## this is needed because we don't want builds to make
                        ## changes to the real source tree, which is annoying;
                        ## as a price we can't build if we have uncommitted
                        ## changes as we rely on git archive to produce our tree
	@test -z "`$(VCS_STATUS) 2>&1`" || { \
	    echo; \
	    echo "Your working tree is not clean; please commit and try again" 1>&2; \
	    $(VCS_STATUS); \
	    echo 'E.g. run git commit -am "Release $(version)"' 1>&2; \
	    exit 1; }
	git pull -r
	rm -rf pkgbuild/$(source)
	git archive --format=tar --prefix=pkgbuild/$(source)/ HEAD | tar -xf -

.PHONY: source-package
source-package: check check-target check-version source-package-skipping-checks
                        ## (internal) run all possible checks and build a source
                        ## .deb, intended for testing and/or uploading to the PPA

.PHONY: source-package-skipping-checks
source-package-skipping-checks: clean-build-tree
                        ## (internal) build a source .deb without doing checks,
                        ## intended for faster testing
	cd pkgbuild/$(source) && debuild -S -i -k$(GPGKEY) -d
	rm -rf pkgbuild/$(source)
	@echo
	@echo "Built pkgbuild/$(source)_$(version)_source.changes"

##: Release time!

.PHONY: upload-to-ppa release
release upload-to-ppa: source-package  ##: prepare, build and upload a source .deb to the PPA
	dput ppa:pov/ppa pkgbuild/$(source)_$(version)_source.changes
	git tag -s $(version) -m "Release $(version)"
	git push
	git push --tags

##: Test before you release!

.PHONY: binary-package
binary-package: clean-build-tree    ##: build a binary .deb for testing locally
	cd pkgbuild/$(source) && debuild -i -k$(GPGKEY)
	rm -rf pkgbuild/$(source)
	@echo
	@echo "Built pkgbuild/$(source)_$(version)_all.deb"
	@echo "      pkgbuild/$(source)-py2_$(version)_all.deb"
	@echo "      pkgbuild/$(source)-py3_$(version)_all.deb"

.PHONY: vagrant-test-install
vagrant-test-install: binary-package  ## this is obsolete really
	cp pkgbuild/$(source)_$(version)_all.deb $(VAGRANT_DIR)/
	cd $(VAGRANT_DIR) && vagrant up
	ssh $(VAGRANT_SSH_ALIAS) 'sudo DEBIAN_FRONTEND=noninteractive dpkg -i /vagrant/$(source)_$(version)_all.deb; sudo apt-get install -f -y'

.PHONY: pbuilder-test-build
pbuilder-test-build: source-package-skipping-checks  ##: build a binary .deb using pbuilder, to find build problems
	# NB: you need to periodically run pbuilder-dist $(TARGET_DISTRO) update
	pbuilder-dist $(TARGET_DISTRO) build pkgbuild/$(source)_$(version).dsc
	@echo
	@echo "Built ~/pbuilder/$(TARGET_DISTRO)_result/$(source)_$(version)_all.deb"
	@echo "      ~/pbuilder/$(TARGET_DISTRO)_result/$(source)-py2_$(version)_all.deb"
	@echo "      ~/pbuilder/$(TARGET_DISTRO)_result/$(source)-py3_$(version)_all.deb"

.PHONY: autopkgtest-prepare-images
autopkgtest-prepare-images:     ##: prepare LXD containers for autopkgtest
	autopkgtest-build-lxd images:ubuntu/focal/amd64
	autopkgtest-build-lxd images:ubuntu/jammy/amd64
	autopkgtest-build-lxd images:ubuntu/noble/amd64

.PHONY: autopkgtest autopkgtest-with-full-build
autopkgtest autopkgtest-with-full-build:    ##: run package tests with autopkgtest
	autopkgtest . -- lxd autopkgtest/ubuntu/jammy/amd64 -- -e

.PHONY: autopkgtest
autopkgtest-built-packages:     ##: run autopkgtest using locally built binary .deb packages
	@test -e pkgbuild/$(source)_$(version)_amd64.changes || $(MAKE) binary-package
	# Note: if you build on Ubuntu focal and test on Ubuntu xenial, expect failures
	autopkgtest pkgbuild/$(source)_$(version)_amd64.changes -- lxd autopkgtest/ubuntu/focal/amd64 -- -e

.PHONY: autopkgtest-pbuilder-packages
autopkgtest-pbuilder-packages:  ##: run autopkgtest using pbuilder packages, targeting all distros
	@test -e ~/pbuilder/$(TARGET_DISTRO)_result/$(source)_$(version)_amd64.changes || $(MAKE) pbuilder-test-build
	autopkgtest ~/pbuilder/$(TARGET_DISTRO)_result/$(source)_$(version)_amd64.changes -- lxd autopkgtest/ubuntu/focal/amd64 -- -e
	autopkgtest ~/pbuilder/$(TARGET_DISTRO)_result/$(source)_$(version)_amd64.changes -- lxd autopkgtest/ubuntu/jammy/amd64 -- -e
	autopkgtest ~/pbuilder/$(TARGET_DISTRO)_result/$(source)_$(version)_amd64.changes -- lxd autopkgtest/ubuntu/noble/amd64 -- -e

.PHONY: autopkgtest-upgrades
autopkgtest-upgrades:   ##: use autopkgtest to test upgrades from current PPA
	autopkgtest \
	    --setup-commands='add-apt-repository -y ppa:pov && apt-get update && apt-get install -y pov-server-page' \
	    . -- lxd autopkgtest/ubuntu/focal/amd64 -- -e
