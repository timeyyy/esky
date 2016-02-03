
'''

    esky.bdist_esky.f_util: utils required for freezing after

adding the future module as a dep. Not useful to end users
so kept out of the way here.
'''

from __future__ import with_statement
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from past.builtins import basestring
from builtins import *


import os
import sys
import shutil
import functools
import zipfile
import tempfile
import py_compile

from esky.util import PY3, extract_zipfile, create_zipfile

EXCLUDES_LIST = ('urllib.StringIO',
                 'urllib.UserDict',
                 'urllib.__builtin__',
                 'urllib.__future__',
                 'urllib.__main__',
                 'urllib._abcoll',
                 'urllib._collections',
                 'urllib._functools',
                 'urllib._hashlib',
                 'urllib._heapq',
                 'urllib._io',
                 'urllib._locale',
                 'urllib._md5',
                 'urllib._random',
                 'urllib._sha',
                 'urllib._sha256',
                 'urllib._sha512',
                 'urllib._socket',
                 'urllib._sre',
                 'urllib._ssl',
                 'urllib._struct',
                 'urllib._subprocess',
                 'urllib._threading_local',
                 'urllib._warnings',
                 'urllib._weakref',
                 'urllib._weakrefset',
                 'urllib._winreg',
                 'urllib.abc',
                 'urllib.array',
                 'urllib.base64',
                 'urllib.bdb',
                 'urllib.binascii',
                 'urllib.cPickle',
                 'urllib.cStringIO',
                 'urllib.calendar',
                 'urllib.cmd',
                 'urllib.collections',
                 'urllib.contextlib',
                 'urllib.copy',
                 'urllib.copy_reg',
                 'urllib.datetime',
                 'urllib.difflib',
                 'urllib.dis',
                 'urllib.doctest',
                 'urllib.dummy_thread',
                 'urllib.email',
                 'urllib.email.utils',
                 'urllib.encodings',
                 'urllib.encodings.aliases',
                 'urllib.errno',
                 'urllib.exceptions',
                 'urllib.fnmatch',
                 'urllib.ftplib',
                 'urllib.functools',
                 'urllib.gc',
                 'urllib.genericpath',
                 'urllib.getopt',
                 'urllib.getpass',
                 'urllib.gettext',
                 'urllib.hashlib',
                 'urllib.heapq',
                 'urllib.httplib',
                 'urllib.imp',
                 'urllib.inspect',
                 'urllib.io',
                 'urllib.itertools',
                 'urllib.keyword',
                 'urllib.linecache',
                 'urllib.locale',
                 'urllib.logging',
                 'urllib.marshal',
                 'urllib.math',
                 'urllib.mimetools',
                 'urllib.mimetypes',
                 'urllib.msvcrt',
                 'urllib.nt',
                 'urllib.ntpath',
                 'urllib.nturl2path',
                 'urllib.opcode',
                 'urllib.operator',
                 'urllib.optparse',
                 'urllib.os',
                 'urllib.os2emxpath',
                 'urllib.pdb',
                 'urllib.pickle',
                 'urllib.posixpath',
                 'urllib.pprint',
                 'urllib.quopri',
                 'urllib.random ',
                 'urllib.re',
                 'urllib.repr',
                 'urllib.rfc822',
                 'urllib.robotparser',
                 'urllib.select',
                 'urllib.shlex',
                 'urllib.signal',
                 'urllib.socket',
                 'urllib.sre_compile',
                 'urllib.sre_constants',
                 'urllib.sre_parse',
                 'urllib.ssl',
                 'urllib.stat',
                 'urllib.string',
                 'urllib.strop',
                 'urllib.struct',
                 'urllib.subprocess',
                 'urllib.sys',
                 'urllib.tempfile',
                 'urllib.textwrap',
                 'urllib.thread',
                 'urllib.threading',
                 'urllib.time',
                 'urllib.token',
                 'urllib.tokenize',
                 'urllib.traceback',
                 'urllib.types',
                 'urllib.unittest',
                 'urllib.unittest.case',
                 'urllib.unittest.loader',
                 'urllib.unittest.main',
                 'urllib.unittest.result',
                 'urllib.unittest.runner',
                 'urllib.unittest.signals',
                 'urllib.unittest.suite',
                 'urllib.unittest.util',
                 'urllib.urllib',
                 'urllib.urlparse',
                 'urllib.uu',
                 'urllib.warnings',
                 'urllib.weakref',
                 'collections.sys',
                 'collections.abc'
                 'collections.types'
                 'collections._weakrefset',
                 'collections._weakref')


