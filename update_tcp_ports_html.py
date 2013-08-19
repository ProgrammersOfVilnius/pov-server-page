#!/usr/bin/python
"""
Update TCP port assignments page in /var/www/HOSTNAME/ports/index.html.
"""

import datetime
import optparse
import os
import pwd
import re
import socket
import string
import subprocess
from cgi import escape
from collections import namedtuple, defaultdict


__version__ = '0.4.2'
__author__ = 'Marius Gedminas <marius@gedmin.as>'


HOSTNAME = socket.getfqdn()
OUTPUT = "/var/www/${hostname}/ports/index.html"


TEMPLATE = string.Template("""\
<html>
<head>
  <title>TCP port assignments on ${hostname}</title>
  <style>
    tr:first-child { background: #eee; }
    th { text-align: left; }
    tr.system { background: #eff; }
    tr.user { background: #cfc; }
    tr.user2 { background: #ffc; }
    tr.user7 { background: #efc; }
    tr.user8 { background: #fec; }
    tr.user9 { background: #cfe; }
    tr.user10 { background: #ccc; }
    tr.user11 { background: #cff; }
    td { padding: 0 6px; white-space: nowrap; text-overflow: ellipsis; }
    td:nth-child(1) { text-align: right; }
    td.public { font-weight: bold; }
  </style>
</head>
<body>
<h1>TCP port assignments on ${hostname}</h1>

<table>
  <tr>
    <th>Port</th>
    <th>User</th>
    <th>Program</th>
    <th>Command line</th>
  </tr>
  ${rows}
</table>

<p>Last updated on ${date}</p>

</body>
</html>
""")

ROW_TEMPLATE = string.Template("""\
  <tr class="${tr_class}">
    <td class="${port_class}" title="${ips}">${port}</td>
    <td>${user}</td>
    <td class="${port_class}">${program}</td>
    <td>${cmdline}</td>
  </tr>
""")


NetStatTuple = namedtuple('NetStatTuple', 'proto ip port pid program')


def netstat():
    with subprocess.Popen(['netstat', '-tnlvp'], stdout=subprocess.PIPE,
                          stderr=open('/dev/null', 'w')).stdout as f:
        for line in f:
            if line == 'Proto Recv-Q Send-Q Local Address           Foreign Address         State       PID/Program name\n':
                break
        for line in f:
            parts = line.split()
            proto = parts[0]
            local_addr = parts[3]
            state = parts[5]
            pid_program = parts[6]
            if proto in ('tcp', 'tcp6') and state == 'LISTEN':
                ip, port = local_addr.rsplit(':', 1)
                if '/' in pid_program:
                    pid, program = pid_program.split('/', 1)
                    pid = int(pid)
                else:
                    pid = None
                    program = pid_program
                yield NetStatTuple(proto, ip, int(port), pid, program)


def pmap_dump():
    with subprocess.Popen(['pmap_dump'], stdout=subprocess.PIPE,
                          stderr=open('/dev/null', 'w')).stdout as f:
        for line in f:
            parts = line.split()
            proto = parts[2]
            port = parts[3]
            program = parts[4]
            yield NetStatTuple(proto, None, int(port), None, program)


def rpcinfo_dump():
    with subprocess.Popen(['rpcinfo', '-p'], stdout=subprocess.PIPE,
                          stderr=open('/dev/null', 'w')).stdout as f:
        for line in f:
            # line is 'program vers proto port service'
            parts = line.split()
            if not parts or parts[0] == 'program':
                continue
            proto = parts[2]
            port = parts[3]
            program = parts[4] if len(parts) > 4 else '-'
            yield NetStatTuple(proto, None, int(port), None, program)


def merge_portmap_data(mapping, pmap_list, open_ports_only=True):
    for data in pmap_list:
        if data.port in mapping or not open_ports_only:
            mapping[data.port].append(data)


def get_owner(pid):
    try:
        return os.stat('/proc/%d' % pid).st_uid
    except (TypeError, OSError):
        return None


