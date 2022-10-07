# -*- coding: utf-8 -*-
import sys
import os
import traceback

from builders.util import shell_call, get_version_and_build, change_first_line, install_pip, get_requirements_for_distro

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


COMPAT_LEVELS = {
    'bionic': 11,
    'buster': 12,
    'focal': 12,
    'bullseye': 13,
    'jammy': 13
}


def build(bumprevision=False):
    """
    Builds a deb package
    """
    pkg_root = os.path.expanduser('~') + '/agent-pkg-root'
    pkg_final = os.path.expanduser('~') + '/agent-package'

    # get version and build
    version, bld = get_version_and_build()

    # bump revision if required
    if bumprevision:
        bld = bld + 1

    # get codename
    codename = shell_call("lsb_release -cs").rstrip('\n')

    if not install_pip():
        sys.exit(1)

    try:
        # delete previous build
        shell_call('rm -rf %s' % pkg_root)
        shell_call('rm -rf %s && mkdir %s' % (pkg_final, pkg_final))

        # prepare debuild-root
        debuild_root = "%s/nginx-amplify-agent-%s" % (pkg_root, version)
        shell_call('mkdir -p %s' % debuild_root)

        # copy debian files to debuild-root
        shell_call('cp -r packages/nginx-amplify-agent/deb/debian %s/' % debuild_root)
        shell_call('mkdir -p %s/debian/source' % debuild_root)
        shell_call('echo "3.0 (quilt)" >%s/debian/source/format' % debuild_root)

        # deal with distro-specific things
        shell_call('cp %s/debian/control.%s %s/debian/control' % (debuild_root, codename, debuild_root))
        shell_call('echo %s >%s/debian/compat' % (COMPAT_LEVELS[codename], debuild_root))
        shell_call('sed -ie "s,%%%%REQUIREMENTS%%%%,%s,g" %s/debian/rules' % (get_requirements_for_distro(), debuild_root))

        # sed first line of changelog
        changelog_first_line = 'nginx-amplify-agent (%s-%s~%s) %s; urgency=low' % (version, bld, codename, codename)
        change_first_line('%s/debian/changelog' % debuild_root, changelog_first_line)

        if bumprevision:
            # sed version_build
            shell_call('sed -i.bak -e "s,self.version_build =.*,self.version_build = %d," amplify/agent/common/context.py' % bld)

        # create source tarball
        shell_call('cp packages/nginx-amplify-agent/setup.py ./')
        shell_call('tar -cz --transform "s,^,nginx-amplify-agent-%s/," -f %s/nginx-amplify-agent_%s.orig.tar.gz LICENSE MANIFEST.in amplify/agent amplify/ext amplify/__init__.py etc/ packages/ nginx-amplify-agent.py setup.py' % (version, pkg_root, version))
        shell_call('cd %s && tar zxf nginx-amplify-agent_%s.orig.tar.gz' % (pkg_root, version))

        if bumprevision:
            # restore original version_build
            shell_call('mv amplify/agent/common/context.py.bak amplify/agent/common/context.py')

        # create deb package
        shell_call('cd %s && debuild -us -uc' % debuild_root, terminal=True)

        # collect artifacts
        shell_call('find %s/ -maxdepth 1 -type f -print -exec cp {} %s/ \;' % (pkg_root, pkg_final))

        # clean
        shell_call('rm -f setup.py', important=False)
    except:
        print(traceback.format_exc())
