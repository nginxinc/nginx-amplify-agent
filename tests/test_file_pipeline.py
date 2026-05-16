"""
Tests for the file pipeline (FileTail).
"""
import itertools
import os
import tempfile

from amplify.agent.pipelines.file import FileTail, OFFSET_CACHE


def test_filetail_tolerates_non_utf8_bytes():
    """A non-UTF-8 byte in a tailed log file must not crash iteration.

    Reproduces the production failure on hosts whose nginx error_log
    mixes encodings (e.g. a stray 0xd0 from Cyrillic mojibake). With
    the default codec + errors='strict', readline() raises
    UnicodeDecodeError and the per-instance collector dies. With
    errors='replace' the bad byte becomes U+FFFD and iteration
    continues.
    """
    fd, path = tempfile.mkstemp(suffix=".log")
    os.close(fd)
    try:
        with open(path, "wb") as fh:
            fh.write(b"good line\n" + b"bad \xd0 byte\n" + b"after\n")

        OFFSET_CACHE.pop(path, None)
        tail = FileTail(path)
        OFFSET_CACHE[path] = 0
        tail._offset = 0

        lines = list(itertools.islice(tail, 3))
        assert len(lines) == 3
        assert "good line" in lines[0]
        assert "after" in lines[2]
    finally:
        OFFSET_CACHE.pop(path, None)
        try:
            os.unlink(path)
        except OSError:
            pass
