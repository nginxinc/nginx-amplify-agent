#!/bin/sh
#
# NGINX Agent install script
#
# Copyright (C) Nginx, Inc. 2021.
#
# Description:
# NGINX Agent install script for downloading the appropriate NGINX Agent package
# from the package repository and installing the agent to work with amplify
# Usage: 
# API_KEY=<api-key> sh install-nginx-agent.sh [-y]
#
# args:
#   API_KEY - unique API key assigned to your Amplify account

packages_url="https://packages.nginx.org/nginx-agent"
package_name="nginx-agent"
public_key_url="https://nginx.org/keys/nginx_signing.key"
public_key_path="/usr/share/keyrings/nginx-archive-keyring.gpg"
agent_conf_path="/etc/nginx-agent"
agent_conf_file="${agent_conf_path}/nginx-agent.conf"
converter_hostname="receiver-grpc.amplify.nginx.com"
grpc_port=443
nginx_conf_file="/etc/nginx/nginx.conf"
ignore_directives_array="ssl_certificate_key ssl_client_certificate ssl_password_file ssl_stapling_file ssl_trusted_certificate auth_basic_user_file secure_link_secret"

# Constants
readonly OS_RHEL="rhel"
readonly OS_CENTOS="centos"
readonly OS_LINUX="linux"
readonly OS_AMAZON="amzn"
readonly OS_UBUNTU="ubuntu"
readonly OS_DEBIAN="debian"
readonly OS_ORACLE="ol"

readonly FLAVOR_RHEL="red hat linux"
readonly FLAVOR_ROCKY="rocky"
readonly FLAVOR_ALMALINUX="almalinux"
readonly FLAVOR_AMAZON="amazon linux"

