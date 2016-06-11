#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

Esky  - keep frozen apps fresh
==============================

Esky is an auto-update framework for frozen Python applications.  It provides
a simple API through which apps can find, fetch and install updates, and a
bootstrapping mechanism that keeps the app safe in the face of failed or
partial updates.

Esky is currently capable of freezing apps with py2exe, py2app and cxfreeze.
Adding support for other freezer programs should be straightforward;
patches will be gratefully accepted.

See https://github.com/cloudmatrix/esky/ for more information:

"""

from __future__ import absolute_import
from future import standard_library
standard_library.install_aliases()
from builtins import next, object
from past.builtins import basestring

__ver_major__ = 0
__ver_minor__ = 9
__ver_patch__ = 10
__ver_sub__ = "dev"
__ver_tuple__ = (__ver_major__, __ver_minor__, __ver_patch__, __ver_sub__)
__version__ = "%d.%d.%d%s" % __ver_tuple__


import sys
import errno
if sys.platform != "win32":
    import fcntl

from esky.errors import *
from esky.sudo import SudoProxy, has_root, allow_from_sudo
from esky.util import is_version_dir, appdir_from_executable
from esky.util import copy_ownership_info, ESKY_CONTROL_DIR
from esky.util import files_differ, lazy_import, ESKY_APPDATA_DIR
from esky.util import is_locked_version_dir, really_rmtree, really_rename
from esky.bootstrap import split_app_version, join_app_version, parse_version
from esky.bootstrap import is_uninstalled_version_dir, get_best_version
from esky.bootstrap import lock_version_dir, get_all_versions, is_installed_version_dir

#  Since all frozen apps are required to import this module and call the
#  run_startup_hooks() function, we use a simple lazy import mechanism to
#  make the initial import of this module as fast as possible.


@lazy_import
def os():
    import os
    return os


@lazy_import
def socket():
    import socket
    return socket


@lazy_import
def time():
    import time
    return time


@lazy_import
def subprocess():
    import subprocess
    return subprocess


@lazy_import
def atexit():
    import atexit
    return atexit


@lazy_import
def base64():
    import base64
    return base64


@lazy_import
def pickle():
    import pickle
    return pickle


@lazy_import
def threading():
    try:
        import threading
    except ImportError:
        threading = None
    return threading


@lazy_import
def apptester():
    import esky.apptester
    return apptester


@lazy_import
def esky():
    import esky
    import esky.finder
    import esky.fstransact
    if sys.platform == "win32":
        import esky.winres
    return esky


class Esky(object):
    """Class representing an updatable frozen app.

    Instances of this class point to a directory containing a frozen app in
    the esky format.  Through such an instance the app can be updated to a
    new version in-place.  Typical use of this class might be:

        if hasattr(sys,"frozen"):
            app = esky.Esky(sys.executable,"http://example.com/downloads/")
            app.auto_update()

    The first argument must be either the top-level application directory,
    or the path of an executable from that application.  The second argument
    is a VersionFinder object that will be used to search for updates.  If
    a string it passed, it is assumed to be a URL and is passed to a new
    DefaultVersionFinder instance.
    """

    lock_timeout = 60 * 60  # 1 hour timeout on appdir locks

    def __init__(self, appdir_or_exe, version_finder=None):
        self._init_from_appdir(appdir_or_exe)
        self._lock_count = 0
        self.sudo_proxy = None
        self.keep_sudo_proxy_alive = False
        self._old_sudo_proxies = []
        self.version_finder = version_finder
        self._update_dir = appdirs.site_data_dir(appdir_or_exe, appdir_or_exe)
        self.reinitialize()

    def _init_from_appdir(self, appdir_or_exe):
        """Extension point to override the initial logic of Esky initialisation.

        This method is expected to interrogate the given appdir and set up the
        basic properties of the esky (e.g. name, platform) in response.  It is
        split into its own method to make it easier to override in subclasses.
        """
        if os.path.isfile(appdir_or_exe):
            self.appdir = appdir_from_executable(appdir_or_exe)
            vsdir = self._get_versions_dir()
            vdir = appdir_or_exe[len(vsdir):].split(os.sep)[1]
            details = split_app_version(vdir)
            self.name, self.active_version, self.platform = details
        else:
            self.active_version = None
            self.appdir = appdir_or_exe
        self.appdir = os.path.abspath(self.appdir)

    def _get_version_finder(self):
        return self.__version_finder

    def _set_version_finder(self, version_finder):
        if version_finder is not None:
            if isinstance(version_finder, basestring):
                kwds = {"download_url": version_finder}
                version_finder = esky.finder.DefaultVersionFinder(**kwds)
        self.__version_finder = version_finder

    version_finder = property(_get_version_finder, _set_version_finder)

    def _get_update_dir(self):
        """Get the directory path in which self.version_finder can work."""
        return os.path.join(self._get_versions_dir(), self._update_dir)

    def _get_versions_dir(self):
        """Get the directory path containing individual version dirs."""
        if not ESKY_APPDATA_DIR:
            return self.appdir
        # TODO: remove compatability hooks for ESKY_APPDATA_DIR=""
        try:
            for nm in os.listdir(os.path.join(self.appdir, ESKY_APPDATA_DIR)):
                fullnm = os.path.join(self.appdir, ESKY_APPDATA_DIR, nm)
                if is_version_dir(fullnm) and is_installed_version_dir(fullnm):
                    return os.path.join(self.appdir, ESKY_APPDATA_DIR)
        except EnvironmentError:
            pass
        return self.appdir

    def get_abspath(self, relpath):
        """Get the absolute path of a file within the current version."""
        if self.active_version:
            v = join_app_version(self.name, self.active_version, self.platform)
        else:
            v = join_app_version(self.name, self.version, self.platform)
        # TODO: remove compatability hooks for ESKY_APPDATA_DIR=""
        if os.path.exists(os.path.join(self._get_versions_dir(), v)):
            return os.path.join(self._get_versions_dir(), v, relpath)
        return os.path.join(self.appdir, v, relpath)

    def reinitialize(self):
        """Reinitialize internal state by poking around in the app directory.

        If the app directory is found to be in an inconsistent state, a
        EskyBrokenError will be raised.  This should never happen unless
        another process has been messing with the files.
        """
        best_version = get_best_version(self._get_versions_dir())
        if best_version is None:
            raise EskyBrokenError("no frozen versions found")
        details = split_app_version(best_version)
        self.name, self.version, self.platform = details

    @allow_from_sudo()
    def lock(self, num_retries=0):
        """Lock the application directory for exclusive write access.

        If the appdir is already locked by another process/thread then
        EskyLockedError is raised.  There is no way to perform a blocking
        lock on an appdir.

        Locking is achieved by creating a "locked" directory and writing the
        current process/thread ID into it.  os.mkdir is atomic on all platforms
        that we care about.

        This also has the side-effect of failing early if the user does not
        have permission to modify the application directory.
        """
        if self.sudo_proxy is not None:
            return self.sudo_proxy.lock()
        if num_retries > 5:
            raise EskyLockedError
        if threading:
            curthread = threading.currentThread()
            try:
                threadid = curthread.ident
            except AttributeError:
                threadid = curthread.getName()
        else:
            threadid = "0"
        myid = "%s-%s-%s" % (socket.gethostname(), os.getpid(), threadid)
        lockdir = os.path.join(self.appdir, "locked")
        #  Do I already own the lock?
        if os.path.exists(os.path.join(lockdir, myid)):
            #  Update file mtime to keep it safe from breakers
            os.utime(os.path.join(lockdir, myid), None)
            self._lock_count += 1
            return True
        #  Try to make the "locked" directory.
        try:
            os.mkdir(lockdir)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
            #  Is it stale?  If so, break it and try again.
            try:
                newest_mtime = os.path.getmtime(lockdir)
                for nm in os.listdir(lockdir):
                    mtime = os.path.getmtime(os.path.join(lockdir, nm))
                    if mtime > newest_mtime:
                        newest_mtime = mtime
                if newest_mtime + self.lock_timeout < time.time():
                    really_rmtree(lockdir)
                    return self.lock(num_retries + 1)
                else:
                    raise EskyLockedError
            except OSError as e:
                if e.errno not in (errno.ENOENT, errno.ENOTDIR, ):
                    raise
                return self.lock(num_retries + 1)
        else:
            #  Success!  Record my ownership
            open(os.path.join(lockdir, myid), "wb").close()
            self._lock_count = 1
            return True

    @allow_from_sudo()
    def unlock(self):
        """Unlock the application directory for exclusive write access."""
        if self.sudo_proxy is not None:
            return self.sudo_proxy.unlock()
        self._lock_count -= 1
        if self._lock_count == 0:
            if threading:
                curthread = threading.currentThread()
                try:
                    threadid = curthread.ident
                except AttributeError:
                    threadid = curthread.getName()
            else:
                threadid = "0"
            myid = "%s-%s-%s" % (socket.gethostname(), os.getpid(), threadid)
            lockdir = os.path.join(self.appdir, "locked")
            os.unlink(os.path.join(lockdir, myid))
            os.rmdir(lockdir)

    @allow_from_sudo()
    def has_root(self):
        """Check whether the user currently has root/administrator access."""
        if self.sudo_proxy is not None:
            return self.sudo_proxy.has_root()
        return has_root()

    def get_root(self):
        """Attempt to gain root/administrator access by spawning helper app."""
        if self.has_root():
            return True
        self.sudo_proxy = SudoProxy(self)
        self.sudo_proxy.start()
        if not self.sudo_proxy.has_root():
            raise OSError(None, "could not escalate to root privileges")

    def drop_root(self):
        """Drop root privileges by killing the helper app."""
        if self.sudo_proxy is not None:
            self.sudo_proxy.close()
            if self.keep_sudo_proxy_alive:
                self._old_sudo_proxies.append(self.sudo_proxy)
            else:
                self.sudo_proxy.terminate()
            self.sudo_proxy = None

    @allow_from_sudo()
    def cleanup(self):
        """Perform cleanup tasks in the app directory.

        This includes removing older versions of the app and completing any
        failed update attempts.  Such maintenance is not done automatically
        since it can take a non-negligible amount of time.

        If the cleanup proceeds sucessfully this method will return True; it
        there is work that cannot currently be completed, it returns False.
        """
        if self.sudo_proxy is not None:
            return self.sudo_proxy.cleanup()
        if not self.needs_cleanup():
            return True
        self.lock()
        try:
            #  This is a little coroutine trampoline that executes each
            #  action yielded from self._cleanup_actions().  Any exceptions
            #  that the action raises are thrown back into the generator.
            #  The result of each is and-ed into the success code.
            #
            #  If you're looking for the actual logic of the cleanup process,
            #  it's all in the _cleanup_actions() method.
            success = True
            actions = self._cleanup_actions()
            try:
                act = lambda: True
                while True:
                    try:
                        if callable(act):
                            res = act()
                        elif len(act) == 1:
                            res = act[0]()
                        elif len(act) == 2:
                            res = act[0](*act[1])
                        else:
                            res = act[0](*act[1], **act[2])
                        if res is not None:
                            success &= res
                    except Exception:
                        act = actions.throw(*sys.exc_info())
                    else:
                        act = next(actions)
            except StopIteration:
                return success
        finally:
            self.unlock()

    def needs_cleanup(self):
        """Check whether a call to cleanup() is necessary.

        This method checks whether a call to the cleanup() method will have
        any work to do, without obtaining a lock on the esky's appdir.  You
        might like to use this to avoid locking the appdir (which may require
        elevating to root) when there's nothing to do.
        """
        for act in self._cleanup_actions():
            return True
        return False

    def _cleanup_actions(self):
        """Iterator giving (func,args,kwds) tuples of cleanup actions.

        This encapsulates the logic of the "cleanup" method without actually
        performing any of the actions, making it easy to check whether cleanup
        is required without duplicating the logic.
        """
        appdir = self.appdir
        vsdir = self._get_versions_dir()
        best_version = get_best_version(vsdir)
        new_version = get_best_version(vsdir, include_partial_installs=True)
        #  If there's a partial install we must complete it, since it
        #  could have left exes in the bootstrap env and we don't want
        #  to accidentally delete their dependencies.
        if best_version != new_version:
            (_, v, _) = split_app_version(new_version)
            yield (self.install_version, (v, ))
            best_version = new_version
        #  TODO: remove compatability hooks for ESKY_APPDATA_DIR=""
        if vsdir == appdir and ESKY_APPDATA_DIR:
            appdatadir = os.path.join(appdir, ESKY_APPDATA_DIR)
            if os.path.isdir(appdatadir) and os.listdir(appdatadir):
                new_version = get_best_version(appdatadir,
                                               include_partial_installs=True)
                if best_version != new_version:
                    (_, v, _) = split_app_version(new_version)
                    yield (self.install_version, (v, ))
                    best_version = new_version
        #  Now we can safely remove all the old versions.
        #  We except the currently-executing version, and silently
        #  ignore any locked versions.
        manifest = self._version_manifest(best_version)
        manifest.add(self._update_dir)
        manifest.add("locked")
        manifest.add(best_version)
        if self.active_version:
            if self.active_version != split_app_version(best_version)[1]:
                yield lambda: False
            manifest.add(self.active_version)
        # TODO: remove compatability hooks for ESKY_APPDATA_DIR=""
        for tdir in (appdir, vsdir):
            for nm in os.listdir(tdir):
                if nm not in manifest:
                    fullnm = os.path.join(tdir, nm)
                    if ".old." in nm or nm.endswith(".old"):
                        #  It's a temporary backup file; remove it.
                        yield (self._try_remove, (tdir, nm, manifest, ))
                    elif not os.path.isdir(fullnm):
                        #  It's an unaccounted-for file in the bootstrap env.
                        #  Leave it alone.
                        pass
                    elif is_version_dir(fullnm):
                        #  It's an installed-but-obsolete version.  Properly
                        #  uninstall it so it will clean up the bootstrap env.
                        (_, v, _) = split_app_version(nm)
                        try:
                            yield (self.uninstall_version, (v, ))
                        except VersionLockedError:
                            yield lambda: False
                        else:
                            yield (self._try_remove, (tdir, nm, manifest, ))
                    elif is_uninstalled_version_dir(fullnm):
                        # It's a partially-removed version; finish removing it.
                        yield (self._try_remove, (tdir, nm, manifest, ))
                    else:
                        for (_, _, filenms) in os.walk(fullnm):
                            if filenms:
                                #  It contains unaccounted-for files in the
                                #  bootstrap env. Can't prove it's safe to
                                #  remove, so leave it alone.
                                break
                        else:
                            #  It's an empty directory structure, remove it.
                            yield (self._try_remove, (tdir, nm, manifest, ))
        #  If there are pending overwrites, try to do them.
        ovrdir = os.path.join(vsdir, best_version, ESKY_CONTROL_DIR,
                              "overwrite")
        if os.path.exists(ovrdir):
            try:
                for (dirnm, _, filenms) in os.walk(ovrdir, topdown=False):
                    for nm in filenms:
                        ovrsrc = os.path.join(dirnm, nm)
                        ovrdst = os.path.join(appdir, ovrsrc[len(ovrdir) + 1:])
                        yield (self._overwrite, (ovrsrc, ovrdst, ))
                        yield (os.unlink, (ovrsrc, ))
                    yield (os.rmdir, (dirnm, ))
            except EnvironmentError:
                yield lambda: False
        #  Get the VersionFinder to clean up after itself
        if self.version_finder is not None:
            if self.version_finder.needs_cleanup(self):
                yield (self.version_finder.cleanup, (self, ))

    def _overwrite(self, src, dst):
        """Directly overwrite file 'dst' with the contents of file 'src'."""
        with open(src, "rb") as fIn:
            with open(dst, "ab") as fOut:
                fOut.seek(0)
                chunk = fIn.read(512 * 16)
                while chunk:
                    fOut.write(chunk)
                    chunk = fIn.read(512 * 16)

    @allow_from_sudo()
    def cleanup_at_exit(self):
        """Arrange for cleanup to occur after application exit.

        This operates by using the atexit module to spawn a new instance of
        this app, with appropriate flags that cause it to launch directly into
        the cleanup process.

        Recall that sys.executable points to a specific version dir, so this
        new process will not hold any filesystem locks in the main app dir.
        """
        if self.sudo_proxy is not None:
            self.keep_sudo_proxy_alive = True
            return self.sudo_proxy.cleanup_at_exit()
        if not getattr(sys, "frozen", False):
            exe = [sys.executable, "-c",
                   "import esky; esky.run_startup_hooks()",
                   "--esky-spawn-cleanup"]
        else:
            exe = sys.executable
            #  Try to re-launch the best available version, so that
            #  the currently in-use version can be cleaned up.
            if self.active_version is not None:
                vsdir = self._get_versions_dir()
                bestver = get_best_version(vsdir,
                                           include_partial_installs=True)
                if bestver is not None:
                    (_, version, _) = split_app_version(bestver)
                    if self.active_version != version:
                        if self.active_version in exe:
                            exe = exe.replace(self.active_version, version)
                            if not os.path.isfile(exe):
                                exe = sys.executable
            if os.path.basename(exe).lower() in ("python", "pythonw"):
                exe = [exe, "-c", "import esky; esky.run_startup_hooks()",
                       "--esky-spawn-cleanup"]
            else:
                if not _startup_hooks_were_run:
                    raise OSError(None,
                                  "unable to cleanup: startup hooks not run")
                exe = [exe, "--esky-spawn-cleanup"]
        appdata = pickle.dumps(self, pickle.HIGHEST_PROTOCOL)
        exe = exe + [base64.b64encode(appdata).decode("ascii")]

        @atexit.register
        def spawn_cleanup():
            rnul = open(os.devnull, "r")
            wnul = open(os.devnull, "w")
            if sys.platform == "win32":
                if sys.hexversion >= 0x02060000:
                    kwds = dict(close_fds=True)
                else:
                    kwds = {}
            else:
                kwds = dict(stdin=rnul,
                            stdout=wnul,
                            stderr=wnul,
                            close_fds=True)
            subprocess.Popen(exe, **kwds)

    def _try_remove(self, tdir, path, manifest=[]):
        """Try to remove the file/directory at given path in the target dir.

        This method attempts to remove the file or directory at the given path,
        but will fail silently under a number of conditions:

            * if a file is locked or permission is denied
            * if a directory cannot be emptied of all contents
            * if the path appears on sys.path
            * if the path appears in the given manifest

        """
        fullpath = os.path.join(tdir, path)
        if fullpath in sys.path:
            return False
        if path in manifest:
            return False
        try:
            if os.path.isdir(fullpath):
                #  Remove paths starting with "esky" last, since we use
                #  these to maintain state information.
                esky_paths = []
                success = True
                for nm in os.listdir(fullpath):
                    if nm == "esky" or nm.startswith("esky-"):
                        esky_paths.append(nm)
                    else:
                        subdir = os.path.join(path, nm)
                        success &= self._try_remove(tdir, subdir, manifest)
                if not success:
                    return False
                for nm in sorted(esky_paths):
                    self._try_remove(tdir, os.path.join(path, nm), manifest)
                os.rmdir(fullpath)
            else:
                os.unlink(fullpath)
        except EnvironmentError as e:
            if e.errno not in self._errors_to_ignore:
                raise
            return False
        else:
            return True

    _errors_to_ignore = (errno.ENOENT,
                         errno.EPERM,
                         errno.EACCES,
                         errno.ENOTDIR,
                         errno.EISDIR,
                         errno.EINVAL,
                         errno.ENOTEMPTY, )

    def auto_update(self, callback=None):
        """Automatically install the latest version of the app.

        This method automatically performs the following sequence of actions,
        escalating to root privileges if a permission error is encountered:

            * find the latest version [self.find_update()]
            * fetch the new version [self.fetch_version()]
            * install the new version [self.install_version()]
            * attempt to uninstall the old version [self.uninstall_version()]
            * reinitialize internal state [self.reinitialize()]
            * clean up the appdir [self.cleanup()]

        This method is mostly here to help you get started.  For an app of
        any serious complexity, you will probably want to build your own
        variant that e.g. operates in a background thread, prompts the user
        for confirmation, etc.
        """
        if self.version_finder is None:
            raise NoVersionFinderError
        if callback is None:
            callback = lambda *args: True
        got_root = False
        cleaned = False
        try:
            callback({"status": "searching"})
            version = self.find_update()
            if version is not None:
                callback({"status": "found", "new_version": version})
                #  Try to install the new version.  If it fails with
                #  a permission error, escalate to root and try again.
                try:
                    self._do_auto_update(version, callback)
                except EnvironmentError:
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    if exc_value.errno != errno.EACCES or self.has_root():
                        raise
                    try:
                        self.get_root()
                    except Exception:
                        raise exc_type(exc_value).with_traceback(exc_traceback)
                    else:
                        got_root = True
                        self._do_auto_update(version, callback)
                self.reinitialize()
            #  Try to clean up the app dir.  If it fails with a
            #  permission error, escalate to root and try again.
            try:
                callback({"status": "cleaning up"})
                cleaned = self.cleanup()
            except EnvironmentError:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                if exc_value.errno != errno.EACCES or self.has_root():
                    raise
                try:
                    self.get_root()
                except Exception:
                    raise exc_type(exc_value).with_traceback(exc_traceback)
                else:
                    got_root = True
                    callback({"status": "cleaning up"})
                    cleaned = self.cleanup()
        except Exception as e:
            callback({"status": "error", "exception": e})
            raise
        else:
            callback({"status": "done"})
        finally:
            #  Drop root privileges as soon as possible.
            if not cleaned and self.needs_cleanup():
                self.cleanup_at_exit()
            if got_root:
                self.drop_root()

    def _do_auto_update(self, version, callback):
        """Actual sequence of operations for auto-update.

        This is a separate method so it can easily be retried after gaining
        root privileges.
        """
        self.fetch_version(version, callback)
        callback({"status": "installing", "new_version": version})
        self.install_version(version)
        try:
            self.uninstall_version(self.version)
        except VersionLockedError:
            pass

    def find_update(self):
        """Check for an available update to this app.

        This method returns either None, or a string giving the version of
        the newest available update.
        """
        if self.version_finder is None:
            raise NoVersionFinderError
        best_version = None
        best_version_p = parse_version(self.version)
        for version in self.version_finder.find_versions(self):
            version_p = parse_version(version)
            if version_p > best_version_p:
                best_version_p = version_p
                best_version = version
        return best_version

    def fetch_version(self, version, callback=None):
        """Fetch the specified updated version of the app."""
        if self.sudo_proxy is not None:
            for status in self.sudo_proxy.fetch_version_iter(version):
                if callback is not None:
                    callback(status)
            return self.version_finder.has_version(self, version)
        if self.version_finder is None:
            raise NoVersionFinderError
        #  Guard against malicious input (might be called with root privs)
        vsdir = self._get_versions_dir()
        target = join_app_version(self.name, version, self.platform)
        target = os.path.join(vsdir, target)
        assert os.path.dirname(target) == vsdir
        #  Get the new version using the VersionFinder
        loc = self.version_finder.has_version(self, version)
        if not loc:
            loc = self.version_finder.fetch_version(self, version, callback)
        #  Adjust permissions to match the current version
        vdir = join_app_version(self.name, self.version, self.platform)
        copy_ownership_info(os.path.join(vsdir, vdir), loc)
        return loc

    @allow_from_sudo(str, iterator=True)
    def fetch_version_iter(self, version):
        """Fetch specified version of the app, with iterator control flow."""
        if self.sudo_proxy is not None:
            for status in self.sudo_proxy.fetch_version_iter(version):
                yield status
            return
        if self.version_finder is None:
            raise NoVersionFinderError
        #  Guard against malicious input (might be called with root privs)
        vsdir = self._get_versions_dir()
        target = join_app_version(self.name, version, self.platform)
        target = os.path.join(vsdir, target)
        assert os.path.dirname(target) == vsdir
        #  Get the new version using the VersionFinder
        loc = self.version_finder.has_version(self, version)
        if not loc:
            for status in self.version_finder.fetch_version_iter(self,
                                                                 version):
                if status["status"] != "ready":
                    yield status
                else:
                    loc = status["path"]
        #  Adjust permissions to match the current version
        vdir = join_app_version(self.name, self.version, self.platform)
        copy_ownership_info(os.path.join(vsdir, vdir), loc)
        yield {"status": "ready", "path": loc}

    @allow_from_sudo(str)
    def install_version(self, version):
        """Install the specified version of the app.

        This fetches the specified version if necessary, then makes it
        available as a version directory inside the app directory.  It
        does not modify any other installed versions.
        """
        if self.sudo_proxy is not None:
            return self.sudo_proxy.install_version(version)
        #  Extract update then rename into position in main app directory
        vsdir = self._get_versions_dir()
        target = join_app_version(self.name, version, self.platform)
        target = os.path.join(vsdir, target)
        #  Guard against malicious input (might be called with root privs)
        assert os.path.dirname(target) == vsdir
        if not os.path.exists(target):
            self.fetch_version(version)
            source = self.version_finder.has_version(self, version)
        #  TODO: remove compatability hooks for ESKY_APPDATA_DIR="".
        #  This is our chance to migrate to the new appdata dir layout,
        #  by installing into it.
        if vsdir == self.appdir and ESKY_APPDATA_DIR:
            vsdir = os.path.join(self.appdir, ESKY_APPDATA_DIR)
            try:
                os.mkdir(vsdir)
            except EnvironmentError as e:
                if e.errno not in (errno.EEXIST, ):
                    raise
            else:
                copy_ownership_info(self.appdir, vsdir)
            target = os.path.join(vsdir, os.path.basename(target))
        self.lock()
        try:
            if not os.path.exists(target):
                really_rename(source, target)
            trn = esky.fstransact.FSTransaction(self.appdir)
            try:
                self._unpack_bootstrap_env(target, trn)
            except Exception:
                trn.abort()
                raise
            else:
                trn.commit()
        finally:
            self.unlock()

    def _unpack_bootstrap_env(self, target, trn):
        """Unpack the bootstrap env from the given target directory."""
        vdir = os.path.basename(target)
        #  Move new bootrapping environment into main app dir.
        #  Be sure to move dependencies before executables.
        bootstrap = os.path.join(target, ESKY_CONTROL_DIR, "bootstrap")
        for nm in self._version_manifest(vdir):
            bssrc = os.path.join(bootstrap, nm)
            bsdst = os.path.join(self.appdir, nm)
            if os.path.exists(bssrc):
                #  On windows we can't atomically replace files.
                #  If they differ in a "safe" way we put them aside
                #  to overwrite at a later time.
                if sys.platform == "win32" and os.path.exists(bsdst):
                    if not files_differ(bssrc, bsdst):
                        trn.remove(bssrc)
                    elif esky.winres.is_safe_to_overwrite(bssrc, bsdst):
                        ovrdir = os.path.join(target, ESKY_CONTROL_DIR)
                        ovrdir = os.path.join(ovrdir, "overwrite")
                        if not os.path.exists(ovrdir):
                            os.mkdir(ovrdir)
                        trn.move(bssrc, os.path.join(ovrdir, nm))
                    else:
                        trn.move(bssrc, bsdst)
                else:
                    trn.move(bssrc, bsdst)
            if os.path.isdir(os.path.dirname(bssrc)):
                if not os.listdir(os.path.dirname(bssrc)):
                    trn.remove(os.path.dirname(bssrc))
        #  Remove the bootstrap dir; the new version is now installed
        trn.remove(bootstrap)

    @allow_from_sudo(str)
    def uninstall_version(self, version):
        """Uninstall the specified version of the app."""
        if self.sudo_proxy is not None:
            return self.sudo_proxy.uninstall_version(version)
        vsdir = self._get_versions_dir()
        target_name = join_app_version(self.name, version, self.platform)
        target = os.path.join(vsdir, target_name)
        #  Guard against malicious input (might be called with root privs)
        assert os.path.dirname(target) == vsdir
        #  TODO: remove compatability hooks for ESKY_APPDATA_DIR="".
        if ESKY_APPDATA_DIR and not os.path.exists(target):
            if vsdir == self.appdir:
                target = os.path.join(self.appdir, ESKY_APPDATA_DIR,
                                      target_name)
            else:
                target = os.path.join(self.appdir, target_name)
        lockfile = os.path.join(target, ESKY_CONTROL_DIR, "lockfile.txt")
        bsfile = os.path.join(target, ESKY_CONTROL_DIR,
                              "bootstrap-manifest.txt")
        bsfile_old = os.path.join(target, ESKY_CONTROL_DIR,
                                  "bootstrap-manifest-old.txt")
        self.lock()
        try:
            if not os.path.exists(target):
                return
            #  Clean up the bootstrapping environment in a transaction.
            #  This might fail on windows if the version is locked.
            try:
                trn = esky.fstransact.FSTransaction(self.appdir)
                try:
                    self._cleanup_bootstrap_env(version, trn)
                except Exception:
                    trn.abort()
                    raise
                else:
                    trn.commit()
            except EnvironmentError:
                if is_locked_version_dir(target):
                    raise VersionLockedError("version in use: %s" %
                                             (version, ))
                raise
            #  Disable the version by renaming its bootstrap-manifest.txt file.
            #  To avoid clobbering in-use version, respect locks on this file.
            if sys.platform == "win32":
                try:
                    really_rename(bsfile, bsfile_old)
                except EnvironmentError:
                    raise VersionLockedError("version in use: %s" %
                                             (version, ))
            else:
                try:
                    f = open(lockfile, "r")
                except EnvironmentError as e:
                    if e.errno != errno.ENOENT:
                        raise
                else:
                    try:
                        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except EnvironmentError as e:
                        if e.errno not in (errno.EACCES, errno.EAGAIN, ):
                            raise
                        msg = "version in use: %s" % (version, )
                        raise VersionLockedError(msg)
                    else:
                        really_rename(bsfile, bsfile_old)
                    finally:
                        f.close()
        finally:
            self.unlock()

    def _cleanup_bootstrap_env(self, version, trn):
        """Cleanup the bootstrap env populated by the given version."""
        target_name = join_app_version(self.name, version, self.platform)
        #  Get set of all files that must stay in the main appdir
        to_keep = set()
        for vname in os.listdir(self._get_versions_dir()):
            if vname == target_name:
                continue
            details = split_app_version(vname)
            if details[0] != self.name:
                continue
            if parse_version(details[1]) < parse_version(version):
                continue
            to_keep.update(self._version_manifest(vname))
        #  Remove files used only by the version being removed
        to_rem = self._version_manifest(target_name) - to_keep
        for nm in to_rem:
            fullnm = os.path.join(self.appdir, nm)
            if os.path.exists(fullnm):
                trn.remove(fullnm)
            if os.path.isdir(os.path.dirname(fullnm)):
                if not os.listdir(os.path.dirname(fullnm)):
                    trn.remove(os.path.dirname(fullnm))

    def _version_manifest(self, vdir):
        """Get the bootstrap manifest for the given version directory.

        This is the set of files/directories that the given version expects
        to be in the main app directory.
        """
        vsdir = self._get_versions_dir()
        mpath = os.path.join(vsdir, vdir, ESKY_CONTROL_DIR)
        mpath = os.path.join(mpath, "bootstrap-manifest.txt")
        #  TODO: remove compatability hooks for ESKY_APPDATA_DIR="".
        if not os.path.exists(mpath):
            if vsdir == self.appdir:
                mpath = os.path.join(self.appdir, ESKY_APPDATA_DIR, vdir,
                                     ESKY_CONTROL_DIR)
            else:
                mpath = os.path.join(self.appdir, vdir, ESKY_CONTROL_DIR)
            mpath = os.path.join(mpath, "bootstrap-manifest.txt")
        manifest = set()
        try:
            with open(mpath, "rt") as mf:
                for ln in mf:
                    #  Guard against malicious input, since we might try
                    #  to manipulate these files with root privs.
                    nm = os.path.normpath(ln.strip())
                    assert not os.path.isabs(nm)
                    assert not nm.startswith("..")
                    manifest.add(nm)
        except IOError:
            pass
        return manifest


_startup_hooks_were_run = False


def run_startup_hooks():
    global _startup_hooks_were_run
    _startup_hooks_were_run = True
    # Lock the version dir while we're executing, so other instances don't
    # delete files out from under us.
    if getattr(sys, "frozen", False):
        appdir = appdir_from_executable(sys.executable)
        # TODO: remove ESKY_APPDATA_DIR="" compatability hooks
        if ESKY_APPDATA_DIR:
            vdir = os.sep.join(sys.executable[len(appdir):].split(os.sep)[1:3])
            vdir = os.path.join(appdir, vdir)
            if not is_version_dir(vdir):
                vdir = sys.executable[len(appdir):].split(os.sep)[1]
                vdir = os.path.join(appdir, vdir)
        else:
            vdir = sys.executable[len(appdir):].split(os.sep)[1]
            vdir = os.path.join(appdir, vdir)
            if not is_version_dir(vdir):
                vdir = os.sep.join(sys.executable[
                    len(appdir):].split(os.sep)[
                        1:3])
                vdir = os.path.join(appdir, vdir)
        lock_version_dir(vdir)
    # Run the "spawn-cleanup" hook if given.
    if len(sys.argv) > 1 and sys.argv[1] == "--esky-spawn-cleanup":
        app = pickle.loads(base64.b64decode(sys.argv[2].encode("ascii")))
        time.sleep(1)
        app.cleanup()
        sys.exit(0)
    # Let esky.slaveproc run its hooks.
    import esky.slaveproc
    esky.slaveproc.run_startup_hooks()
    # Let esky.sudo run its hooks.
    import esky.sudo
    esky.sudo.run_startup_hooks()
