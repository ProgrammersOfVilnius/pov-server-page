import random

from nose.tools import assert_equal

from update_server_page import Builder


def test_Builder_from_config_all_defaults():
    cp = Builder.ConfigParser()
    Builder.from_config(cp) # should not raise


def test_DiskUsage_files_to_keep():
    keep = Builder.DiskUsage.files_to_keep
    files = [
        '/var/www/example.com/du/var/du-2013-01-01.gz',
        '/var/www/example.com/du/var/du-2013-01-02.gz',
        '/var/www/example.com/du/var/du-2013-01-03.gz',
        '/var/www/example.com/du/var/du-2013-02-01.gz',
        '/var/www/example.com/du/var/du-2013-02-02.gz',
        '/var/www/example.com/du/var/du-2013-03-05.gz',
        '/var/www/example.com/du/var/du-2013-04-01.gz',
        '/var/www/example.com/du/var/du-2013-05-01.gz',
        '/var/www/example.com/du/var/du-2013-05-02.gz',
        '/var/www/example.com/du/var/du-2013-05-03.gz',
        '/var/www/example.com/du/var/du-2013-05-04.gz',
    ]
    random.shuffle(files)  # glob doesn't guarantee ordering
    kept = keep(files, keep_daily=0)
    assert_equal(kept, set([]))
    kept = keep(files, keep_daily=2)
    assert_equal(kept, set([
        '/var/www/example.com/du/var/du-2013-05-03.gz', # daily 2
        '/var/www/example.com/du/var/du-2013-05-04.gz', # daily 1
    ]))
    kept = keep(files, keep_monthly=3)
    assert_equal(kept, set([
        '/var/www/example.com/du/var/du-2013-03-05.gz', # monthly 3
        '/var/www/example.com/du/var/du-2013-04-01.gz', # monthly 2
        '/var/www/example.com/du/var/du-2013-05-01.gz', # monthly 1
    ]))
    kept = keep(files, keep_yearly=4)
    assert_equal(kept, set([
        '/var/www/example.com/du/var/du-2013-01-01.gz', # yearly 1
    ]))
    kept = keep(files, keep_daily=2, keep_monthly=3, keep_yearly=4)
    assert_equal(kept, set([
        '/var/www/example.com/du/var/du-2013-01-01.gz', # yearly 1
        '/var/www/example.com/du/var/du-2013-03-05.gz', # monthly 3
        '/var/www/example.com/du/var/du-2013-04-01.gz', # monthly 2
        '/var/www/example.com/du/var/du-2013-05-01.gz', # monthly 1
        '/var/www/example.com/du/var/du-2013-05-03.gz', # daily 2
        '/var/www/example.com/du/var/du-2013-05-04.gz', # daily 1
    ]))
    kept = keep(files, keep_daily=5, keep_monthly=5, keep_yearly=4)
    assert_equal(kept, set([
        '/var/www/example.com/du/var/du-2013-01-01.gz', # yearly 1, monthly 5
        '/var/www/example.com/du/var/du-2013-02-01.gz', # monthly 4
        '/var/www/example.com/du/var/du-2013-03-05.gz', # monthly 3
        '/var/www/example.com/du/var/du-2013-04-01.gz', # monthly 2, daily 5
        '/var/www/example.com/du/var/du-2013-05-01.gz', # monthly 1, daily 4
        '/var/www/example.com/du/var/du-2013-05-02.gz', # daily 3
        '/var/www/example.com/du/var/du-2013-05-03.gz', # daily 2
        '/var/www/example.com/du/var/du-2013-05-04.gz', # daily 1
    ]))