# Get OS and CPU Architecture information
get_os_and_arch_name () {

    centos_flavor="centos"

    # Use lsb_release if possible
    if command -V lsb_release > /dev/null 2>&1; then
        os=$(lsb_release -is | tr '[:upper:]' '[:lower:]')
        codename=$(lsb_release -cs | tr '[:upper:]' '[:lower:]')
        release=$(lsb_release -rs | sed 's/\..*$//')

        case "$os" in
            redhatenterprise|redhatenterpriseserver|oracleserver)
                os=$OS_RHEL
                centos_flavor=$FLAVOR_RHEL
                ;;
        esac
    # Otherwise it's getting a little bit more tricky
    else
        if ! ls /etc/*-release > /dev/null 2>&1; then
            os=$(uname -s | \
                tr '[:upper:]' '[:lower:]')
        elif cat /etc/*-release | grep '^ID="almalinux"' > /dev/null 2>&1; then
            os=$OS_CENTOS
            centos_flavor=$FLAVOR_ALMALINUX
        elif cat /etc/*-release | grep '^ID="rocky"' > /dev/null 2>&1; then
            os=$OS_CENTOS
            centos_flavor=$FLAVOR_ROCKY
        else
            os=$(cat /etc/*-release | grep '^ID=' | \
                sed 's/^ID=["]*\([a-zA-Z]*\).*$/\1/' | \
                tr '[:upper:]' '[:lower:]')

            if [ -z "$os" ]; then
                if grep -i "oracle linux" /etc/*-release > /dev/null 2>&1 || \
                   grep -i "red hat" /etc/*-release > /dev/null 2>&1; then
                    os=$OS_RHEL
                elif grep -i "centos" /etc/*-release > /dev/null 2>&1; then
                    os=$OS_CENTOS
                else
                    os=$OS_LINUX
                fi
            fi
        fi

        case "$os" in
            "$OS_UBUNTU")
                codename=$(cat /etc/*-release | grep '^DISTRIB_CODENAME' | \
                          sed 's/^[^=]*=\([^=]*\)/\1/' | \
                          tr '[:upper:]' '[:lower:]')
                ;;
            "$OS_DEBIAN")
                codename=$(cat /etc/*-release | grep '^VERSION=' | \
                          sed 's/.*(\(.*\)).*/\1/' | \
                          tr '[:upper:]' '[:lower:]')
                ;;
            "$OS_CENTOS")
                codename=$(cat /etc/*-release | grep -i 'almalinux\|rocky\|centos.*(' | \
                          sed 's/.*(\(.*\)).*/\1/' | head -1 | \
                          tr '[:upper:]' '[:lower:]')
                # For CentOS grab release
                release=$(cat /etc/*-release | grep -i '^version_id=' | cut -d '"' -f 2 | cut -c 1)
                ;;
            "$OS_RHEL"|"$OS_ORACLE")
                codename=$(cat /etc/*-release | grep -i 'red hat.*(' | \
                          sed 's/.*(\(.*\)).*/\1/' | head -1 | \
                          tr '[:upper:]' '[:lower:]')
                # For Red Hat also grab release
                release=$(cat /etc/*-release | grep -i 'red hat.*[0-9]' | \
                         sed 's/^[^0-9]*\([0-9][0-9]*\).*$/\1/' | head -1)

                if [ -z "$release" ]; then
                    release=$(cat /etc/*-release | grep -i '^VERSION_ID=' | \
                             sed 's/^[^0-9]*\([0-9][0-9]*\).*$/\1/' | head -1)
                fi

                os=$OS_CENTOS
                centos_flavor=$FLAVOR_RHEL
                ;;
            "$OS_AMAZON")
                codename="amazon-linux-ami"
                amzn=$(rpm --eval "%{amzn}")
                if [ "${amzn}" = 1 ]; then
                    release="latest"
                else
                    release=${amzn}
                fi

                os=$OS_AMAZON
                centos_flavor=$FLAVOR_AMAZON
                ;;
            *)
                codename=""
                release=""
                ;;
        esac
    fi

    arch=$(uname -m | tr '[:upper:]' '[:lower:]')

    case "$os" in
        "$OS_UBUNTU"| "$OS_DEBIAN")
            if [ "$arch" = "x86_64" ]; then
                arch="amd64"
            elif [ "$arch" = "aarch64" ]; then
                arch="arm64"
            fi
            ;;
        *)
            if [ "$arch" = "amd64" ]; then
                arch="x86_64"
            elif [ "$arch" = "arm64" ]; then
                arch="aarch64"
            fi
            ;;
    esac


}

# Install prerequisite packages (Ubuntu/Debian)
install_prerequisites_deb() {

    keyring_package="ubuntu-keyring"

    if [ "$os" = "$OS_DEBIAN" ]; then
        keyring_package="debian-archive-keyring"
    fi

    # Install prerequisite packages if not found
    if ! dpkg -s curl gnupg2 ca-certificates lsb-release "${keyring_package}" > /dev/null 2>&1; then
        printf "\033[32m ${step}. Installing prerequisites ...\033[0m"

        test -n "$update_cmd" && \
        test -n "$install_cmd" && \
        ${sudo_cmd} apt-get update > /dev/null 2>&1 && \
        ${sudo_cmd} apt-get -y install curl gnupg2 ca-certificates lsb-release "${keyring_package}" > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            printf "\033[32m done.\033[0m\n"
        else
            printf "\033[31m failed.\033[0m\n\n"
            exit 1
        fi

        incr_step
    fi
}

# Install prerequisite packages (yum - CentOS/RHEL/Amazon/Oracle)
install_prerequisites_rpm() {

    prerequisites="yum-utils"

    if [ "$os" = "$OS_AMAZON" ]; then
        prerequisites="${prerequisites} procps"
    fi

    # Install prerequisite packages if not found
    if ! yum list installed "${prerequisites}" > /dev/null 2>&1; then
        printf "\033[32m ${step}. Installing prerequisites ...\033[0m"

        test -n "$update_cmd" && \
        test -n "$install_cmd" && \
        ${sudo_cmd} ${update_cmd} > /dev/null 2>&1 && \
        ${sudo_cmd} ${install_cmd} yum-utils > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            printf "\033[32m done.\033[0m\n"
        else
            printf "\033[31m failed.\033[0m\n\n"
            exit 1
        fi

        incr_step
    fi
}

# Check what downloader is available
check_downloader() {
    if command -V curl > /dev/null 2>&1; then
        downloader="curl"
        downloader_opts="-fs -L"
    elif command -V wget > /dev/null 2>&1; then
        downloader="wget"
        downloader_opts="-q"
    else
        printf "\033[31m no curl or wget found, exiting.\033[0m\n\n"
        exit 1
    fi
}

# Add public key for package verification (Ubuntu/Debian)
add_public_key_deb() {
    printf "\033[32m ${step}. Adding public key ...\033[0m"

    check_downloader && \
    ${downloader} ${downloader_opts} ${public_key_url} | gpg --dearmor \
    | ${sudo_cmd} tee ${public_key_path} > /dev/null 2>&1

    if [ $? -ne 0 ]; then
        printf "\033[31m failed.\033[0m\n\n"
        exit 1
    else
        printf "\033[32m done.\033[0m\n"
    fi
}

# Add repo configuration (apt - Ubuntu/Debian)
add_repo_deb () {
    printf "\033[32m ${step}. Adding repository ...\033[0m"

    test -d /etc/apt/sources.list.d && \
    ${sudo_cmd} test -w /etc/apt/sources.list.d && \
    ${sudo_cmd} rm -f /etc/apt/sources.list.d/nginx-agent.list && \
    echo "deb [signed-by=${public_key_path}]" \
    "${packages_url}/${os}/ ${codename} agent" | \
    ${sudo_cmd} tee /etc/apt/sources.list.d/nginx-agent.list > /dev/null 2>&1 && \
    ${sudo_cmd} chmod 644 /etc/apt/sources.list.d/nginx-agent.list > /dev/null 2>&1

    if [ $? -eq 0 ]; then
        printf "\033[32m added.\033[0m\n"
    else
        printf "\033[31m failed.\033[0m\n\n"
        exit 1
    fi
}

# Add repo configuration (yum - CentOS/RHEL/Amazon/Oracle)
add_repo_rpm () {
    printf "\033[32m ${step}. Adding repository config ...\033[0m"

    os_subpath=$os
    if [ "$os" = "$OS_AMAZON" ]; then
        os_subpath=amzn2
    fi

    test -d /etc/yum.repos.d && \
    ${sudo_cmd} test -w /etc/yum.repos.d && \
    ${sudo_cmd} rm -f /etc/yum.repos.d/nginx-amplify.repo && \
    printf "[nginx-agent]\nname=nginx agent repo\nbaseurl=${packages_url}/${os_subpath}/${release}/\$basearch\ngpgcheck=1\nenabled=1\ngpgkey=${public_key_url}\nmodule_hotfixes=true\n" | \
    ${sudo_cmd} tee /etc/yum.repos.d/nginx-agent.repo > /dev/null 2>&1 && \
    ${sudo_cmd} chmod 644 /etc/yum.repos.d/nginx-agent.repo > /dev/null 2>&1

    if [ $? -eq 0 ]; then
        printf "\033[32m added.\033[0m\n"
    else
        printf "\033[31m failed.\033[0m\n\n"
        exit 1
    fi
}

# Install package (either deb or rpm)
install_deb_or_rpm() {
    # Update repo
    test -n "$update_cmd" && \
    ${sudo_cmd} ${update_cmd}

    if [ $? -eq 0 ]; then
        printf "\033[32m\n ${step}. Updating repository ... done.\033[0m\n"
    else
        printf "\033[31m\n ${step}. Updating repository ... failed.\033[0m\n\n"
        printf "\033[32m Please check the list of the supported systems here https://docs.nginx.com/nginx-agent/technical-specifications\033[0m\n\n"
        exit 1
    fi

    incr_step

    test -n "$package_name" && \
    test -n "$install_cmd" && \
    ${sudo_cmd} ${install_cmd} ${package_name}

    # Install package(s)
    if [ $? -eq 0 ]; then
        printf "\033[32m\n ${step}. Installing nginx-agent package ... done.\033[0m\n"
    else
        printf "\033[31m\n ${step}. Installing nginx-agent package ... failed.\033[0m\n\n"
        printf "\033[32m Please check the list of the supported systems here https://docs.nginx.com/nginx-agent/technical-specifications\033[0m\n\n"
        exit 1
    fi
}

incr_step() {
    step=$((step + 1))
    if [ "${step}" -lt 10 ]; then
        step=" ${step}"
    fi
}

#
# Main
#

assume_yes=""
errors=0

for arg in "$@"; do
    case "$arg" in
        -y)
            assume_yes="-y"
            ;;
        *)
            ;;
    esac
done

step=" 1"

printf "\n --- This script will install the NGINX Agent package ---\n\n"
printf "\033[32m ${step}. Checking admin user ...\033[0m"


sudo_found="no"
sudo_cmd=""

# Check if sudo is installed
if command -V sudo > /dev/null 2>&1; then
    sudo_found="yes"
    sudo_cmd="sudo "
fi

# Detect root
if [ "$(id -u)" = "0" ]; then
    printf "\033[32m root, ok.\033[0m\n"
    sudo_cmd=""
elif [ "$sudo_found" = "yes" ]; then
    printf "\033[33m you'll need sudo rights.\033[0m\n"
else
    printf "\033[31m not root, sudo not found, exiting.\033[0m\n"
    exit 1
fi

incr_step

# Add API key
printf "\033[32m ${step}. Checking API key ...\033[0m"

if [ -n "$API_KEY" ]; then
    api_key=$API_KEY
fi

if [ -z "$api_key" ]; then
    printf "\033[31m What's your API key? Please check the docs and the UI.\033[0m\n\n"
    exit 1
else
    printf "\033[32m using ${api_key}\033[0m\n"
fi

incr_step

get_os_and_arch_name

# Check for supported OS
printf "\033[32m ${step}. Checking OS compatibility ...\033[0m"

# install package
case "$os" in
    "$OS_UBUNTU"|"$OS_DEBIAN")
        printf "\033[32m ${os} detected.\033[0m\n"

        # Install package
        update_cmd="apt-get ${assume_yes} update"
        install_cmd="apt-get ${assume_yes} install"

        install_prerequisites_deb
        incr_step

        add_public_key_deb
        incr_step

        add_repo_deb
        incr_step

        install_deb_or_rpm

        ;;
    "$OS_CENTOS"|"$OS_RHEL"|"$OS_AMAZON")
        printf "\033[32m ${centos_flavor} detected.\033[0m\n"

        update_cmd="yum ${assume_yes} makecache"
        install_cmd="yum ${assume_yes} install"

        install_prerequisites_rpm
        incr_step

        add_repo_rpm
        incr_step


        # Check if nginx packages are excluded
        if grep 'exclude.*nginx' /etc/yum.conf | grep -v '#' >/dev/null 2>&1; then
            printf "\n"
            printf "\033[32m Packages with the 'nginx' names are excluded in /etc/yum.conf - proceed with install (y/n)? \033[0m"

            read -r answer
            printf "\n"

            if [ "${answer}" = "y" ] || [ "${answer}" = "Y" ]; then
                install_cmd="yum ${assume_yes} --disableexcludes=main install"
            else
                printf "\033[31m exiting.\033[0m\n"
                exit 1
            fi
        else
            install_cmd="yum ${assume_yes} install"
        fi

        install_deb_or_rpm
        ;;

    *)
        if [ -n "$os" ] && [ "$os" != "linux" ]; then
            printf "\033[31m $os is currently unsupported, apologies!\033[0m\n\n"
            printf "\033[32m Please check the list of the supported systems here https://docs.nginx.com/nginx-agent/technical-specifications\033[0m\n\n"
        else
            printf "\033[31m failed.\033[0m\n\n"
        fi

        exit 1
esac

incr_step

# Build config file from template
printf "\033[32m ${step}. Building configuration file ...\033[0m"

if [ -f "${agent_conf_file}" ]; then
    ${sudo_cmd} rm -f ${agent_conf_file}.old
    ${sudo_cmd} cp -p ${agent_conf_file} ${agent_conf_file}.old
fi

if command ${sudo_cmd} grep "server:" ${agent_conf_file} >/dev/null 2>&1; then
    ${sudo_cmd} sh -c "sed -i -e 's|host:.*$|host: ${converter_hostname}|' \
                -e 's|grpcPort:.*$|grpcPort: ${grpc_port}|' \
                -e 's|token:.*$|token: \"${api_key}\"|' \
                ${agent_conf_file}"
else
    ${sudo_cmd} printf "\nserver:\n  token: \"${api_key}\"\n  host: ${converter_hostname}\n  grpcPort: ${grpc_port}\n" | \
    ${sudo_cmd} tee -a ${agent_conf_file} > /dev/null 2>&1
fi

if command ${sudo_cmd} grep "tls:" ${agent_conf_file} >/dev/null 2>&1; then
    ${sudo_cmd} sh -c "sed -i -e 's|enable:.*$|enable: True|' \
                -e 's|skip_verify:.*$|skip_verify: False|' \
                ${agent_conf_file}"
else
    ${sudo_cmd} printf "\ntls:\n  enable: True\n  skip_verify: False\n" | \
    ${sudo_cmd} tee -a ${agent_conf_file} > /dev/null 2>&1
fi

# Construct the ignore directives list
ignore_directives_string=""

for ignore_directive in $ignore_directives_array; do
    ignore_directives_string="$ignore_directives_string\n  - $ignore_directive"
done

if command ${sudo_cmd} grep "ignore_directives:" ${agent_conf_file} >/dev/null 2>&1; then
    printf "\n Updating existing ignore_directives... \n"
    ${sudo_cmd} sh -c "sed -i -e 's|ignore_directives:.*$|ignore_directives:${ignore_directives_string}|' \
                ${agent_conf_file}"
else
    printf "\n Adding ignore_directives... \n"
    ${sudo_cmd} printf "ignore_directives:${ignore_directives_string}\n" | \
    ${sudo_cmd} tee -a ${agent_conf_file} > /dev/null 2>&1
fi

${sudo_cmd} chmod 644 ${agent_conf_file}

if [ $? -eq 0 ]; then
    printf "\033[32m done.\033[0m\n"
else
    printf "\033[31m failed.\033[0m\n\n"
    exit 1
fi

incr_step

# Check nginx.conf for stub_status
if [ -f "${nginx_conf_file}" ]; then
    nginx_conf_dir=$(echo ${nginx_conf_file} | sed 's/^\(.*\)\/[^/]*/\1/')

    if [ -d "${nginx_conf_dir}" ]; then
        printf "\033[32m ${step}. Checking if stub_status is configured ...\033[0m"

        if ${sudo_cmd} grep -R "stub_status" "${nginx_conf_dir}"/* > /dev/null 2>&1; then
            printf "\033[32m ok.\033[0m\n"
        else
            printf "\033[31m no stub_status in nginx config, please check https://docs.nginx.com/nginx-amplify/install-manage/configuring-agent/#configuring-the-url-for-stub_status-or-status-api\033[0m\n"
            errors=$((errors + 1))
        fi

        incr_step
    fi
fi

printf "\n"

# Finalize install
if [ "$errors" -eq 0 ]; then
    printf "\033[32m OK, everything went just fine!\033[0m\n\n"
else
    printf "\033[31m A few checks have failed - please read the warnings above!\033[0m\n\n"
fi

start_cmd=""
systemd_cmd=""
if command -V service > /dev/null 2>&1; then 
    systemd_cmd="service"
    start_cmd="service nginx-agent start"
elif command -V systemctl > /dev/null 2>&1; then
    systemd_cmd="systemctl"
    start_cmd="systemctl start nginx-agent"
else
    printf "\033[31m Could not find a way to start the nginx-agent service.\033[0m\n\n"
fi

printf "\033[32m To start and stop the NGINX Agent type:\033[0m\n\n"

if [ "$systemd_cmd" = "service" ]; then
    printf "     \033[7m${sudo_cmd} service nginx-agent { start | stop }\033[0m\n\n"
elif [ "$systemd_cmd" = "systemctl" ]; then
    printf "     \033[7m${sudo_cmd} systemctl { start | stop } nginx-agent\033[0m\n\n"
else
    printf "\033[7m Please use the nginx-agent binary to start the agent.\033[0m\n\n"
fi

printf "\033[32m Nginx Agent log can be found here:\033[0m\n"
printf "     /var/log/nginx-agent/agent.log\n\n"

printf "\033[32m After the agent is launched, it takes a couple of minutes for this system to appear\033[0m\n"
printf "\033[32m in the Amplify user interface.\033[0m\n\n"

# Launch agent
printf "\033[32m Launching nginx-agent ...\033[0m\n"

if [ -z "$start_cmd" ]; then
    printf "\n"
    printf "\033[31m Couldn't start the agent.\033[0m\n\n"
    exit 1 
else
    ${sudo_cmd} ${start_cmd}
    if [ $? -eq 0 ]; then
        printf "\033[32m All done.\033[0m\n\n"
    else
        printf "\n"
        printf "\033[31m Couldn't start the agent, please check /var/log/nginx-agent/agent.log\033[0m\n\n"
        exit 1
    fi
fi
exit 0
