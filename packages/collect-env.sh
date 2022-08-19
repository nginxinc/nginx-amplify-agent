#!/bin/sh
#
# Copyright (C) Nginx, Inc.
#

# TODO
#
# -- check if sudo exists
#

agent_conf_path="/etc/amplify-agent"
agent_conf_file="${agent_conf_path}/agent.conf"
agent_log_file="/var/log/amplify-agent/agent.log"
api_url="https://receiver.amplify.nginx.com:443/ping/"

found_nginx_master=""
found_nginx_user=""
found_agent_conf=""
found_lsb_release=""

if [ "$1" != "-q" ]; then
    quiet="yes"

    cat <<-EOM >&2
	#
	# HEADS UP:
	#
	# This script will collect various configuration information about
	# the OS, the nginx, and the Amplify Agent environments.
	#
	# It is intended to be used only while DEBUGGING a failed installation,
	# or while examining an obscure problem with the metric collection.
	#
	# This script is NOT part of the Amplify Agent runtime.
	# It DOES NOT send anything anywhere on its own.
	# It is NOT installed by default, and it is NOT ever
	# being invoked automatically.
	#
	# The script will use standard OS utilities to gather an
	# understanding of the OS, the package and the user environment.
	#
	# The script DOES NOT change any system parameters or
	# configuration. All output is simply to STDOUT.
	#
	# Some of the output might be sensitive to the administrator.
	# If anything sensitive pops up in the script output,
	# please REVIEW it thoroughly before sharing for debug
	# purposes.
	#
	# The script should be run under root privileges.
	#
	# Example:
	# sh collect-env.sh > collect-env.log
	#
EOM

    echo "" >&2
    /bin/echo -n "Continue (y/n)? " >&2

    read answer && \
    test "${answer}" = "y" -o \
         "${answer}" = "Y" -o \
         "${answer}" = "yes" -o \
         "${answer}" = "Yes" || \
    exit 1
fi

if [ "`id -u`" != "0" ]; then
    echo ""
    echo "This script should be run under root privileges."
    echo "exiting."

    exit 1
fi

echo "Collecting data ..." >&2

nginx_master=`ps axu | grep -i '[:] master.*nginx'`

if [ -n "${nginx_master}" ]; then
    IFS_OLD=$IFS
    IFS=`/bin/echo -en "\n\b"`

    found_nginx_master="yes"

    echo "===> found nginx master process(es):"

    for i in ${nginx_master}; do
	echo " ---> ${i}"
	echo ""
	nginx_bin=`echo ${i} | sed 's/.*master process \([^ ][^ ]*\).*$/\1/'`
	nginx_pid=`echo ${i} | awk '{print $2}'`
	nginx_ppid=`ps o ppid ${nginx_pid} | sed 's/ //g' | tail -1`
	nginx_conf_option=`echo ${i} | grep '\-c' | sed 's/.*-c \([^ ][^ ]*\).*$/\1/'`

	if [ -n "${nginx_bin}" ]; then
	    echo "  ---> started from binary: ${nginx_bin}, pid ${nginx_pid}, ppid ${nginx_ppid}"
	    test -f "${nginx_bin}" && \
	    ls -la ${nginx_bin}
	    echo ""

	    if [ "${nginx_ppid}" -ne 1 ]; then
	        echo "  ---> nginx master process ppid ${nginx_ppid} != 1 (a Docker container?)"
	        echo ""

			if [ "${nginx_ppid}" -ne 0 ]; then
			    echo "   ---> ps o pid,ppid,user,command ${nginx_ppid}:"
	            ps o pid,ppid,user,command ${nginx_ppid} 2>&1
	            echo ""
			fi
	    fi

	    if [ -n "${nginx_conf_option}" ]; then
		echo "  ---> started with config file: ${nginx_conf_option}"
		ls -la ${nginx_conf_option}
		echo ""
	    fi

	    if [ -f "${nginx_bin}" ]; then
		echo "  ---> version and configure options:"
		${nginx_bin} -V 2>&1
	    else
		echo "  ---> can't find binary \"${nginx_bin}\" !"
	    fi
	    echo ""
	fi

	echo "  ---> ps xa -o user,pid,ppid,command | egrep 'nginx[:]|[^/]amplify[-]agent'"
	ps xa -o user,pid,ppid,command | egrep 'nginx[:]|[^/]amplify[-]agent'
	echo ""
    done

    IFS=$IFS_OLD