def username(uid):
    try:
        return pwd.getpwuid(uid).pw_name
    except TypeError:
        return '?'


def get_argv(pid):
    try:
        with open('/proc/%d/cmdline' % pid) as f:
            return f.read().split('\0')
    except (OSError, TypeError):
        return []


def format_arg(arg):
    safe_chars = string.ascii_letters + string.digits + '-=+,./:@^_~'
    if all(c in safe_chars for c in arg):
        return arg
    else:
        return "'%s'" % arg.encode('string-escape')


def format_argv(argv):
    return ' '.join(map(format_arg, argv))


def get_cmdline(pid):
    return format_argv(get_argv(pid))


def is_interpreter(program_name):
    return re.match(r'^python(\d([.]\d+)?)?$', program_name)


def get_program(pid):
    argv = get_argv(pid)
    if len(argv) >= 1 and ''.join(argv[1:]) == '' and ' ' in argv[0]:
        # programs that change their argv like postgrey or spamd
        argv = argv[0].split()
    args = map(escape, map(format_arg, argv))
    if not args:
        return ''
    # extract progname
    n = 0
    prefix, slash, progname = args[n].rpartition('/')
    if is_interpreter(progname):
        if len(args) >= 2:
            n = 1
            prefix, slash, progname = args[n].rpartition('/')
    return progname


def get_html_cmdline(pid):
    argv = get_argv(pid)
    if len(argv) >= 1 and ''.join(argv[1:]) == '' and ' ' in argv[0]:
        # programs that change their argv like postgrey or spamd
        argv = argv[0].split()
    args = map(escape, map(format_arg, argv))
    if not args:
        return ''
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


def get_port_mapping(netstat_data):
    mapping = defaultdict(list)
    for data in netstat_data:
        mapping[data.port].append(data)
    return mapping


def is_loopback_ip(ip):
    return ip == '::1' or ip.startswith('127.')


def render_row(netstat_list):
    assert len(netstat_list) >= 1
    port = netstat_list[0].port
    pids = set(t.pid for t in netstat_list if t.pid is not None)
    ips = set(t.ip for t in netstat_list if t.ip is not None)
    user = sorted(set(map(username, map(get_owner, pids)))) or '-'
    program = sorted(set(map(get_program, pids)))
    if not program:
        program = sorted(set(escape(t.program) for t in netstat_list
                             if t.program != '-')) or '-'
    commands = sorted(set(map(get_html_cmdline, pids)))
    if not commands:
        commands = ['<b>%s</b>' % p for p in program]
    return ROW_TEMPLATE.substitute(
        port=port,
        tr_class='system' if port < 1024 else 'user user%d' % (port // 1000),
        port_class='local' if all(is_loopback_ip(ip) for ip in ips) else 'public',
        ips=', '.join(sorted(ips)),
        user='<br>'.join(map(escape, user)),
        program='<br>'.join(program),
        cmdline='<br>'.join(commands),
    )


def render_rows(netstat_mapping):
    return ''.join(render_row(netstat_list)
                   for port, netstat_list in sorted(netstat_mapping.items()))


def render_html(netstat_mapping, hostname=HOSTNAME):
    rows = render_rows(netstat_mapping)
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return TEMPLATE.substitute(
        hostname=hostname,
        rows=rows,
        date=now,
    )


def render_cgi(netstat_mapping):
    print("Content-Type: text/html; charset=UTF-8")
    print("")
    print(render_html(netstat_mapping))


def render_file(netstat_mapping, output, hostname=HOSTNAME):
    with open(output, 'w') as f:
        f.write(render_html(netstat_mapping, hostname=hostname))


def main():
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
    mapping = get_port_mapping(netstat())
    if 111 in mapping: # portmap is used
        try:
            portmap_data = list(rpcinfo_dump())
        except OSError:
            portmap_data = list(pmap_dump())
        merge_portmap_data(mapping, portmap_data, open_ports_only=False)
    render_file(mapping, output=output, hostname=opts.hostname)


if __name__ == '__main__':
    main()
