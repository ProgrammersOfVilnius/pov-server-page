=======
du-diff
=======

--------------------------------
compare two disk usage snapshots
--------------------------------

:Author: Marius Gedminas <marius@gedmin.as>
:Date: 2016-09-21
:Version: 1.0
:Manual section: 1


SYNOPSIS
========

**du-diff** *file1* *file2*


DESCRIPTION
===========

**du-diff** compares two disk usage reports (in the format produced by
**du**\ (1)) and outputs the differences sorted by the delta size.

You can use it to find out areas of disk usage growth, if you have regular
disk usage snapshots.

**du-diff** transparently supports gzipped files.


EXAMPLES
========

``du /var | gzip > ~/du-$(date +%Y-%m-%d).gz``

    Take a gzipped disk usage snapshot with today's date in the filename.

``du /var > ~/du-current``

    Take another disk usage snapshot.

``du-diff ~/du-2013-08-01.gz ~/du-current``

    Compare the two snapshots


SEE ALSO
========

**du**\ (1)
