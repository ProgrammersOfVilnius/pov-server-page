import getpass
import os
import sys
import textwrap
import unittest
from contextlib import closing
from io import BytesIO, TextIOWrapper

import mock

from pov_server_page.update_ports_html import (
    NetStatTuple,
    format_arg,
    get_argv,
    get_html_cmdline,
    get_owner,
    get_port_mapping,
    get_program,
    main,
    netstat,
    parse_services,
    render_row,
    rpcinfo_dump,
    systemctl_list_sockets,
    username,
    wireguard_ports,
)


try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO


CMDLINES = {
    1: b"/lib/systemd/systemd\0--system\0--deserialize\00023\0",
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
    9003: b"nginx: master process /opt/gitlab/embedded/sbin/nginx -p /var/opt/gitlab/nginx",
}

NETSTAT_COMMAND = ('netstat', '-tunlvp')
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
tcp        0      0 127.0.0.1:7777          10.20.30.40:40626       ESTABLISHED 22591/ssh
tcp        0      0 127.0.0.1:8000          0.0.0.0:*               LISTEN      1/systemd
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
udp        0      0 0.0.0.0:5353            0.0.0.0:*                           5281/chromium-brows
udp        0      0 0.0.0.0:5353            0.0.0.0:*                           -
udp        0      0 0.0.0.0:48214           0.0.0.0:*                           -
udp        0      0 127.0.1.1:53            0.0.0.0:*                           -
udp        0      0 192.168.122.1:53        0.0.0.0:*                           -
udp        0      0 0.0.0.0:67              0.0.0.0:*                           -
udp        0      0 0.0.0.0:68              0.0.0.0:*                           -
udp        0      0 192.168.1.165:123       0.0.0.0:*                           -
udp        0      0 127.0.0.1:123           0.0.0.0:*                           -
udp        0      0 0.0.0.0:123             0.0.0.0:*                           -
udp        0      0 0.0.0.0:631             0.0.0.0:*                           -
udp        0      0 224.0.0.251:5353        0.0.0.0:*                           9100/chrome --no-de
udp6       0      0 :::5353                 :::*                                -
udp6       0      0 :::38336                :::*                                -
udp6       0      0 fe80::52ca:9cd0:ed7:123 :::*                                -
udp6       0      0 ::1:123                 :::*                                -
udp6       0      0 :::123                  :::*                                -
"""

RPCINFO_COMMAND = ('rpcinfo', '-p')
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

SYSTEMCTL_LIST_SOCKETS_COMMAND = ('systemctl', 'list-sockets', '--show-types')
SYSTEMCTL_LIST_SOCKETS_SAMPLE = (
    # NB: the trailing spaces are important
    b"LISTEN                          TYPE             UNITS                           ACTIVATES               \n"
    b"/run/apport.socket              Stream           apport-forward.socket                                   \n"
    b"/run/spinta/socket              Stream           spinta.socket                   spinta.service          \n"
    b"/run/systemd/initctl/fifo       FIFO             systemd-initctl.socket          systemd-initctl.service \n"
    b"/run/systemd/journal/dev-log    Datagram         systemd-journald-dev-log.socket systemd-journald.service\n"
    b"/run/systemd/journal/socket     Datagram         systemd-journald.socket         systemd-journald.service\n"
    b"/run/systemd/journal/stdout     Stream           systemd-journald.socket         systemd-journald.service\n"
    b"/run/systemd/journal/syslog     Datagram         syslog.socket                   rsyslog.service         \n"
    b"/run/udev/control               SequentialPacket systemd-udevd-control.socket    systemd-udevd.service   \n"
    b"/run/uuidd/request              Stream           uuidd.socket                    uuidd.service           \n"
    b"/var/run/dbus/system_bus_socket Stream           dbus.socket                     dbus.service            \n"
    b"127.0.0.1:8000                  Stream           spinta.socket                   spinta.service          \n"
    b"kobject-uevent 1                Netlink          systemd-udevd-kernel.socket     systemd-udevd.service   \n"
    b"\n"
    b"12 sockets listed.\n"
    b"Pass --all to see loaded but inactive sockets, too.\n"
)

WIREGUARD_COMMAND = ('wg', 'show', 'all', 'listen-port')
WIREGUARD_SAMPLE = (
    b"wg0\t56390\n"
    b"wg1\t38837\n"
)

DEFAULT_COMMANDS = {
    NETSTAT_COMMAND: NETSTAT_SAMPLE,
    RPCINFO_COMMAND: RPCINFO_SAMPLE,
    SYSTEMCTL_LIST_SOCKETS_COMMAND: SYSTEMCTL_LIST_SOCKETS_SAMPLE,
    WIREGUARD_COMMAND: WIREGUARD_SAMPLE,
}


SERVICES = """\
# Network services, Internet style

