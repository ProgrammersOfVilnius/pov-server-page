#!/usr/bin/python
"""
Update TCP & UDP port assignments page in /var/www/HOSTNAME/ports/index.html.
"""

import io
import logging
import optparse
import os
import pwd
import re
import socket
import string
import subprocess
import time
from collections import namedtuple, defaultdict
from contextlib import contextmanager

try:
    from html import escape
except ImportError:
    from cgi import escape


__version__ = '0.10.4'
__author__ = 'Marius Gedminas <marius@gedmin.as>'


log = logging.getLogger(__name__)


HOSTNAME = socket.getfqdn()
OUTPUT = "/var/www/${hostname}/ports/index.html"


TEMPLATE = string.Template("""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <meta name="viewport" content="width=device-width, initial-scale=1">

  <title>Open TCP & UDP ports on ${hostname}</title>
  <link rel="stylesheet" href="../static/css/bootstrap.min.css">
  <link rel="stylesheet" href="../static/css/style.css">
  <link rel="stylesheet" href="../static/css/ports.css">
</head>
<body>
<h1>Open TCP & UDP ports on ${hostname}</h1>

<table class="ports table table-hover">
<thead>
  <tr>
    <th>Protocol</th>
    <th>Port</th>
    <th>User</th>
    <th>Program</th>
    <th>Command line</th>
  </tr>
</thead>
<tbody>
  ${rows}
</tbody>
</table>

<footer>Last updated on ${date}.</footer>

</body>
</html>
""")

ROW_TEMPLATE = string.Template("""\
  <tr class="${tr_class}">
    <td class="${port_class}" title="${ips}">${proto}</td>
    <td class="${port_class}" title="${service}">${port}</td>
    <td class="text-nowrap">${user}</td>
    <td class="text-nowrap ${port_class}" title="${pids}">${program}</td>
    <td>${cmdline}</td>
  </tr>
""")


class NetStatTuple(namedtuple('NetStatTuple', 'protocol ip port pid program')):
    @property
    def proto(self):
        return self.protocol.rstrip('6')  # tcp6 -> tcp


@contextmanager
def pipe(*command):
    with open('/dev/null', 'wb') as devnull:
        with subprocess.Popen(command, stdout=subprocess.PIPE,
                              stderr=devnull).stdout as f:
            if bytes is not str:  # pragma: PY3
                f = io.TextIOWrapper(f, encoding='UTF-8', errors='replace')
            yield f


def netstat():
    with pipe('netstat', '-tunlvp') as f:
        failures = []
        for line in f:
            if line.rstrip() == 'Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name':
                break
            failures.append(line)
        else:
            log.warning('Failed to find expected netstat header in\n%s'
                        % ''.join(failures))
            return
        header = line
        failures = []
        for line in f:
            columns = 7 if line.startswith('tcp') else 6
            parts = line.split(None, columns - 1)
            if len(parts) != columns:
                failures.append(line)
                continue
            proto = parts[0]
            local_addr = parts[3]
            if proto in ('tcp', 'tcp6'):
                state = parts[5]
            else:
                state = None
            pid_program = parts[-1].rstrip()
            if proto in ('tcp', 'tcp6') and state != 'LISTEN':
                continue
            try:
                ip, port = local_addr.rsplit(':', 1)
                if '/' in pid_program:
                    pid, program = pid_program.split('/', 1)
                    pid = int(pid)
                else:
                    pid = None
                    program = pid_program
            except ValueError:
                failures.append(line)
                continue
            yield NetStatTuple(proto, ip, int(port), pid, program)
    if failures:
        log.warning('Failed to parse netstat output:\n%s'
                    % ''.join([header] + failures))


def rpcinfo_dump():
    with pipe('rpcinfo', '-p') as f:
        header = next(f)  # skip header
        failures = []
        for line in f:
            # line is 'program vers proto port service'
            parts = line.split()
            if not parts:
                continue
            if len(parts) not in (4, 5):
                failures.append(line)
                continue
            proto = parts[2]
            port = parts[3]
            program = parts[4] if len(parts) > 4 else '-'
            yield NetStatTuple(proto, None, int(port), None, program)
    if failures:
        log.warning('Failed to parse rpcinfo output:\n%s'
                    % ''.join([header] + failures))


