#!/usr/bin/python
"""
Usage: du-diff filename1 filename2

Computes the differences between two disk usage files (produced by du > filename).

Can read from gzipped files.
"""

import sys
import gzip
import argparse
from collections import defaultdict, namedtuple


__author__ = 'Marius Gedminas <marius@gedmin.as>'
__version__ = '1.1'
__date__ = '2018-01-19'


def parse_du(stream):
    res = defaultdict(int)
    for line in stream:
        if not line.strip():
            continue
        size, name = line.split(None, 1)
        res[name.rstrip(b'\r\n')] = int(size)
    return res


DeltaRow = namedtuple('DeltaRow', 'delta, path')


def gzip_open(filename):
    if filename.endswith('.gz'):
        return gzip.open(filename)
    else:
        return open(filename, 'rb')


def du_diff(f1, f2):
    with gzip_open(f1) as fp:
        du1 = parse_du(fp)
    with gzip_open(f2) as fp:
        du2 = parse_du(fp)
    diffs = dict((name, du2[name] - du1[name])
                 for name in set(du1) | set(du2))
    return [
        DeltaRow(delta, name.decode('UTF-8', 'replace'))
        for name, delta in sorted(diffs.items(), key=lambda t: t[1])
        if delta != 0
    ]


def format_du_diff(diff):
    return u'\n'.join(
        u"%+d\t%s" % (delta, name) for delta, name in diff
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Computes the differences between two disk usage files produced by du(1)."
            " Can read gzipped files transparently."
        )
    )
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('files', metavar='FILE', nargs=2,
                        help='files to compare (old, new)')
    args = parser.parse_args()
    report = format_du_diff(du_diff(*args.files)).encode('UTF-8') + b'\n'
    buffer = getattr(sys.stdout, 'buffer', sys.stdout)
    buffer.write(report)


if __name__ == '__main__':
    main()
