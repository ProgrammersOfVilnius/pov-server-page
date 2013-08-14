HOSTNAME = $(shell hostname -f)
SHORTHOSTNAME = $(shell hostname -s)
AUTH_USER_FILE = /etc/apache2/fridge.passwd
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
