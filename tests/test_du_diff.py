import sys
import unittest
from io import BytesIO, TextIOWrapper

from pov_server_page.du_diff import parse_du, main


class TestParseDu(unittest.TestCase):

    def test_parse_du(self):
        self.assertEqual(parse_du(BytesIO(b'4\tfoo\n50\tbar\n\n')), {
            b'foo': 4,
            b'bar': 50,
        })


class TestMain(unittest.TestCase):

    def run_main(self, *args):
        orig_sys_argv = sys.argv
        orig_sys_stdout = sys.stdout
        try:
            sys.argv = ['du-diff'] + list(args)
            sys.stdout = self.stdout = TextIOWrapper(BytesIO())
            main()
        finally:
            sys.stdout = orig_sys_stdout
            sys.argv = orig_sys_argv

    def test_main(self):
        self.run_main('/dev/null', '/dev/null')