else
    echo "===> no nginx master process(es) found!"
fi

if id nginx > /dev/null 2>&1; then
    echo "===> found nginx user:"
    id nginx
    echo ""
    found_nginx_user="yes"
fi

if [ -e /etc/nginx ]; then
    echo "===> contents of /etc/nginx:"
    ls -la /etc/nginx
    echo ""

    if [ -e /etc/nginx/conf.d ]; then
	echo "===> contents of /etc/nginx/conf.d:"
	ls -la /etc/nginx/conf.d
	echo ""
    fi

    if grep -R "stub_status" /etc/nginx/* > /dev/null 2>&1; then
        echo "===> found stub_status somewhere inside /etc/nginx/*"
        grep -n -R "stub_status" /etc/nginx/*
        echo ""
    fi
fi

if [ -e /var/log/nginx ]; then
    echo "===> uncompressed log files in /var/log/nginx:"
    ls -la /var/log/nginx | grep -i 'log$'
    echo ""
fi


if [ -f "${agent_conf_file}" ]; then
    echo "===> found agent.conf file:"
    ls -la ${agent_conf_file}
    echo ""
    found_agent_conf="yes"
fi

if [ "${found_agent_conf}" = "yes" ]; then
    echo "===> ${agent_conf_file}:"
    cat ${agent_conf_file}
    echo ""

    amplify_user=`grep -v '#' ${agent_conf_file} | \
                  grep -A 5 -i '\[.*nginx.*\]' | \
                  grep -i 'user.*=' | \
                  awk -F= '{print $2}' | \
                  sed 's/ //g' | \
                  head -1`

    nginx_conf_file=`grep -A 5 -i '\[.*nginx.*\]' ${agent_conf_file} | \
               grep -i 'configfile.*=' | \
               awk -F= '{print $2}' | \
               sed 's/ //g' | \
               head -1`

    if [ -z "${nginx_conf_file}" ]; then
        echo " ---> using default path to nginx config"
	nginx_conf_file="/etc/nginx/nginx.conf"
    else
	echo " ---> using non-default path to nginx config: ${nginx_conf_file}"
    fi

    if [ -f "${nginx_conf_file}" ]; then
	nginx_user=`grep 'user[[:space:]]' ${nginx_conf_file} | \
                	  grep -v '[#].*user.*;' | \
                	  grep -v '_user' | \
                	  sed -n -e 's/.*\(user[[:space:]][[:space:]]*[^;]*\);.*/\1/p' | \
                	  awk '{ print $2 }' | head -1`
    fi

    if [ -n "${amplify_user}" ]; then
        echo " ---> real user ID for the agent is set in ${agent_conf_file}"
    else
	test -n "${nginx_user}" && \
	amplify_user=${nginx_user} && \
	echo " ---> real user ID for the agent is set by the 'user' directive in ${nginx_conf_file}"

	if [ $? = 0 ]; then
	    echo " ---> agent will use the following real user ID for EUID: ${amplify_user}"
	else
	    amplify_user="nginx"
	    echo " ---> using default real user ID for the agent's EUID"
	fi
    fi

    echo ""
    echo " ---> ps axu | grep -i '[^/]amplify[-]'"
    ps axu | grep -i '[^/]amplify[-]'
    echo ""
fi

if [ -n "${amplify_user}" ]; then
    echo "===> checking if user \"${amplify_user}\" can see nginx master processes:"
    sudo -u ${amplify_user} /bin/sh -c "ps xao pid,ppid,command | grep 'nginx[:]'" 2>&1
    echo ""
fi

if command -V python > /dev/null 2>&1; then
    echo "===> Python version:"
    python --version 2>&1
else
    echo "===> Python not found!"
fi

echo ""

echo "===> uname -a"
uname -a
echo ""

centos_flavor="centos"

if command -V lsb_release > /dev/null 2>&1; then
    os=`lsb_release -is | tr '[:upper:]' '[:lower:]'`
    codename=`lsb_release -cs | tr '[:upper:]' '[:lower:]'`
    release=`lsb_release -rs | sed 's/\..*$//'`

    found_lsb_release="yes"

    if [ "$os" = "redhatenterpriseserver" -o "$os" = "oracleserver" ]; then
	os="centos"
	centos_flavor="red hat linux"
    fi
