# Copyright (C) Nginx, Inc.
# Distributed under the terms of the BSD 2-clause Simplified License
# $Id$

EAPI="5"

PYTHON_COMPAT=( python2_7 )

inherit eutils distutils-r1 user versionator

DESCRIPTION="NGINX Amplify Agent"
HOMEPAGE="https://amplify.nginx.com"
MY_PV=$(replace_version_separator 2 '-')
MY_PV1=$(get_version_component_range 1-2)
FNAME="${PN}-${MY_PV}"
SRC_URI="https://github.com/nginxinc/nginx-amplify-agent/archive/v${PV}-1.zip"
RESTRICT="mirror"
LICENSE="BSD 2-clause Simplified License"
SLOT="0"
KEYWORDS="amd64 x86"
IUSE=""

DEPEND="
    ~dev-python/gevent-1.2.1[${PYTHON_USEDEP}]
    ~dev-python/lockfile-0.11.0[${PYTHON_USEDEP}]
    ~dev-python/netaddr-0.7.18[${PYTHON_USEDEP}]
    ~dev-python/netifaces-0.10.4[${PYTHON_USEDEP}]
    >=dev-python/psutil-4.0.0[${PYTHON_USEDEP}]
    ~dev-python/requests-2.12.5[${PYTHON_USEDEP}]
    ~dev-python/ujson-1.33[${PYTHON_USEDEP}]
    >=dev-python/python-daemon-2.0.6[${PYTHON_USEDEP}]
    ~dev-python/pyparsing-2.2.0[${PYTHON_USEDEP}]
    ~dev-python/setproctitle-1.1.10[${PYTHON_USEDEP}]
    >=dev-python/rstr-2.2.3[${PYTHON_USEDEP}]
    ~dev-python/flup-1.0.2[${PYTHON_USEDEP}]
    ~dev-python/scandir-1.5[${PYTHON_USEDEP}]
    >=dev-python/crossplane-0.1.1[${PYTHON_USEDEP}]
"
RDEPEND="
	www-servers/nginx[nginx_modules_http_stub_status]
"

S="${WORKDIR}/${FNAME}"

python_install_all() {
	distutils-r1_python_install_all
	newinitd "${FILESDIR}"/nginx-amplify-agent.initd nginx-amplify-agent

	keepdir /var/log/amplify-agent/ /var/run/amplify-agent

}

pkg_postinst() {
	chown nginx /var/log/amplify-agent
	# agent rewrites file itself, needs to be writable
	chown nginx /etc/amplify-agent/agent.conf
	chown nginx /var/run/amplify-agent
}
