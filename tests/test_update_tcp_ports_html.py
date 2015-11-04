import os
import unittest
import sys
from io import BytesIO, TextIOWrapper

try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

import mock

from update_tcp_ports_html import (
    main, get_owner, username, get_argv, format_arg, get_program
)


CMDLINES = {
    540: b"/sbin/rpcbind\0-w\0",
    821: b"/usr/bin/memcached\0-m\064\0-p\011211\0-u\0memcache\0-l\0127.0.0.1\0",
    824: b"/usr/sbin/sshd\0-D\0",
    849: b"/usr/sbin/rpc.mountd\0--manage-gids\0",
    851: b"/usr/bin/redis-server 127.0.0.1:6379\0\0\0\0\0\0\0\0",
    977: b"/usr/lib/postgresql/9.4/bin/postgres\0-D\0/var/lib/postgresql/9.4/main\0-c\0config_file=/etc/postgresql/9.4/main/postgresql.conf\0",
    1432: b"/usr/sbin/dnsmasq\0--conf-file=/var/lib/libvirt/dnsmasq/default.conf\0--leasefile-ro\0--dhcp-script=/usr/lib/libvirt/libvirt_leaseshelper\0",
    1643: b"/usr/sbin/apache2\0-k\0start\0",
    1691: b"/usr/sbin/dnsmasq\0--no-resolv\0--keep-in-foreground\0--no-hosts\0--bind-interfaces\0--pid-file=/run/sendsigs.omit.d/network-manager.dnsmasq.pid\0--listen-address=127.0.1.1\0--conf-file=/var/run/NetworkManager/dnsmasq.conf\0--cache-size=0\0--proxy-dnssec\0--enable-dbus=org.freedesktop.NetworkManager.dnsmasq\0--conf-dir=/etc/NetworkManager/dnsmasq.d\0",
    1728: b"/usr/sbin/cupsd\0-l\0",
    2150: b"(squid-1)\0-YC\0-f\0/etc/squid3/squid.conf\0",
    2408: b"/usr/lib/postfix/master\0",
    9000: b"/usr/bin/python2.7\0webserver.py\0--port=8080\0",
}

NETSTAT_SAMPLE = b"""\
Active Internet connections (only servers)
Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name
tcp        0      0 0.0.0.0:111             0.0.0.0:*               LISTEN      540/rpcbind
tcp        0      0 127.0.1.1:53            0.0.0.0:*               LISTEN      1691/dnsmasq
tcp        0      0 192.168.122.1:53        0.0.0.0:*               LISTEN      1432/dnsmasq
tcp        0      0 0.0.0.0:22              0.0.0.0:*               LISTEN      824/sshd
tcp        0      0 127.0.0.1:631           0.0.0.0:*               LISTEN      1728/cupsd
tcp        0      0 127.0.0.1:5432          0.0.0.0:*               LISTEN      977/postgres
tcp        0      0 127.0.0.1:25            0.0.0.0:*               LISTEN      2408/master
tcp        0      0 0.0.0.0:51033           0.0.0.0:*               LISTEN      849/rpc.mountd
tcp        0      0 0.0.0.0:2049            0.0.0.0:*               LISTEN      -
tcp        0      0 0.0.0.0:43461           0.0.0.0:*               LISTEN      -
tcp        0      0 0.0.0.0:57031           0.0.0.0:*               LISTEN      849/rpc.mountd
tcp        0      0 127.0.0.1:6379          0.0.0.0:*               LISTEN      851/redis-server 12
tcp        0      0 127.0.0.1:11211         0.0.0.0:*               LISTEN      821/memcached
tcp        0      0 0.0.0.0:60076           0.0.0.0:*               LISTEN      849/rpc.mountd
tcp6       0      0 :::111                  :::*                    LISTEN      540/rpcbind
tcp6       0      0 :::80                   :::*                    LISTEN      1643/apache2
tcp6       0      0 :::22                   :::*                    LISTEN      824/sshd
tcp6       0      0 ::1:631                 :::*                    LISTEN      1728/cupsd
tcp6       0      0 :::3128                 :::*                    LISTEN      2150/(squid-1)
tcp6       0      0 :::56664                :::*                    LISTEN      849/rpc.mountd
tcp6       0      0 :::39418                :::*                    LISTEN      849/rpc.mountd
tcp6       0      0 :::443                  :::*                    LISTEN      1643/apache2
tcp6       0      0 :::37055                :::*                    LISTEN      -
tcp6       0      0 :::2049                 :::*                    LISTEN      -
tcp6       0      0 :::33738                :::*                    LISTEN      849/rpc.mountd
"""

