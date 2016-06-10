'''
Implements a tester which can be run against an esky executable
'''
from __future__ import print_function
from future import standard_library
standard_library.install_aliases()

import os
from os.path import splitext
import shutil
import tempfile
import re
from distutils.version import Version
import subprocess
import shlex
from contextlib import suppress

from esky.apptester.util import start_server, sort_zipfiles
from esky.apptester.util import get_appdir, get_cmd
from esky.util import extract_zipfile


class EskyAppTester():
    def __init__(self, zipdir, version_getter, torun, port=8000,
                 verbose=True):
        '''
        zipdir : path to patches/zips
        torun : name of the executable w/o file extension
        version_getter : function to return version of your app
                     the function runs after app exits
                     the function gets passed the executable path
        '''
        self.zipdir = zipdir
        self.version_getter = version_getter
        self.port = port
        self.torun = torun
        self.verbose = verbose

    def _assert_version_matches(self, version, executable):
        found = self.version_getter(executable)
        print('Looking :%s, found : %s' %(version, found))


    def test_all(self):
        pass

    def test_can_upgrade(self, params=None, only_latest=False):
        '''
        extracts a zip
        starts a local server serving up the next version
        start the app and let it update
        make sure app now starts in new version

        params : string that wil be shlexed and passed to
        your program
        '''
        server = None
        tdir = tempfile.mkdtemp()
        deploydir = os.path.join(tdir, 'deploy')
        uzdir = os.path.join(tdir, 'unzip')
        srvdir = os.path.join(tdir, 'server')

        if only_latest:
            raise Exception
        else:
            zfiles = (x for x in os.listdir(self.zipdir)
                            if splitext(x)[-1] == '.zip')
            pfiles = (x for x in os.listdir(self.zipdir)
                            if splitext(x)[-1] == '.patch')

        # Extract Zips in correct order
        zfiles_sorted = list(sort_zipfiles(zfiles))
        for i, zfile in enumerate(zfiles_sorted):
            source = os.path.join(self.zipdir, zfile)
            extract_zipfile(source, uzdir)
            # Setup next version in server directory
            with suppress(FileNotFoundError):
                shutil.rmtree(srvdir)
            os.mkdir(srvdir)
            try:
                next_ver = zfiles_sorted[i+1]
            except IndexError:
                break
            source = os.path.join(self.zipdir, next_ver)
            shutil.copy(source, srvdir)
            try:
                server = start_server(self.port)
            except Exception:
                raise
            else:
                # Setup app in its dir
                with suppress(FileNotFoundError):
                    shutil.rmtree(deploydir)
                shutil.copytree(uzdir, deploydir)
                # Run the app
                exe = get_cmd(get_appdir(deploydir), self.torun)
                if params:
                    cmd = [exe]
                    cmd.extend(shlex.split(params))
                else:
                    cmd = exe
                if self.verbose:
                    print('Spawning apptester!')
                proc = subprocess.Popen(cmd)
                if proc.wait():
                    if self.verbose:
                        print(proc.stdout)
                        print(proc.stderr)
                    assert False
                self._assert_version_matches(next_ver, exe)
            finally:
                if server:
                    server.shutdown()

        if i == 0 and self.verbose:
            print('Did not find enough zip or patches...')
                # Setup app in its dir
                # shutil.rmtree(deploydir)
                # os.mkdir(deploydir)
                # shutil.copytree(uzdir, deploydir)

                # TODO PATCHES
                # zip_ver = get_zip_ver(zfile)
                # for pfile, patch_ver in (pfile, get_patch_ver(x)
                                            # for x in patch_files):
                    # if zip_ver == patch_ver:
                    # patch_ver = ver



        #aply patchest



    def test_can_reach_server(self):
        pass

