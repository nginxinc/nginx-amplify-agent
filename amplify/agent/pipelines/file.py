# -*- coding: utf-8 -*-
import time
from os import stat

from amplify.agent.common.context import context

from amplify.agent.pipelines.abstract import Pipeline


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


# this one is used to store offset between objects' reloads
OFFSET_CACHE = {}


class FileTail(Pipeline):
    """
    Creates an iterable object that returns only unread lines.

    Based on some code of Pygtail
    pygtail - a python "port" of logtail2
    Copyright (C) 2011 Brad Greenlee <brad@footle.org>

    https://raw.githubusercontent.com/bgreenlee/pygtail/master/pygtail/core.py
    """

    def __init__(self, filename):
        super(FileTail, self).__init__(name='file:%s' % filename)
        self.filename = filename
        self._fh = None

        # open a file and seek to the end
        if self.filename not in OFFSET_CACHE:
            with open(self.filename, "r") as f:
                f.seek(0, 2)
                self._offset = OFFSET_CACHE[self.filename] = f.tell()
        else:
            self._offset = OFFSET_CACHE[self.filename]

        # save inode to determine rotations
        self._inode = self._st_ino()

    def __del__(self):
        try:
            if self._filehandle():
                self._fh.close()
        except StopIteration:
            pass

    def __iter__(self):
        self._filehandle()
        return self

    def _st_ino(self):
        return stat(self.filename).st_ino

    def _update_inode(self):
        self._inode = self._st_ino()

    def _file_was_rotated(self):
        """
        Checks that file was rotated
        :return: bool
        """
        # wait for new file
        tries = 0
        new_inode = self._inode

        while tries < 2:  # Try twice before moving on.
            try:
                new_inode = self._st_ino()
            except:
                time.sleep(0.5)
                tries += 1
                pass
            else:
                break

        # If tries == 2 then we know we broke out of the while above manually.
        if tries == 2:
            context.log.error('could not check if file "%s" was rotated (maybe file was deleted?)' % self.filename)
            context.log.debug('additional info:', exc_info=True)
            raise StopIteration

        # check for copytruncate
        # it will use the same file so inode will stay the same
        file_truncated = False
        if new_inode == self._inode and self.filename in OFFSET_CACHE:
            with open(self.filename, 'r') as temp_fh:
                temp_fh.seek(0, 2)
                if temp_fh.tell() < OFFSET_CACHE[self.filename]:
                    # this means the file is smaller than previously cached
                    # so file must have been truncated
                    file_truncated = True

        if file_truncated:
            return True
        return new_inode != self._inode

    def __next__(self):
        """
        Return the next line in the file, updating the offset.
        """
        try:
            line = self._get_next_line()
        except StopIteration:
            # we've reached the end of the file;
            self._update_offset()
            raise
        return line

    def readlines(self):
        """
        Read in all unread lines and return them as a list.
        """
        return [line for line in self]

    def _is_closed(self):
        if not self._fh:
            return True
        return self._fh.closed

    def _filehandle(self):
        """
        Return a filehandle to the file being tailed, with the position set
        to the current offset.
        """
        file_was_rotated = self._file_was_rotated()

        if not self._fh or self._is_closed() or file_was_rotated:
            if not self._is_closed():
                self._fh.close()

            if file_was_rotated:
                self._update_inode()
                self._offset = OFFSET_CACHE[self.filename] = 0

            self._fh = open(self.filename, "r")
            self._fh.seek(self._offset)
        return self._fh

    def _update_offset(self):
        self._offset = OFFSET_CACHE[self.filename] = self._filehandle().tell()

    def _get_next_line(self):
        line = self._fh.readline()
        if not line:
            raise StopIteration
        return line.rstrip('\n\r')
