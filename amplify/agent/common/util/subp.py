# -*- coding: utf-8 -*-
import subprocess

from amplify.agent.common.errors import AmplifySubprocessError

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


def call(command, check=True):
    """
    Calls subprocess.Popen with the command

    :param command: full shell command
    :param check: check the return code or not
    :return: subprocess stdout [], stderr [] - both as lists
    """
    subprocess_params = dict(
        shell=True,
        universal_newlines=True,
        encoding='utf-8',
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    process = subprocess.Popen(command, **subprocess_params)
    try:
        raw_out, raw_err = process.communicate()
        if process.returncode != 0 and check:
            raise AmplifySubprocessError(message=command, payload=dict(returncode=process.returncode, error=raw_err))
        else:
            if type(raw_out) == bytes:
               raw_out = raw_out.decode('utf-8')
            if type(raw_err) == bytes:
               raw_err = raw_err.decode('utf-8')
            out = raw_out.split('\n')
            err = raw_err.split('\n')
            return out, err
    except:
        raise
    finally:
        # warning: if GreenletExit was the original exception thrown, no other raised exception in this
        # finally block should be left unhandled

        # in the case of multiple greenlets trying to run and read from and close stdout/stderr,
        # this can lead to RuntimeError: reentrant calls.  Watch for exception and ignore
        for pipe in (process.stdin, process.stdout, process.stderr):
            try:
                pipe.close()
            except:
                pass
