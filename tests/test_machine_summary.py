from pov_server_page.machine_summary import (
    fmt_with_units, fmt_size_decimal, fmt_size_si, round_binary
)


def test_fmt_with_units():
    assert fmt_with_units(12.5, 'megs') == '12.5 megs'
    assert fmt_with_units(12.75, 'megs') == '12.8 megs'
    assert fmt_with_units(12.0, 'megs') == '12 megs'


def test_fmt_size_decimal():
    assert fmt_size_decimal(0) == '0 B'
    assert fmt_size_decimal(1) == '1 B'
    assert fmt_size_decimal(10) == '10 B'
    assert fmt_size_decimal(1000) == '1 KB'
    assert fmt_size_decimal(1200) == '1.2 KB'
    assert fmt_size_decimal(1200*10**3) == '1.2 MB'
    assert fmt_size_decimal(1200*10**6) == '1.2 GB'
    assert fmt_size_decimal(1200*10**9) == '1.2 TB'
    assert fmt_size_decimal(1200*10**12) == '1.2 PB'


def test_fmt_size_si():
    assert fmt_size_si(0) == '0 B'
    assert fmt_size_si(1) == '1 B'
    assert fmt_size_si(10) == '10 B'
    assert fmt_size_si(1024) == '1 KiB'
    assert fmt_size_si(1200) == '1.2 KiB'
    assert fmt_size_si(1200*1024) == '1.2 MiB'
    assert fmt_size_si(1200*1024**2) == '1.2 GiB'
    assert fmt_size_si(1200*1024**3) == '1.2 TiB'
    assert fmt_size_si(1200*1024**4) == '1.2 PiB'


def test_round_binary():
    # these are not very realistic corner cases
    assert round_binary(0) == 0
    assert round_binary(1) == 1
    assert round_binary(2) == 2
    # test cases from actual servers (MemTotal from /proc/meminfo)
    assert round_binary(61680 * 1024) == 64 * 1024**2
    assert round_binary(2061288 * 1024) == 2 * 1024**3
    assert round_binary(3096712 * 1024) == 3 * 1024**3
    assert round_binary(4040084 * 1024) == 4 * 1024**3
    assert round_binary(8061912 * 1024) == 8 * 1024**3
