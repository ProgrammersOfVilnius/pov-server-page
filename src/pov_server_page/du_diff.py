#!/usr/bin/python
"""
Usage: du-diff filename1 filename2

Computes the differences between two disk usage files (produced by du > filename).

Can read from gzipped files.
"""

import sys
import gzip
import optparse
from collections import defaultdict


__version__ = '1.0'
__author__ = 'Marius Gedminas <marius@gedmin.as>'


def parse_du(stream):
    res = defaultdict(int)
    for line in stream:
        if not line.strip():
            continue
        size, name = line.split(None, 1)
        res[name.rstrip('\r\n')] = int(size)
    return res


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
    du1 = parse_du(gzip.open(f1))
    du2 = parse_du(gzip.open(f2))
    diffs = dict((name, du2[name] - du1[name])
                 for name in set(du1) | set(du2))
    for name, delta in sorted(diffs.items(), key=lambda t: t[1]):
        if delta != 0:
            print("%+d\t%s" % (delta, name))

if __name__ == '__main__':
    main()
