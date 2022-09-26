# -*- coding: utf-8 -*-
import fnmatch
import glob
import os
import re
import sys

import crossplane

try:
    from os import scandir, walk
except ImportError:
    from scandir import scandir, walk

from amplify.agent.common.context import context

__author__ = 'Arie van Luttikhuizen'
__copyright__ = 'Copyright (C) Nginx, Inc. All rights reserved.'
__license__ = ''
__maintainer__ = 'Arie van Luttikhuizen'
__email__ = 'arie@nginx.com'

# these regular expressions are used for light-weight parsing
INCLUDE_ONLY_RE = re.compile(r'(?:^|[;{}])\s*(include)\s+([\'"]?)([^#]*?)\2\s*?(?=;)')
INCLUDE_CERT_RE = re.compile(r'(?:^|[;{}])\s*(include|ssl_certificate)\s+([\'"]?)([^#]*?)\2\s*?(?=;)')

IGNORED_DIRECTIVES = [] if context.agent_name == 'controller' else frozenset([
    'ssl_certificate_key',
    'ssl_client_certificate',
    'ssl_password_file',
    'ssl_stapling_file',
    'ssl_trusted_certificate',
    'auth_basic_user_file',
    'secure_link_secret'
])


def get_filesystem_info(path):
    size, mtime, permissions = 0, 0, '0000'
    try:
        info = os.stat(path)
        size = info.st_size
        mtime = int(info.st_mtime)
        permissions = oct(info.st_mode & 0o0777).zfill(4)
    except Exception as e:
        exc_cls = e.__class__.__name__
        message = 'failed to stat %s do to %s' % (path, exc_cls)
        context.log.debug(message, exc_info=True)
    finally:
        return {'size': size, 'mtime': mtime, 'permissions': permissions}


def _fnmatch_pattern(names, pttn):
    if glob.has_magic(pttn):
        return fnmatch.filter(names, pttn)
    else:
        return [pttn] if pttn in names else []


def _iglob_pattern(pattern):
    if glob.has_magic(pattern):
        for path in glob.iglob(pattern):
            yield path
    else:
        yield pattern


def _getline(filename, lineno):
    with open(filename, encoding='utf-8', errors='replace') as fp:
        for i, line in enumerate(fp, start=1):
            if i == lineno:
                return line.rstrip('\r\n')