def merge_portmap_data(mapping, pmap_list, open_ports_only=False):
    for data in pmap_list:
        if (data.proto, data.port) in mapping or not open_ports_only:
            mapping[data.proto, data.port].append(data)


def systemctl_list_sockets():
    with pipe('systemctl', 'list-sockets', '--show-types') as f:
        header = next(f).rstrip()
        cols = [0] + [m.start() + 1 for m in re.finditer(r' [^ ]', header)] + [None]
        cols = [slice(col, nextcol) for col, nextcol in zip(cols, cols[1:])]
        failures = []
        for line in f:
            line = line.rstrip()
            if not line:
                break
            parts = [line[col].rstrip() for col in cols]
            try:
                listen, type_, unit, activates = parts
                proto = {'Stream': 'tcp', 'Datagram': 'udp'}.get(type_)
                if not proto or ':' not in listen:
                    continue
                ip, port = listen.rsplit(':', 1)
            except ValueError:
                failures.append(line)
                continue
            yield NetStatTuple(proto, ip, int(port), None, unit)
    if failures:
        log.warning('Failed to parse systemctl list-sockets output:\n%s'
                    % '\n'.join([header] + failures))


def get_owner(pid):
    try:
        return os.stat('/proc/%d' % pid).st_uid
    except (TypeError, OSError):
        return None


def username(uid):
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)
    except TypeError:
        return '?'


def get_argv(pid):
    try:
        with open('/proc/%d/cmdline' % pid) as f:
            argv = f.read().split('\0')
    except (TypeError, IOError):
        return []
    else:
        if argv and not argv[-1]:
            argv = argv[:-1]
        return argv


def format_arg(arg):
    safe_chars = string.ascii_letters + string.digits + '-=+,./:@^_~'
    if all(c in safe_chars for c in arg):
        return arg
    else:
        return "'%s'" % ''.join("\\'" if c == "'" else
                                "\\n" if c == "\n" else
                                "\\r" if c == "\r" else
                                "\\t" if c == "\t" else
                                "\\x%02x" % ord(c) if ord(c) < 32 else
                                c for c in arg)


def is_interpreter(program_name):
    return re.match(r'^python(\d([.]\d+)?)?$', program_name)


def get_program(pid, unknown='-'):
    argv = get_argv(pid)
    if len(argv) >= 1 and ''.join(argv[1:]) == '' and ' ' in argv[0]:
        # programs that change their argv like postgrey or spamd
        argv = argv[0].split()
        argv[0] = argv[0].rstrip(':')
    args = [escape(format_arg(arg)) for arg in argv]
    if not args:
        return unknown
    # extract progname
    n = 0
    prefix, slash, progname = args[n].rpartition('/')
    if is_interpreter(progname):
        if len(args) >= 2:
            n = 1
            prefix, slash, progname = args[n].rpartition('/')
    return progname


def get_html_cmdline(pid, unknown='-'):
    argv = get_argv(pid)
    if len(argv) >= 1 and ''.join(argv[1:]) == '' and ' ' in argv[0]:
        # programs that change their argv like postgrey or spamd
        argv = argv[0].split()
    args = [escape(format_arg(arg)) for arg in argv]
    if not args:
        return unknown
    # highlight progname
    n = 0
    prefix, slash, progname = args[n].rpartition('/')
    if is_interpreter(progname):
        if len(args) >= 2:
            n = 1
            prefix, slash, progname = args[n].rpartition('/')
    if progname:
        args[n] = '%s%s<b>%s</b>' % (prefix, slash, progname)
    return ' '.join(args)


def parse_port_mapping(netstat_data):
    mapping = defaultdict(list)
    for data in netstat_data:
        mapping[data.proto, data.port].append(data)
    return mapping


