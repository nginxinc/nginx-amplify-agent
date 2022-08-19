# -*- coding: utf-8 -*-
import subprocess
import sys
import os
import distro

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


PIP_MIN_VERSION = '9.0.4'


def color_print(message, color='green'):
    if color == 'red':
        template = '\033[31m%s\033[0m'
    elif color == 'green':
        template = '\033[32m%s\033[0m'
    elif color == 'yellow':
        template = '\033[33m%s\033[0m'
    print (template % message)


def shell_call(cmd, terminal=False, important=True):
    """
    Runs shell command

    :param cmd: ready-to-run command
    :param terminal: uses os.system to run instead of process
    :param important: stops the script if shell command returns non-zero exit code
    :return:
    """
    print('\033[32m%s\033[0m' % cmd)

    if terminal:
        rc = os.system(cmd)
        if important and rc != 0:
            print('\033[31mFAILED!\033[0m')
            sys.exit(1)
    else:
        process = subprocess.Popen(cmd, shell=True, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        results, errors = process.communicate()

        # print normal results
        for line in results.split('\n'):
            if line:
                print(line)

        # print warnings and errors
        sys.stdout.write('\033[33m')
        for line in errors.split('\n'):
            if line:
                print(line)
        sys.stdout.write('\033[0m')
        print('')

        # check
        process.wait()
        if important and process.returncode != 0:
            print('\033[31mFAILED!\033[0m')
            sys.exit(1)
        else:
            return results


def get_version_and_build():
    with open('packages/version', 'r') as f:
        version, build = f.readline().split('-')
        return version, int(build)


def change_first_line(filename, first_line):
    with open(filename, 'r+') as f:
        lines = f.readlines()
        lines[0] = first_line
        lines.insert(1, "\n")
        f.seek(0)
        f.writelines(lines)


def get_pip_version():
    try:
        import pip as _pip
    except:
        return False

    return tuple(map(int, _pip.__version__.split('.')))


def install_pip():
    pip_version = get_pip_version()

    # we are good - pip was found with enough version
    if pip_version and pip_version >= tuple(map(int, PIP_MIN_VERSION.split('.'))):
        color_print('Using pip version %s\n' % '.'.join(map(str, pip_version)), color='green')
        return True

    # pip was found but a version is older than required
    if pip_version:
        if os.getenv('FORCE_PIP_INSTALL', 'NO').lower() != 'yes':
            color_print('ERROR: pip version is lower than required, set FORCE_PIP_INSTALL=YES to overcome or try to upgrade python3-pip package', color='red')
            return False

        color_print('Upgrading pip', color='yellow')
        shell_call("%s -m pip install --user 'pip>=%s'" % (sys.executable, PIP_MIN_VERSION), important=True)

    # pip was not found
    else:
        if os.getenv('FORCE_PIP_INSTALL', 'NO').lower() != 'yes':
            color_print('ERROR: pip not found, set FORCE_PIP_INSTALL=YES to overcome or try to install python3-pip package', color='red')
            return False

        color_print('Installing pip via get-pip', color='yellow')
        shell_call('curl -LO https://bootstrap.pypa.io/get-pip.py', important=True)
        shell_call('%s get-pip.py --user --ignore-installed --upgrade' % sys.executable, important=True)

    return True


def get_requirements_for_distro():
    distro_tag_full = "%s%s%s" % (distro.id(), distro.major_version(), distro.minor_version())
    distro_tag_short = "%s%s" % (distro.id(), distro.major_version())
    distro_tag_codename = "%s" % distro.codename()

    if os.path.isfile("packages/nginx-amplify-agent/requirements-%s.txt" % distro_tag_full):
        return "packages/nginx-amplify-agent/requirements-%s.txt" % distro_tag_full

    elif os.path.isfile("packages/nginx-amplify-agent/requirements-%s.txt" % distro_tag_short):
        return "packages/nginx-amplify-agent/requirements-%s.txt" % distro_tag_short

    elif os.path.isfile("packages/nginx-amplify-agent/requirements-%s.txt" % distro_tag_codename):
        return "packages/nginx-amplify-agent/requirements-%s.txt" % distro_tag_codename

    else:
        color_print('WARNING: no specific requirements for %s, using default list' % ' '.join(distro.linux_distribution()), color='yellow')
        return "packages/nginx-amplify-agent/requirements.txt"


def install_pip_deps():
    shell_call(
        '%s -m pip install --upgrade --target=amplify --no-compile -r %s' %
        (sys.executable, get_requirements_for_distro())
    )