class NginxConfigParser(object):
    """
    Parser responsible for parsing the NGINX config and following all includes.
    It is created on demand and discarded after use (to save system resources).
    """

    def __init__(self, filename='/etc/nginx/nginx.conf'):
        self.filename = filename
        self.directory = self._dirname(filename)

        self.files = {}
        self.directories = {}
        self.directory_map = {}

        self.errors = []
        self._broken_files = {}
        self._broken_directories = {}

        self.tree = {}

        self.includes = []
        self.ssl_certificates = []

    def _abspath(self, path):
        if not os.path.isabs(path):
            path = os.path.join(self.directory, path)
        return os.path.normpath(path)

    def _dirname(self, path):
        return os.path.dirname(path) + '/'

    def _handle_error(self, path, e, is_dir=False, exc_info=True, what='read'):
        """
        Stores and logs errors raised by reading and parsing the nginx config
        
        :param path: str - the absolute path of the file or directory
        :param e: Exception - the exception that was raised
        :param is_dir: bool - whether the path is for a directory
        :param exc_info: True or (exc_type, exc_value, exc_traceback)
        :param what: str - what action caused the error (used for logging)
        """
        exc_cls = e.__class__.__name__
        exc_msg = e.strerror if hasattr(e, 'strerror') else str(e)
        message = 'failed to %s %s due to: %s' % (what, path, exc_cls)
        self.errors.append(message)
        if is_dir:
            self._broken_directories[path] = '%s: %s' % (exc_cls, exc_msg)
            context.log.debug(message, exc_info=exc_info)
        else:
            self._broken_files[path] = '%s: %s' % (exc_cls, exc_msg)
            context.log.error(message)

            if isinstance(e, crossplane.errors.NgxParserDirectiveError):
                line = _getline(e.filename, e.lineno)
                context.log.debug('line where error was raised: %r' % line)

            context.log.debug('additional info:', exc_info=exc_info)

    def _add_directory(self, dirname, check=False):
        if dirname not in self.directories:
            self.directories[dirname] = get_filesystem_info(dirname)
            if check:
                try:
                    scandir(dirname)
                except Exception as e:
                    self._handle_error(dirname, e, is_dir=True)

    def _add_file(self, filename):
        if filename not in self.files:
            dirname = self._dirname(filename)
            self._add_directory(dirname, check=True)
            try:
                info = get_filesystem_info(filename)
                info['lines'] = open(filename, encoding='utf-8', errors='replace').read().count('\n')
                self.files[filename] = info
            except Exception as e:
                self._handle_error(filename, e, is_dir=False)

    def _scan_path_pattern(self, pattern):
        """Similar to glob.iglob, except it saves directory errors"""

        # just yield the file if it's a regular boring path with no magic
        magic = glob.magic_check.search(pattern)
        if magic is None:
            yield pattern
            return

        # find the deepest path before the first magic part
        elements = glob.magic_check.split(pattern, 1)
        anchor = elements[0]
        after = elements[-1]

        anchor, start = anchor.rsplit('/', 1)

        offset = anchor.count('/') + 1
        anchor = anchor or '/'

        # get all of the following path parts (>=1 will have magic)
        after = start + magic.group(0) + after
        parts = after.split('/')

        # used to handle directory errors when walking filesystem
        def onerror(e):
            dirname = e.filename + '/'
            if dirname not in self.directories:
                self.directories[dirname] = get_filesystem_info(dirname)
                self._handle_error(dirname, e, is_dir=True)

        # walk the filesystem to collect file paths (and directory errors)
        it = walk(anchor, followlinks=True, onerror=onerror)
        for root, dirs, files in it:
            # get the index of the current path part to use
            index = (root != '/') + root.count('/') - offset

            if index > len(parts) - 1:
                # must've followed a recursive link so go no deeper
                dirs[:] = []
            elif index < len(parts) - 1:
                # determine which directories to walk into next
                dirs[:] = _fnmatch_pattern(dirs, parts[index])
            else:
                # this is the last part, so yield from matching files
                for f in _fnmatch_pattern(files, parts[index]):
                    yield os.path.join(root, f)

                # yield from matching directories too
                for d in _fnmatch_pattern(dirs, parts[index]):
                    yield os.path.join(root, d) + '/'

    def _collect_included_files_and_cert_dirs(self, block, include_ssl_certs):
        for stmt in block:
            if stmt['directive'] == 'include':
                pattern = self._abspath(stmt['args'][0])
                if pattern not in self.includes:
                    self.includes.append(pattern)

                    # use found include patterns to check for os errors
                    for filename in self._scan_path_pattern(pattern):
                        self._add_file(filename)

            elif stmt['directive'] == 'ssl_certificate' and include_ssl_certs:
                cert = self._abspath(stmt['args'][0])
                if stmt['args'][0] and ('$' not in cert or ' if=$' in cert):

                    # add directories that only contain ssl cert files
                    if cert not in self.ssl_certificates:
                        self.ssl_certificates.append(cert)
                        dirname = self._dirname(cert)
                        self._add_directory(dirname, check=True)

            elif 'block' in stmt:
                self._collect_included_files_and_cert_dirs(stmt['block'], include_ssl_certs)

    def parse(self, include_ssl_certs=True):
        # clear results from the previous run
        self.files = {}
        self.directories = {}

        # clear some bits and pieces from previous run
        self._broken_files = {}
        self._broken_directories = {}
        self.includes = []
        self.ssl_certificates = []

        # use the new parser to parse the nginx config
        self.tree = crossplane.parse(
            filename=self.filename,
            onerror=(lambda e: sys.exc_info()),
            catch_errors=True,
            ignore=IGNORED_DIRECTIVES
        )

        for error in self.tree['errors']:
            path = error['file']
            exc_info = error.pop('callback')
            try:
                # these error types are handled by this script already
                if not isinstance(exc_info[1], (OSError, IOError)):
                    self._handle_error(path, exc_info[1], exc_info=exc_info, what='parse')
                    self._add_file(path)
            finally:
                # this speeds things up by deleting traceback, see python docs
                del exc_info

        # for every file in parsed payload, search for files/directories to add
        for config in self.tree['config']:
            if config['parsed']:
                self._add_file(config['file'])
                self._collect_included_files_and_cert_dirs(config['parsed'], include_ssl_certs=include_ssl_certs)

        # construct directory_map
        for dirname, info in self.directories.items():
            self.directory_map[dirname] = {'info': info, 'files': {}}

        for dirname, error in self._broken_directories.items():
            self.directory_map.setdefault(dirname, {'info': {}, 'files': {}})
            self.directory_map[dirname]['error'] = error

        for filename, info in self.files.items():
            dirname = self._dirname(filename)
            self.directory_map[dirname]['files'][filename] = {'info': info}

        for filename, error in self._broken_files.items():
            dirname = self._dirname(filename)
            self.directory_map[dirname]['files'].setdefault(filename, {'info': {}})
            self.directory_map[dirname]['files'][filename]['error'] = error

    def simplify(self):
        """
        This will return one giant list that uses all of the includes logic
        to compile one large nginx context (similar to parsing nginx -T).
        It's very useful for post-analysis and testing.
        """

        def simplify_block(block):
            for stmt in block:
                # ignore comments
                if 'comment' in stmt:
                    continue

                # recurse deeper into block contexts
                if 'block' in stmt:
                    ctx = simplify_block(stmt['block'])
                    stmt = dict(stmt, block=list(ctx))

                yield stmt

                # do yield from contexts included from other files
                if stmt['directive'] == 'include':
                    for index in stmt['includes']:
                        incl_block = self.tree['config'][index]['parsed']
                        for incl_stmt in simplify_block(incl_block):
                            yield incl_stmt

        main_ctx = simplify_block(self.tree['config'][0]['parsed'])
        return list(main_ctx)

    def get_structure(self, include_ssl_certs=False):
        """
        Collects included files, ssl cert files, and their directories and
        then returns them as dicts with mtimes, sizes, and permissions

        :param include_ssl_certs: bool - include ssl certs  or not
        :return: (dict, dict) - files, directories
        """
        files = {}

        if include_ssl_certs:
            regex = INCLUDE_CERT_RE
            has_directive = lambda line: 'include' in line or 'ssl_certificate' in line
        else:
            regex = INCLUDE_ONLY_RE
            has_directive = lambda line: 'include' in line

        def _skim_file(filename):
            """
            Recursively skims nginx configs for include and ssl_certificate
            directives, yielding paths of the files they reference on the way
            """
            if filename in files:
                return

            yield filename
            try:
                # search each line for include or ssl_certificate directives
                with open(filename, encoding='utf-8', errors='replace') as lines:
                    for line in lines:
                        if not has_directive(line):
                            continue

                        for match in regex.finditer(line):
                            if not match:
                                continue

                            file_pattern = self._abspath(match.group(3))

                            # add directory but don't use self._scan_path_pattern
                            # because we don't need to collect directory errors
                            dir_pattern = self._dirname(file_pattern)
                            for path in _iglob_pattern(dir_pattern):
                                self._add_directory(path, check=True)

                            # yield from matching files using _iglob_pattern
                            for path in _iglob_pattern(file_pattern):
                                if match.group(1) == 'include':
                                    for p in _skim_file(path):
                                        yield p
                                else:
                                    yield path
            except Exception as e:
                self._handle_error(filename, e, is_dir=False)

        # collect file names and get mtimes, sizes, and permissions for them
        for fname in _skim_file(self.filename):
            files[fname] = get_filesystem_info(fname)

        return files, self.directories
