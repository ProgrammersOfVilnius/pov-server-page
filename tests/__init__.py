import importlib
import io
import os
from collections import namedtuple


NativeStringIO = io.BytesIO if str is bytes else io.StringIO


Directory = namedtuple('Directory', '')
Symlink = namedtuple('Symlink', 'destination')


class PatchMixin(object):

    maxDiff = None
    module_under_test = None

    def patch(self, what, mock):
        if '.' in what:
            modname, name = what.rsplit('.', 1)
            mod = importlib.import_module(modname)
        else:
            assert self.module_under_test is not None
            name = what
            mod = self.module_under_test
        try:
            orig_what = getattr(mod, name)
        except AttributeError:
            self.addCleanup(delattr, mod, name)
        else:
            self.addCleanup(setattr, mod, name, orig_what)
        setattr(mod, name, mock)

    def patch_files(self, files):
        if not hasattr(self, '_files'):
            self._files = {}
            self.patch('read_file', self._read_file)
            self.patch('open', self._open)
            self.patch('xml.etree.ElementTree.open', self._open)
            self.patch('os.path.exists', self._exists)
            self.patch('os.listdir', self._listdir)
            self.patch('os.path.islink', self._islink)
            self.patch('os.readlink', self._readlink)
        for fn, content in files.items():
            self._files[fn] = content
            dn = fn
            while True:
                dn = os.path.dirname(dn)
                if dn in self._files:
                    break
                self._files[dn] = Directory()

    def _read_file(self, filename):
        try:
            f = self._files[filename]
        except KeyError:
            raise IOError(2, 'File not found: %r' % filename)
        if isinstance(f, Symlink):
            return self._read_file(f.destination)
        if isinstance(f, Directory):
            raise IOError(21, 'Is a directory: %r' % filename)
        return self._files[filename]

    def _open(self, filename, mode='r'):
        assert mode in ('r', 'rb')
        if mode == 'r':
            return NativeStringIO(self._read_file(filename))
        else:
            return io.BytesIO(self._read_file(filename).encode('UTF-8'))

    def _exists(self, filename):
        # Ignoring the corner case of broken symlinks for now
        return filename in self._files

    def _listdir(self, dirname):
        if not self._exists(dirname):
            raise OSError(2, 'Directory not found: %r' % dirname)
        if not dirname.endswith('/'):
            dirname += '/'
        files = sorted(set(fn[len(dirname):].partition('/')[0]
                           for fn in self._files
                           if fn.startswith(dirname)))
        return files

    def _islink(self, filename):
        return isinstance(self._files.get(filename), Symlink)

    def _readlink(self, filename):
        try:
            f = self._files[filename]
        except KeyError:
            raise IOError(2, 'File not found: %r' % filename)
        if not isinstance(f, Symlink):
            raise IOError(22, 'Not a symlink: %r' % filename)
        return f.destination

    def patch_commands(self, commands):
        if hasattr(self, '_commands'):
            self._commands.update(commands)
        else:
            self._commands = commands
            self.patch('os.popen', self._popen)

    def _popen(self, command):
        try:
            return NativeStringIO(self._commands[command])
        except KeyError:
            raise IOError(2, 'Command not found: %r' % command)