else
    if ! ls /etc/*-release > /dev/null 2>&1; then
	os=`uname -s | \
	    tr '[:upper:]' '[:lower:]'`
    else
	os=`cat /etc/*-release | grep '^ID=' | \
	    sed 's/^ID=["]*\([a-zA-Z]*\).*$/\1/' | \
	    tr '[:upper:]' '[:lower:]'`

	if [ -z "$os" ]; then
	    if grep -i "oracle linux" /etc/*-release > /dev/null 2>&1 || \
	       grep -i "red hat" /etc/*-release > /dev/null 2>&1; then
		os="rhel"
	    else
		if grep -i "centos" /etc/*-release > /dev/null 2>&1; then
		    os="centos"
		else
		    os="linux"
		fi
	    fi
	fi
    fi

    case "$os" in
	ubuntu)
	    codename=`cat /etc/*-release | grep '^DISTRIB_CODENAME' | \
		      sed 's/^[^=]*=\([^=]*\)/\1/' | \
		      tr '[:upper:]' '[:lower:]'`
	    ;;
	debian)
	    codename=`cat /etc/*-release | grep '^VERSION=' | \
		      sed 's/.*(\(.*\)).*/\1/' | \
		      tr '[:upper:]' '[:lower:]'`
	    ;;
	centos)
	    codename=`cat /etc/*-release | grep -i 'centos.*(' | \
		      sed 's/.*(\(.*\)).*/\1/' | head -1 | \
		      tr '[:upper:]' '[:lower:]'`
	    # For CentOS grab release
	    release=`cat /etc/*-release | grep -i 'centos.*[0-9]' | \
		     sed 's/^[^0-9]*\([0-9][0-9]*\).*$/\1/' | head -1`
	    ;;
	rhel)
	    codename=`cat /etc/*-release | grep -i 'red hat.*(' | \
		      sed 's/.*(\(.*\)).*/\1/' | head -1 | \
		      tr '[:upper:]' '[:lower:]'`
	    # For Red Hat also grab release
	    release=`cat /etc/*-release | grep -i 'red hat.*[0-9]' | \
		     sed 's/^[^0-9]*\([0-9][0-9]*\).*$/\1/' | head -1`

	    if [ -z "$release" ]; then
		release=`cat /etc/*-release | grep -i '^VERSION_ID=' | \
			 sed 's/^[^0-9]*\([0-9][0-9]*\).*$/\1/' | head -1`
	    fi

	    os="centos"
	    centos_flavor="red hat linux"
	    ;;
	amzn)
	    codename="amazon-linux-ami"
	    release_amzn=`cat /etc/*-release | grep -i 'amazon.*[0-9]' | \
		     sed 's/^[^0-9]*\([0-9][0-9]*\.[0-9][0-9]*\).*$/\1/' | \
		     head -1`
	    release="latest"

	    os="amzn"
	    centos_flavor="amazon linux"
	    ;;
	*)
	    codename=""
	    release=""
	    ;;
    esac
fi

if [ -n "${found_lsb_release}" ]; then
    echo "===> lsb_release:"
    lsb_release -is
    lsb_release -cs
    lsb_release -rs
    echo ""
fi

if ls /etc/*-release > /dev/null 2>&1; then
    echo "===> /etc/*-release file(s):"
    for i in `ls /etc/*-release`; do
        echo " ---> ${i}:"
        cat ${i}
        echo ""
    done
fi

echo "===> install.sh variables:"
echo "os=${os}"
echo "codename=${codename}"
echo "release=${release}"
echo ""

pkg_cmd=""

case "${os}" in
    ubuntu|debian)
	pkg_cmd1="dpkg -s"
	pkg_cmd2="dpkg -L"
	;;
    centos|rhel|amzn)
	pkg_cmd1="rpm -qi"
	pkg_cmd2="rpm -ql"
	;;
    *)
	;;
esac

if [ -n "${pkg_cmd1}" -a -n "${pkg_cmd2}" ]; then
    echo "===> checking packages:"
    echo ""
    echo " ---> ${pkg_cmd1} nginx-amplify-agent"
    ${pkg_cmd1} nginx-amplify-agent 2>&1
    echo ""
    echo " ---> ${pkg_cmd2} nginx-amplify-agent | grep 'agent\(.py\)*$'"
    ${pkg_cmd2} nginx-amplify-agent 2>&1 | grep 'agent\(.py\)*$' 2>&1
    echo ""

    for pkg in nginx nginx-core nginx-plus; do
	echo " ---> ${pkg_cmd1} ${pkg}" && \
	${pkg_cmd1} ${pkg} 2>&1 && \
	echo "" && \
	echo " ---> ${pkg_cmd2} ${pkg} | grep 'nginx$'" && \
	${pkg_cmd2} ${pkg} 2>&1 | grep 'nginx$' 2>&1
	echo ""
    done
fi

if cat /proc/1/cgroup | grep -v '.*/$' > /dev/null 2>&1; then
    echo "===> looks like this is a container, not a host system"
    cat /proc/1/cgroup | grep -v '.*/$'
    echo ""
