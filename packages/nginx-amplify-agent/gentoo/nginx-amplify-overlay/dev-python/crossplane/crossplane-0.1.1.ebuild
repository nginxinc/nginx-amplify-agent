# Copyright (C) Nginx, Inc.
# Distributed under the terms of the Apache License 2.0
# $Id$

EAPI=5
PYTHON_COMPAT=( python2_7 )

inherit distutils-r1

DESCRIPTION="Fast and reliable NGINX configuration parser created by the NGINX Amplify team. "
HOMEPAGE="https://github.com/nginxinc/crossplane/"
SRC_URI="mirror://pypi/${PN:0:1}/${PN}/${PN}-${PV}.tar.gz"

LICENSE=Apache
SLOT=0
KEYWORDS="amd64 x86"
IUSE=""

RDEPEND=""
DEPEND="${RDEPEND}"