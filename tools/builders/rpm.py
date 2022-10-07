# -*- coding: utf-8 -*-
import sys
import os
import traceback

from builders.util import shell_call, get_version_and_build, install_pip, get_requirements_for_distro

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


def build(bumprevision=False):
    """
    Builds a rpm package
    """
    pkg_root = os.path.expanduser('~') + '/agent-pkg-root'
    pkg_final = os.path.expanduser('~') + '/agent-package'

    rpm_specs = pkg_root + '/SPECS'
    rpm_sources = pkg_root + '/SOURCES'

    # get version and build
    version, bld = get_version_and_build()

    # bump revision if required
    if bumprevision:
        bld = bld + 1

    if not install_pip():
        sys.exit(1)

    try:
        # delete previous build
        shell_call('rm -rf %s' % pkg_root)
        shell_call('rm -rf %s && mkdir %s' % (pkg_final, pkg_final))

        # create rpmbuild dirs
        os.makedirs(rpm_specs)
        os.makedirs(rpm_sources)

        if bumprevision:
            # sed version_build
            shell_call('sed -i.bak -e "s,self.version_build =.*,self.version_build = %d," amplify/agent/common/context.py' % bld)

        # prepare sources
        shell_call('cp packages/nginx-amplify-agent/setup.py ./')
        shell_call('tar -cz --transform "s,^,nginx-amplify-agent-%s/," -f %s/nginx-amplify-agent-%s.tar.gz LICENSE MANIFEST.in amplify/agent amplify/ext amplify/__init__.py etc/ packages/ nginx-amplify-agent.py setup.py' % (version, rpm_sources, version))
        shell_call('cp packages/nginx-amplify-agent/rpm/nginx-amplify-agent.service %s' % rpm_sources)

        if bumprevision:
            # restore original version_build
            shell_call('mv amplify/agent/common/context.py.bak amplify/agent/common/context.py')

        # prepare spec
        shell_call('cp packages/nginx-amplify-agent/rpm/nginx-amplify-agent.spec %s/' % rpm_specs)
        shell_call('sed -e "s,%%%%AMPLIFY_AGENT_VERSION%%%%,%s,g" -e "s,%%%%AMPLIFY_AGENT_RELEASE%%%%,%s,g" -e "s,%%%%REQUIREMENTS%%%%,%s,g" -i %s/nginx-amplify-agent.spec' % (version, bld, get_requirements_for_distro(), rpm_specs))

        # build rpm packages
        shell_call('rpmbuild -D "_topdir %s" -ba %s/nginx-amplify-agent.spec' % (pkg_root, rpm_specs))

        # collect artifacts
        shell_call('find %s/RPMS/ %s/SRPMS/ -type f -name "*.rpm" -print -exec cp {} %s/ \;' % (pkg_root, pkg_root, pkg_final))

        # clean
        shell_call('rm -f setup.py', important=False)
    except:
        print(traceback.format_exc())