INCLUDES_LIST = ('future', 'builtins')

ESKY_INCLUDES_LIST = ('UserList',
                      'UserString',
                      'commands',
                      )

INCLUDES_COND_3 = ("past", "builtins", "lib2to3", "past.builtins")

FUTURE_PACKAGES = ("future",
                   "future.builtins",
                   "future.types",
                   "future.standard_library",
                   "future.backports",
                   "future.backports.email",
                   "future.backports.email.mime",
                   "future.backports.html",
                   "future.backports.http",
                   "future.backports.test",
                   "future.backports.urllib",
                   "future.backports.xmlrpc",
                   "future.backports.misc",
                   "future.moves",
                   "future.moves.dbm",
                   "future.moves.html",
                   "future.moves.http",
                   "future.moves.test",
                   "future.moves.tkinter",
                   "future.moves.urllib",
                   "future.moves.xmlrpc",
                   "future.tests",
                   "future.utils",
                   "past",
                   "past.builtins",
                   "past.types",
                   "past.utils",
                   "past.translation",
                   "libfuturize",
                   "libfuturize.fixes",
                   "libpasteurize",
                   "libpasteurize.fixes",
                   )


def freeze_future(dist):
    '''Esky uses the futures library to work with python3 and 2,
    these settings are required to make the future module freeze properly'''

    if 'linux' in sys.platform:
        if not PY3:
            dist.excludes.extend(EXCLUDES_LIST)
            dist.includes.extend(ESKY_INCLUDES_LIST)
            dist.includes.extend(FUTURE_PACKAGES)

    elif sys.platform == 'win32':
        if not PY3:
            dist.includes.extend(ESKY_INCLUDES_LIST)


def preserve_cwd(function):
    '''Decorator used for keeping the original cwd after function call'''
    @functools.wraps(function)
    def decorator(*args, **kwargs):
        cwd = os.getcwd()
        try:
            return function(*args, **kwargs)
        finally:
            os.chdir(cwd)
    return decorator


def freeze_future_cxfreeze(dist_dir, **kwargs):
    '''
    copy our modules and sit them next to the library.zip, this works
    '''
    lib_path, zip_archive, broken_modules = _freeze_future(**kwargs)
    os.chdir(dist_dir)

    # Copy all modules in
    for module in broken_modules:
        shutil.copytree(os.path.join(lib_path, module.name),
                        os.path.join(os.getcwd(), module.name))
    # make pyc files?
    optimize = kwargs.get('optimize')
    if optimize not in ('0', 0):
        make_pyc(broken_modules)


def make_pyc(broken_modules):
    for module in broken_modules:
        for root, dirs, files in os.walk(os.path.join(os.getcwd(), module.name)):
            for file in files:
                if os.path.splitext(file)[-1] == '.py':
                    py_compile.compile(file, file + 'c')
                    os.remove(file)

def _freeze_future(**kwargs):
    '''
    returns
    path to python/lib/site-packages
    library zip name
    modules requiring fixes
    '''

    class Unnest(Exception):
        '''This is raised to exit out of a nested loop'''
        pass

    zip_archive = 'library.zip'

    broken_modules = (_lib2to3, )

    # locating the Lib folder path
    if os.name == 'nt':
        lib_path = os.path.join(sys.exec_prefix, 'Lib')
        assert os.path.exists(lib_path)
    elif 'linux' in sys.platform:
        try:
            for folder in sys.path:
                if folder:
                    try:
                        for file in os.listdir(folder):
                            for module in broken_modules:
                                if file == module.name:
                                    lib_path = folder
                                    raise Unnest
                    except OSError:
                        # In a virtualenv weird stuff gets put on the path sometimes
                        pass
        except Unnest:
            pass
        else:
            raise Exception('One of our required modules could not be found')

    return lib_path, zip_archive, broken_modules