RPCINFO_SAMPLE = b"""\
   program vers proto   port  service
    100000    4   tcp    111  portmapper
    100000    3   tcp    111  portmapper
    100000    2   tcp    111  portmapper
    100000    4   udp    111  portmapper
    100000    3   udp    111  portmapper
    100000    2   udp    111  portmapper
    100005    1   udp  45550  mountd
    100005    1   tcp  51033  mountd
    100005    2   udp  39809  mountd
    100005    2   tcp  60076  mountd
    100005    3   udp  51044  mountd
    100005    3   tcp  57031  mountd
    100003    2   tcp   2049  nfs
    100003    3   tcp   2049  nfs
    100003    4   tcp   2049  nfs
    100227    2   tcp   2049
    100227    3   tcp   2049
    100003    2   udp   2049  nfs
    100003    3   udp   2049  nfs
    100003    4   udp   2049  nfs
    100227    2   udp   2049
    100227    3   udp   2049
    100021    1   udp  60768  nlockmgr
    100021    3   udp  60768  nlockmgr
    100021    4   udp  60768  nlockmgr
    100021    1   tcp  43461  nlockmgr
    100021    3   tcp  43461  nlockmgr
    100021    4   tcp  43461  nlockmgr
"""


class FakePopen(object):
    def __init__(self, command, stdout=None, stderr=None):
        if isinstance(command, tuple):
            command = list(command)
        if command == ['netstat', '-tnlvp']:
            self.stdout = BytesIO(NETSTAT_SAMPLE)
        elif command == ['rpcinfo', '-p']:
            self.stdout = BytesIO(RPCINFO_SAMPLE)
        else:
            self.stdout = BytesIO()


def fake_open(filename, mode='r'):
    if filename.startswith('/proc/') and filename.endswith('/cmdline'):
        pid = int(filename[len('/proc/'):-len('/cmdline')])
        f = BytesIO(CMDLINES[pid])
        if bytes is not str and mode != 'rb':
            f = TextIOWrapper(f, encoding='UTF-8')
        return f
    else:
        return open(filename, mode)


class TestProcHelpers(unittest.TestCase):

    def test_get_owner(self):
        self.assertEqual(get_owner(os.getpid()), os.getuid())

    def test_get_owner_process_is_gone(self):
        self.assertEqual(get_owner(-1), None)

    def test_username(self):
        self.assertEqual(username(os.getuid()), os.getenv('USER'))

    def test_username_no_such_user(self):
        self.assertEqual(username(-1), '-1')


class TestFormattingHelpers(unittest.TestCase):

    def test_format_arg(self):
        self.assertEqual(format_arg('--abc123'), '--abc123')
        self.assertEqual(format_arg('foo bar'), "'foo bar'")
        self.assertEqual(format_arg("it's alive"), "'it\\'s alive'")
        self.assertEqual(format_arg("two\nlines"), "'two\\nlines'")
        self.assertEqual(format_arg("\t"), "'\\t'")
        self.assertEqual(format_arg("\r"), "'\\r'")
        self.assertEqual(format_arg("\033"), "'\\x1b'")
        self.assertEqual(format_arg("\a"), "'\\x07'")
        self.assertEqual(format_arg("\b"), "'\\x08'")


class TestWithFakeEnvironment(unittest.TestCase):

    def setUp(self):
        patcher = mock.patch('subprocess.Popen', FakePopen)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch('update_tcp_ports_html.open', fake_open)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_main(self, *args):
        orig_sys_argv = sys.argv
        try:
            sys.argv = [
                'update_tcp_ports_html.py',
                '-o', '/dev/null',
            ] + list(args)
            main()
        finally:
            sys.argv = orig_sys_argv

    def test_main(self):
        self.run_main()

    def test_getargv(self):
        self.assertEqual(get_argv(9000),
                         ["/usr/bin/python2.7", "webserver.py", "--port=8080"])

    def test_get_program(self):
        self.assertEqual(get_program(9000), 'webserver.py')