fi

echo "===> checking /proc:"
echo " ---> mount | egrep 'proc|sysfs'"
mount | egrep 'proc|sysfs'
echo ""

if mount | egrep 'proc|sysfs' > /dev/null 2>&1; then
    nginx_workers="`ps xa -o pid,command | egrep 'nginx[:].*worker process' | awk '{print $1}'`"

    echo " ---> ls -lad /proc:"
    ls -lad /proc
    echo ""

    if [ -n "${nginx_workers}" ]
    then
	echo ' ---> /proc/${pid}/io and /proc/${pid}/limits:'

	for i in ${nginx_workers}; do
	    ls -la /proc/${i}/io
	    ls -la /proc/${i}/limits
	    worker_user=`ps -o user ${i} | tail -1`
	    test "${worker_user}" = "${amplify_user}" && \
		test_worker_pid=$i
	done

	if [ -n "${amplify_user}" ]; then
	    echo ""
	    echo " ---> sudo -u ${amplify_user} /bin/sh -c 'cat /proc/${test_worker_pid}/io'"
	    sudo -u ${amplify_user} /bin/sh -c "cat /proc/${test_worker_pid}/io" 2>&1

	    echo ""
	    echo " ---> sudo -u ${amplify_user} /bin/sh -c 'head -5 /proc/vmstat'"
	    sudo -u ${amplify_user} /bin/sh -c "head -5 /proc/vmstat" 2>&1

	    echo ""
	    echo " ---> sudo -u ${amplify_user} /bin/sh -c 'ls -la /sys/block'"
	    sudo -u ${amplify_user} /bin/sh -c "ls -la /sys/block" 2>&1
	fi
    else
	echo " ---> can't find any nginx workers."
    fi

    if test -e /proc/user_beancounters -o \
	    -e /proc/bc; then
	echo ""
	echo "===> found /proc/user_beancounters or /proc/bc (OpenVZ?)"
	echo ""
    fi
else
    echo " ---> can find procfs or sysfs mounts"
fi

echo ""

if [ -f /etc/resolv.conf ]; then
    echo "===> /etc/resolv.conf is:"
    cat /etc/resolv.conf
    echo ""
fi

if [ "${os}" = "ubuntu" -o "${os}" = "debian" -a -x /etc/init.d/apparmor ]; then
    echo "===> /etc/init.d/apparmor status:"
    /etc/init.d/apparmor status
    echo ""
fi

if [ "${os}" = "centos" -o "${os}" = "amzn" -a -f /etc/selinux/config ]; then
    echo "===> /etc/selinux/config is:"
    cat /etc/selinux/config
    echo ""
fi

if [ -f /etc/grsec/policy ]; then
    echo "===> found /etc/grsec/policy!"
    echo ""

    if command -V gradm > /dev/null 2>&1; then
	echo " ---> gradm --status"
	gradm --status 2>&1
	echo ""
    fi
fi

echo "===> environment variables:"
set | \
egrep 'PATH|SHELL|TERM|USER|HOSTNAME|HOSTTYPE|LOGNAME|MACHTYPE|OSTYPE|SUDO_USER|SUDO_COMMAND'

echo ""

if [ -f "${agent_log_file}" ]; then
    echo "===> checking ${agent_log_file}:"
    echo ""
    echo " ---> tail -20 ${agent_log_file}"
    tail -20 ${agent_log_file}
    echo ""
    echo " ---> egrep -i 'failed to' ${agent_log_file} | tail -50"
    egrep -i 'failed to' ${agent_log_file} | tail -50
else
    echo "===> can't find ${agent_log_file}"
fi

echo ""

echo "===> testing connectivity to Amplify:"
if command -V curl > /dev/null 2>&1; then
    curl -s -I ${api_url}
else
    if command -V wget > /dev/null 2>&1; then
	wget -S --max-redirect 0 ${api_url}
    fi
fi

echo ""
echo "finished." >&2

exit 0