class ToFix():
    '''
    defines all the data required to make fixes to broken_modules imports due to the issue described
    '''
    def __init__(self, name, datafiles, brokenfiles, fixes):
        '''
        :param name: name of the module
        :param datafiles: tuple of files that need to moved outside of the library.zip
        :param broken_modulesfiles: files that need to be modified by the fixes to work
        :param fixes: tuple of 2 elements - >
                                string to identify line to apply fixes to
                                function that takes the line and fixes it then returns it
        '''
        self.name = name
        self.datafiles = datafiles
        self.brokenfiles = brokenfiles
        self.fixes = fixes


def _lib2to3_fix(line):
    ''' simple callback to fix the lib2to3 code'''
    parts = line.split('os.path.dirname(__file__)')
    parts.insert(1, 'os.sep.join(i for i in os.path.abspath(__file__).split(os.sep)[:-3]), "lib2to3"')
    return ''.join(i for i in parts)


_lib2to3 = ToFix(name='lib2to3',
                 datafiles=('Grammar.txt', 'PatternGrammar.txt',),
                 brokenfiles=('pygram.py',),
                 fixes=(('_GRAMMAR_FILE', _lib2to3_fix,),
                        ('_PATTERN_GRAMMAR_FILE', _lib2to3_fix,),))

@preserve_cwd
def freeze_future_fix(dist_dir, freezer):
    '''
    if a library uses open() on a file that now is moved in our library.zip, it will fail
    we unzip the package data and library so that it now works,
    for cxfreeze we can just unzip the module and it works fine,
    py2exe requires us to patch the files...
    '''
    zip_archive_name = 'library.zip'
    class Unnest(Exception):
        '''This is raised to exit out of a nested loop'''
        pass

    class ToFix():
        '''
        defines all the data required to make fixes to broken_modules imports due to the issue described
        '''
        def __init__(self, name, datafiles, brokenfiles, fixes):
            '''
            :param name: name of the module
            :param datafiles: tuple of files that need to moved outside of the library.zip
            :param broken_modulesfiles: files that need to be modified by the fixes to work
            :param fixes: tuple of 2 elements - >
                                    string to identify line to apply fixes to
                                    function that takes the line and fixes it then returns it
            '''
            self.name = name
            self.datafiles = datafiles
            self.brokenfiles = brokenfiles
            self.fixes = fixes

    def _lib2to3_fix(line):
        ''' simple callback to fix the lib2to3 code'''
        parts = line.split('os.path.dirname(__file__)')
        parts.insert(1, 'os.sep.join(i for i in os.path.abspath(__file__).split(os.sep)[:-3]), "lib2to3"')
        return ''.join(i for i in parts)

    _lib2to3 = ToFix(name='lib2to3',
                     datafiles=('Grammar.txt', 'PatternGrammar.txt',),
                     brokenfiles=('pygram.py',),
                     fixes=(('_GRAMMAR_FILE', _lib2to3_fix,),
                            ('_PATTERN_GRAMMAR_FILE', _lib2to3_fix,),))

    broken_modules = (_lib2to3,)

    # locating the Lib folder path
    if os.name == 'nt':
        data_path = os.path.join(sys.exec_prefix, 'Lib')
        assert os.path.exists(data_path)
    elif 'linux' in sys.platform:
        try:
            for folder in sys.path:
                if folder:
                    try:
                        for file in os.listdir(folder):
                            for module in broken_modules:
                                if file == module.name:
                                    data_path = folder
                                    raise Unnest
                    except OSError:
                        # In a virtualenv weird stuff gets put on the path sometimes
                        pass
        except Unnest:
            pass
        else:
            raise Exception('One of our required modules could not be found')

    os.chdir(dist_dir)

    # extract our modules and sit them next to the library.zip This is enough for cxfreeze
    if freezer == 'cxfreeze':
        archive = zipfile.ZipFile(zip_archive_name)
        for file in archive.namelist():
            for bad_module in broken_modules:
                if file.startswith(bad_module.name + '/'):
                    archive.extract(file, os.getcwd())
        archive.close()

    # Copy over any data files as well ('more portable between freezers than using the setup options')
    for module in broken_modules:
        try:
            os.makedirs(module.name)
        except Exception:
            pass
        for data in module.datafiles:
            shutil.copy(
                    os.path.join(data_path, module.name, data),
                    os.path.join(module.name, data))

    # copy in the source of the files to fix, and patch them
    if freezer == 'py2exe':
        fixdir = tempfile.mkdtemp()
        for module in broken_modules:
            try:
                os.makedirs(os.path.join(fixdir, module.name))
            except Exception:
                pass
            for broken in module.brokenfiles:
                fixme = os.path.join(fixdir, module.name, broken)
                shutil.copy(os.path.join(data_path, module.name, broken), fixme)
                for fix in module.fixes:
                    make_open_work_on_zip(
                                        file=fixme,
                                        to_match=fix[0],
                                        fix=fix[1])
                make_pyc(zip_archive_name, file=fixme, match=module.name + '/' + broken)
        replace_files(zip_archive_name, fixdir)
        # shutil.rmtree(fixdir)

