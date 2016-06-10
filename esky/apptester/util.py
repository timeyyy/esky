from future import standard_library
standard_library.install_aliases()

import os
import re
from distutils.version import StrictVersion as Version
from http.server import SimpleHTTPRequestHandler
from http.server import HTTPServer
import threading
from platform import system
from functools import cmp_to_key


if not hasattr(HTTPServer, "shutdown"):
    import socket

    def socketserver_shutdown(self):
        try:
            self.socket.close()
        except socket.error:
            pass

    HTTPServer.shutdown = socketserver_shutdown


def _zip_ver(string):
    '''
    returns the version from a zipfile
    '''
    ver = re.search(r'\s*([\d.]+)', string).group(1)
    if ver[-1] == '.':
        ver = ver[:-1]
    return ver

def _zip_sort_cmp(zfile1, zfile2):
    '''
    used to sort zipfiles with sorted function
    '''
    v1 = _zip_ver(zfile1)
    v2 = _zip_ver(zfile2)
    if Version(v1) > Version(v2):
        return 1
    elif Version(v1) == Version(v2):
        return 0
    else:
        return -1

def sort_zipfiles(files):
    return sorted(files, key=cmp_to_key(_zip_sort_cmp))

def start_server(port):
    '''start a server on port'''
    server = HTTPServer(("localhost", port),
                        SimpleHTTPRequestHandler)
    server_thread = threading.Thread(
                            target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()

def get_appdir(deploydir):
    # mac??
    if 'darwin' in system().lower():
        appdir = os.path.join(deploydir,
                              os.listdir(deploydir)[0])
    else:
        appdir = deploydir
    return appdir

def get_cmd(appdir, torun):
    if 'darwin' in system().lower():
        cmd = os.path.join(appdir,
                           "Contents",
                           "MacOS",
                           torun)
    elif 'linux' in system().lower():
        cmd = os.path.join(appdir, torun)
    else:
        cmd = os.path.join(appdir, torun+'.exe')
    return cmd

