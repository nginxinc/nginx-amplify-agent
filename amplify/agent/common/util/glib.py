"""
File _list_ globbing utility

This code is based on glob but varies slightly in that it works on a list of files/paths that is passed rather than a
directory/pathname.

This is useful for multi-tiered glob rules or applying glob rules to a known set of files.
"""
# -*- coding: utf-8 -*-
import os
import re
from glob import has_magic

__all__ = ["glib", "_iglib"]

__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


# Globals

# Match functions (for different match types)

def _combined_match(file_pathname, regex):
    return bool(regex.match(file_pathname))


def _directory_match(file_pathname, regex):
    # dirname is returned without trailing slash
    dirname, _ = os.path.split(file_pathname)
    return bool(regex.match(dirname + '/'))


def _filename_match(file_pathname, regex):
    _, tail = os.path.split(file_pathname)
    return bool(regex.match(tail))


PATHNAME_MAP = {
    'combined': _combined_match,
    'directory': _directory_match,
    'filename': _filename_match
}


def glib(file_list, pathname_pattern):
    """
    Return a subset of the file_list passed that contains only files matching a pathname pattern.

    The pattern may contain simple shell-style wildcards a la fnmatch. However, unlike fnmatch, filenames starting
    with a dot are special cases that are not matched by '*' and '?'

    :param file_list: List of string pathnames
    :param pathname_pattern: String pathname pattern
    :return: List
    """
    return list(_iglib(file_list, pathname_pattern))


# Helpers

def _iglib(file_list, pathname_pattern):
    """
    Return an iterator which yields a subset of the passed file_list matching the pathname pattern.

    The pattern may contain simple shell-style wildcards a la fnmatch. However, unlike fnmatch, filenames starting
    with a dot are special cases that are not matched by '*' and '?'

    :param file_list: List of String pathnames
    :param pathname_pattern: String pathname pattern
    :return: Iterator
    """
    try:
        dirname, tail = os.path.split(pathname_pattern)
    except:
        dirname, tail = None, None

    # Set type based on what info was in pathname pattern
    pathname_type = None
    if dirname and tail:
        pathname_type = 'combined'
    elif dirname and not tail:
        pathname_type = 'directory'
    elif not dirname and tail:
        pathname_type = 'filename'

    if not pathname_type:
        raise TypeError('Expected pathname pattern, got "%s" (type: %s)' % (pathname_pattern, type(pathname_pattern)))

    glib_regex = _glib_regex(pathname_pattern)

    for file_pathname in file_list:
        if PATHNAME_MAP[pathname_type](file_pathname, glib_regex):
            yield file_pathname


def _glib_regex(pathname_pattern):
    """
    Helper for taking pathname patterns and converting them into Python regexes with Unix pathname matching behavior.

    :param pathname_pattern: String pathname
    :return: Compiled Regex
    """
    # First escape '.'
    pathname_pattern.replace('.', '\.')

    if has_magic(pathname_pattern):
        # Replace unspecific '*' and '?' with regex appropriate specifiers ('.')
        for special_char in ('*', '?'):
            split_pattern = pathname_pattern.split(special_char)

            new_split_pattern = []
            # For each section, if there is no regex appropriate closure, add a generic catch.
            for bucket in split_pattern:
                if bucket:
                    # If previous character is not regex closure and is not end of string, then add char...
                    if bucket[-1] != ']' and split_pattern.index(bucket) != len(split_pattern) - 1:
                        bucket += '[^/]'
                elif split_pattern.index(bucket) == 0:
                    # If match char was beginning of string, add regex char...
                    bucket += '[^/]'

                new_split_pattern.append(bucket)

            # Rejoin on special characters
            pathname_pattern = special_char.join(new_split_pattern)

    return re.compile(pathname_pattern)

# TODO: Add better variable guarantees via type checking/casting, or unicode spoofing (see glob for reference).