def make_open_work_on_zip(file, to_match, fix):
    # make the change to the file
    broken_file = InMemoryWriter(file, copy=True)
    for line in broken_file:
        if line.rstrip():
            if to_match in line:
                broken_file[broken_file.i - 1] = fix(line)
                break
    broken_file.save()

def make_pyc(zip_archive_name, file, match):
    # if the original file was a pyc make a pyc as well..
    with zipfile.ZipFile(zip_archive_name, 'r') as zipp:
        for zfile in zipp.namelist():
            if match in zfile:
                extension = os.path.splitext(zfile)[-1]
                if extension == '.pyc':
                    import py_compile
                    py_compile.compile(file, file + 'c')
                    os.remove(file)
                break

def replace_files(zip_archive_name, fixdir):
    # extract library
    tdir = tempfile.mkdtemp()
    extract_zipfile(zip_archive_name, tdir)
    os.remove(zip_archive_name)

    # replace with our edited file and rezip
    from distutils.dir_util import copy_tree
    copy_tree(fixdir, tdir)
    create_zipfile(tdir, zip_archive_name)

    # shutil.rmtree(tdir)


class InMemoryWriter(list, object):
    """
    simplify editing files

    On creation you can read all contents either from:
    an open file,
    a list
    a path/name to a file

    While iterating you can set copy=True to edit data
    as you iterate over it

    you can accesses the current position using self.i, useful if
    you are using filter or something like that while iterating
    """
    def __init__(self, insert_me=None, copy=False):
        list.__init__(self)
        self.copy = copy
        self.data = self
        if type(insert_me) == str:
            try:
                with open(insert_me, 'r') as file:
                    self.writelines(file)
                    self.original_filename = insert_me
            except FileNotFoundError as err:
                raise err
        elif insert_me:
            self.writelines(insert_me)
    def write(self, stuff):
        self.append(stuff)
    def writelines(self, passed_data):
        for item in passed_data:
            self.data.append(item)
    def __call__(self, copy=None):
        if copy:
            self.copy = True
        return self
    def __iter__(self):
        self.i=0
        if self.copy:
            self.data_copy = self.data[:]
        return self
    def __next__(self):
        if self.i+1 > len(self.data):
            try:
                del self.data_copy
            except AttributeError:
                pass
            raise StopIteration
        if not self.copy:
            requested = self.data[self.i]
        else:
            requested = self.data_copy[self.i]
        self.i+=1
        return requested
    def close(self):
        pass

    def readlines(self):
        return self.data

    def save(self, path=False):
        '''If you passed the filename as a str will default to that otherwise pass in a name'''
        if not path:
            path = self.original_filename
        with open(path, 'w') as file:
            for row in self.data:
                file.write(row)
