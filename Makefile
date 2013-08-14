HOSTNAME = $(shell hostname -f)
SHORTHOSTNAME = $(shell hostname -s)
AUTH_USER_FILE = /var/www/$(HOSTNAME)/.htpasswd
COLLECTION_CGI = /usr/local/sbin/collection.cgi

templates = $(wildcard *.in)
outputs = $(templates:%.in=build/%)

all: $(outputs)

build/%: %.in
	@mkdir -p build
	sed -e 's,{HOSTNAME},$(HOSTNAME),g' \
	    -e 's,{SHORTHOSTNAME},$(SHORTHOSTNAME),g' \
	    -e 's,{COLLECTION_CGI},$(COLLECTION_CGI),g' \
	    -e 's,{AUTH_USER_FILE},$(AUTH_USER_FILE),g' \
	    < $< > $@


install: install-var-www install-collection-cgi install-apache-vhost

install-var-www: build/index.html
	install -d $(DESTDIR)/var/www/$(HOSTNAME)
	install -m 644 build/index.html $(DESTDIR)/var/www/$(HOSTNAME)/

install-collection-cgi:
	install collection.cgi $(DESTDIR)$(COLLECTION_CGI)

install-apache-vhost: build/apache.conf
	install -m 644 build/apache.conf $(DESTDIR)/etc/apache2/sites-available/$(HOSTNAME)
