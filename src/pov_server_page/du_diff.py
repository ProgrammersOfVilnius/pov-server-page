#!/usr/bin/python
"""
Usage: du-diff filename1 filename2

Computes the differences between two disk usage files (produced by du > filename).

Can read from gzipped files.
"""

import sys
import gzip
import optparse
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
    parser = optparse.OptionParser(
        'usage: %prog filename1 filename2',
        version=__version__,
        description="computes the differences between two disk usage files"
                    " (produced by du > filename; optionally also gzipped)")
    parser.add_option('-v', '--verbose', action='store_true')
    opts, args = parser.parse_args()
    try:
        f1, f2 = args
    except ValueError:
        sys.exit(__doc__.strip())
    print(format_du_diff(du_diff(f1, f2)))


if __name__ == '__main__':
    main()