http\t\t80/tcp\t\twww\t\t# WorldWideWeb HTTP
https\t\t443/tcp\t\t\t\t# http protocol over TLS/SSL
"""


class FakePopen(object):

    def __init__(self, commands=None):
        self._commands = DEFAULT_COMMANDS if commands is None else commands

    def __call__(self, command, stdout=None, stderr=None):
        try:
            return _FakePopen(self._commands[tuple(command)])
        except KeyError:
            raise AssertionError('unexpected command: %r' % list(command))


class _FakePopen(object):
    def __init__(self, stdout):
        self.stdout = BytesIO(stdout)


def fake_open(filename, mode='r'):
    if filename.startswith('/proc/') and filename.endswith('/cmdline'):
        pid = int(filename[len('/proc/'):-len('/cmdline')])
        try:
            f = BytesIO(CMDLINES[pid])
        except KeyError:
            raise IOError('no such file ekcetera')
        if bytes is not str and mode != 'rb':
            f = TextIOWrapper(f, encoding='UTF-8')
        return f
    elif filename == '/etc/services':
        return closing(StringIO(SERVICES))
    else:
        return open(filename, mode)


class MockMixin:

    def patch(self, what, *with_what, **kw):
        patcher = mock.patch(what, *with_what, **kw)
        retval = patcher.start()
        self.addCleanup(patcher.stop)
        return retval


class TestNetstat(MockMixin, unittest.TestCase):

    def test_netstat_failure_handling_no_header(self):
        self.patch('subprocess.Popen', FakePopen({
            NETSTAT_COMMAND: (
                b"netstat: command not found\n"
            ),
        }))
        self.assertEqual(list(netstat()), [])

    def test_netstat_failure_handling(self):
        self.patch('subprocess.Popen', FakePopen({
            NETSTAT_COMMAND: (
                b'Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name\n'
                b'tcp        0      0 0.0.0.0:2049            0.0.0.0:*               LISTEN\n'
                b'tcp        0      0 127.0.0.1               0.0.0.0:*               LISTEN      851/redis-server 12\n'
                b'tcp6       0      0 :::80                   :::*                    LISTEN      xyzzy/apache2\n'
            ),
        }))
        self.assertEqual(list(netstat()), [])


class TestRpcinfo(MockMixin, unittest.TestCase):

    def test_rpcinfo_dump_sockets_error_handling(self):
        self.patch('subprocess.Popen', FakePopen({
            # imagine a couple of columns are randomly missing (unlikely, but)
            RPCINFO_COMMAND: (
                b"   proto   port  service\n"
                b"     tcp    111  portmapper\n"
                b"\n"
            ),
        }))
        self.assertEqual(list(rpcinfo_dump()), [])


class TestSystemctl(MockMixin, unittest.TestCase):

    def test_systemctl_list_sockets(self):
        self.patch('subprocess.Popen', FakePopen())
        self.assertEqual(list(systemctl_list_sockets()), [
            NetStatTuple('tcp', '127.0.0.1', 8000, None, 'spinta.socket'),
        ])

    def test_systemctl_list_sockets_error_handling(self):
        self.patch('subprocess.Popen', FakePopen({
            # imagine a column is randomly missing (unlikely, but)
            SYSTEMCTL_LIST_SOCKETS_COMMAND: (
                b"LISTEN             TYPE   UNITS                \n"
                b"/run/apport.socket Stream apport-forward.socket\n"
            ),
        }))
        self.assertEqual(list(systemctl_list_sockets()), [])


class TestWireguard(MockMixin, unittest.TestCase):

    def test_wireguard_ports(self):
        self.patch('os.path.exists', return_value=True)
        self.patch('subprocess.Popen', FakePopen())
        self.assertEqual(list(wireguard_ports()), [
            NetStatTuple('udp', None, 56390, None, 'wireguard (wg0)'),
            NetStatTuple('udp', None, 38837, None, 'wireguard (wg1)'),
        ])

    def test_wireguard_ports_no_wg(self):
        self.patch('os.path.exists', return_value=False)
        self.patch('subprocess.Popen', FakePopen())
        self.assertEqual(list(wireguard_ports()), [])

    def test_wireguard_ports_failure_handling(self):
        self.patch('os.path.exists', return_value=True)
        self.patch('subprocess.Popen', FakePopen({
            WIREGUARD_COMMAND: (
                b"something unrelated\n"
            )
        }))
        self.assertEqual(list(wireguard_ports()), [])


class TestProcHelpers(unittest.TestCase):

    def test_get_owner(self):
        self.assertEqual(get_owner(os.getpid()), os.getuid())

    def test_get_owner_process_is_gone(self):
        self.assertEqual(get_owner(-1), None)

    def test_username(self):
        self.assertEqual(username(os.getuid()), getpass.getuser())

    def test_username_no_such_user(self):
        self.assertEqual(username(-1), '-1')

    def test_username_unknown_user(self):
        self.assertEqual(username(None), '?')


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


class TestGetPortMapping(MockMixin, unittest.TestCase):

    def setUp(self):
        self.patch('subprocess.Popen', FakePopen())
        self.patch('pov_server_page.update_ports_html.open', fake_open)

    def test_systemd_integration(self):
        mapping = get_port_mapping()
        self.assertEqual(mapping['tcp', 8000], [
            NetStatTuple('tcp', '127.0.0.1', 8000, 1, 'systemd'),
            NetStatTuple('tcp', '127.0.0.1', 8000, None, 'spinta.socket'),
        ])


class TestParseServices(unittest.TestCase):

    def test_etc_services_missing(self):
        with mock.patch('pov_server_page.update_ports_html.open',
                        side_effect=IOError(2, "No such file")):
            self.assertEqual(parse_services(), {})


class TestWithFakeEnvironment(MockMixin, unittest.TestCase):

    def setUp(self):
        self.patch('subprocess.Popen', FakePopen())
        self.patch('pov_server_page.update_ports_html.open', fake_open)
        self.stderr = self.patch('sys.stderr', StringIO())

    def run_main(self, *args):
        orig_sys_argv = sys.argv
        try:
            sys.argv = [
                'update_ports_html.py',
                '-o', '/dev/null',
            ] + list(args)
            main()
        finally:
            sys.argv = orig_sys_argv

    def test_main(self):
        self.run_main()

    def test_main_unexpected_arguments(self):
        with self.assertRaises(SystemExit):
            self.run_main('foo')

    def test_getargv(self):
        self.assertEqual(get_argv(9000),
                         ["/usr/bin/python2.7", "webserver.py", "--port=8080"])

    def test_getargv_no_trailing_nul(self):
        self.assertEqual(get_argv(9003),
                         ["nginx: master process /opt/gitlab/embedded/sbin/nginx -p /var/opt/gitlab/nginx"])

    def test_get_program(self):
        self.assertEqual(get_program(9000), 'webserver.py')

    def test_get_program_unknown_pid(self):
        self.assertEqual(get_program(None), '-')

    def test_get_html_cmdline(self):
        self.assertEqual(get_html_cmdline(9000), '/usr/bin/python2.7 <b>webserver.py</b> --port=8080')

    def test_get_html_cmdline_program_disappeared(self):
        self.assertEqual(get_html_cmdline(8999), '-')

    def test_get_html_cmdline_pid_unknown(self):
        self.assertEqual(get_html_cmdline(None), '-')

    def test_render_row_pid_disappeared(self):
        self.assertEqual(textwrap.dedent(render_row([
            NetStatTuple('tcp6', '::', 80, None, 'apache2')
        ])), textwrap.dedent('''\
            <tr class="system">
              <td class="public" title="::">tcp</td>
              <td class="public" title="http/www">80</td>
              <td class="text-nowrap">-</td>
              <td class="text-nowrap public" title="">apache2</td>
              <td><b>apache2</b></td>
            </tr>
          '''))

    def test_render_row_systemd_socket(self):
        self.assertEqual(textwrap.dedent(render_row([
            NetStatTuple('tcp', '127.0.0.1', 8000, 1, 'systemd'),
            NetStatTuple('tcp', '127.0.0.1', 8000, None, 'spinta.socket'),
        ])), textwrap.dedent('''\
            <tr class="user user8">
              <td class="local" title="127.0.0.1">tcp</td>
              <td class="local" title="">8000</td>
              <td class="text-nowrap">root</td>
              <td class="text-nowrap local" title="pid 1">spinta.socket<p>systemd</td>
              <td>/lib/systemd/<b>systemd</b> --system --deserialize 23</td>
            </tr>
          '''))