def get_port_mapping():
    mapping = parse_port_mapping(netstat())
    if ('tcp', 111) in mapping: # portmap is used
        portmap_data = list(rpcinfo_dump())
        merge_portmap_data(mapping, portmap_data)
    # It's not safe to filter on data.program, it might be 'systemd', but it
    # might also be 'init' -- and if we switch to ss(8) rather than netstat(8),
    # we no longer get program names.  We assume that pid 1 is systemd always,
    # which is true for Ubuntu.
    if any(data.pid == 1 for plist in mapping.values() for data in plist):
        systemd_sockets = list(systemctl_list_sockets())
        merge_portmap_data(mapping, systemd_sockets)
    return mapping


def is_loopback_ip(ip):
    return ip == '::1' or ip.startswith('127.')


def parse_services(filename='/etc/services'):
    services = {}
    try:
        with open(filename) as f:
            for line in f:
                parts = line.partition('#')[0].split()
                if len(parts) >= 2:
                    key = parts[1]
                    primary = parts[0]
                    aliases = parts[2:]
                    services[key] = [primary] + aliases
    except IOError:
        pass
    return services


def get_service_name(proto, port, _cache={}):
    if 'services' not in _cache:
        _cache['services'] = parse_services()
    return '/'.join(_cache['services'].get('%s/%s' % (port, proto), []))


def render_row(netstat_list):
    assert len(netstat_list) >= 1
    proto = netstat_list[0].proto
    port = netstat_list[0].port
    pids = sorted(set(t.pid for t in netstat_list if t.pid is not None))
    ips = set(t.ip for t in netstat_list if t.ip is not None)
    user = sorted(set(map(username, map(get_owner, pids)))) or '-'
    program = sorted(set(map(get_program, pids)))
    if not program or pids == [1] and (program == ['systemd'] or program == ['system']):
        program = sorted(set(escape(t.program) or '-' for t in netstat_list)) or '-'
    commands = sorted(set(map(get_html_cmdline, pids)))
    if not commands:
        commands = ['<b>%s</b>' % p for p in program]
    return ROW_TEMPLATE.substitute(
        proto=proto,
        port=port,
        service=get_service_name(proto, port),
        tr_class='system' if port < 1024 else 'user user%d' % (port // 1000),
        port_class='local' if all(is_loopback_ip(ip) for ip in ips) else 'public',
        ips=', '.join(sorted(ips)),
        user='<p>'.join(escape(u) or '-' for u in user),
        pids=', '.join('pid %s' % pid for pid in pids),
        program='<p>'.join(program),
        cmdline='<p>'.join(commands),
    )


def render_rows(netstat_mapping):
    return ''.join(render_row(netstat_list)
                   for (proto, port), netstat_list in sorted(netstat_mapping.items()))


def render_html(netstat_mapping, hostname=HOSTNAME):
    rows = render_rows(netstat_mapping)
    now = time.strftime('%Y-%m-%d %H:%M:%S %z')
    return TEMPLATE.substitute(
        hostname=hostname,
        rows=rows,
        date=now,
    )


def render_file(netstat_mapping, output, hostname=HOSTNAME):
    with open(output, 'w') as f:
        f.write(render_html(netstat_mapping, hostname=hostname))


def init_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(logging.StreamHandler())


def main():
    init_logging()
    parser = optparse.OptionParser(usage='usage: %prog [options]',
                                   version=__version__)
    parser.add_option('-H', '--hostname', default=HOSTNAME,
                      help='Specify hostname explicitly (default: %default)')
    parser.add_option('-o', '--output', default=OUTPUT,
                      help='Specify output file name (default: %default)')
    opts, args = parser.parse_args()
    if args:
        parser.error('unexpected arguments')
    output = opts.output.replace('${hostname}', opts.hostname)
    mapping = get_port_mapping()
    render_file(mapping, output=output, hostname=opts.hostname)


if __name__ == '__main__':
    main()
