#!/bin/sh

#
# This script will collect various configuration information about
# the OS, the nginx, and the Amplify Agent environments.
#
# It is intended to be used only while DEBUGGING a failed installation,
# or while examining any obscure problems with the metric collection.
#
# This script is NOT part of the Amplify Agent runtime.
# It DOES NOT send anything anywhere on its own.
# It is NOT ever being invoked automatically.
#
# The script will use the Amplify Agent in the debug mode, and it will
# also use some standard OS utilities to gather an understanding of
# the OS, the package and the user environment.
#
# The script DOES NOT change any system parameters or configuration.
# It saves all output to a temporary directory in /tmp
#
# Some of the output might be sensitive to the administrator.
#
# If you think anything sensitive can be found in the logs, please
# REVIEW the output very thoroughly before sharing it with the
# Amplify support for the purposes of troubleshooting your Amplify
# installation.
#
# The script should be run under root privileges.
#

amplify_pid_file="/var/run/amplify-agent/amplify-agent.pid"

printf "\n"
printf "\033[32m --- This script will collect debug informatiom from the NGINX Amplify Agent --- \033[0m\n\n"

# Detect root
if [ "`id -u`" = "0" ]; then
    sudo_cmd=""
else
    if command -V sudo >/dev/null 2>&1; then
        sudo_cmd="sudo "
        echo "HEADS UP - The script will use sudo, you need to be in sudoers(5)"
        echo ""
    else
        echo "Started as non-root, sudo not found, exiting."
        exit 1
    fi
fi

printf "\033[31m *** PLEASE READ THE IMPORTANT INFORMATION BELOW *** \033[0m\n\n"
printf "   1. The script will re-start the Amplify Agent in a debug mode.\n\n"
printf "   2. The debug log from the agent will reside in a temporary directory\n"
printf "      named /tmp/amplify.debug.<ID>\n\n"
printf "   3. Some additional information about your operational system will\n"
printf "      also be collected.\n\n"
printf "   4. It may take the script up to 10 minutes to finish.\n\n"
printf "   5. This script is not automatically sending ANY information ANYWHERE.\n\n"
printf "   6. You will have to check the collected information, and sanitize it,\n"
printf "      if necessary.\n\n"
printf "   7. You will have to manually send the collected information to\n"
printf "      our support team.\n\n"

printf "\033[32m Continue (y/n)? \033[0m"
read line
echo ""
test "${line}" = "y" -o "${line}" = "Y" || \
    exit 1

# Check for an older version of the agent running
if [ -f "${amplify_pid_file}" ]; then
    amplify_pid=`cat ${amplify_pid_file}`

    if ps "${amplify_pid}" >/dev/null 2>&1; then
        printf "\033[32m Stopping old amplify-agent, pid ${amplify_pid}\033[0m\n\n"
        ${sudo_cmd} service amplify-agent stop > /dev/null 2>&1 < /dev/null

        if [ $? != 0 ]; then
            printf "\033[31m Can't stop amplify-agent, exiting!\033[0m\n\n"
            exit 1
        fi
    fi
fi

random=`date '+%s' | sed 's/.*\(.....\)$/\1/'`
tmpdir="/tmp/amplify.debug.`expr ${random} + $$`"

printf "\033[32m Creating log directory ${tmpdir} ... \033[0m\n\n"

if [ ! -d /tmp ]; then
    printf "\033[31m Can't find /tmp, exiting!\033[0m\n\n"
    exit 1
fi

if [ -e ${tmpdir} ]; then
    printf "\033[31m Found ${tmpdir} already existing, can't continue!\033[0m\n\n"
    exit 1
else
    mkdir -p ${tmpdir}
fi

printf "\033[32m Launching amplify-agent in debug mode ...\033[0m\n"

if command -V timeout >/dev/null 2>&1; then
    ${sudo_cmd} timeout --signal=SIGTERM --kill-after=630s 600s service amplify-agent debug "${tmpdir}/agent.debug.log"
else
    ( ${sudo_cmd} service amplify-agent debug "${tmpdir}/agent.debug.log" ) &
    sleep 5
    timeout=0

    while :; do
    	agent_pid=`ps axuw | grep -i "[ ]amplify[-]agent" | awk '{print $2}'`
        if [ "${agent_pid}" != "" ]; then
            sleep 1
            timeout=`expr ${timeout} + 1`
            if [ "${timeout}" -gt 600 ]; then
                kill ${agent_pid}
                if [ "${timeout}" -gt 630 ]; then
                    kill -9 ${agent_pid}
                    break
                fi
            fi
        else
            break
        fi
    done
fi

printf "\n"

${sudo_cmd} chown $(whoami) $tmpdir

if [ -f ./collect-env.sh ]; then
    printf "\033[32m Collecting additional information about with collect-env.sh ...\033[0m\n\n"
    ${sudo_cmd} sh ./collect-env.sh -q > "${tmpdir}/collect-env.log"
else
    printf "\033[31m Can't find ./collect-env.sh ...\033[0m\n"
fi

printf "\n"
printf "\033[32m Here are the contents of ${tmpdir} ...\033[0m\n\n"
ls -la ${tmpdir}
printf "\n"
printf "\033[32m Please check the files above and send them to the Amplify support team!\033[0m\n\n"


printf "\033[32m Launching amplify-agent ...\033[0m\n\n"
${sudo_cmd} service amplify-agent start > /dev/null 2>&1 < /dev/null

if [ $? -eq 0 ]; then
    printf "\033[32m All done.\033[0m\n\n"
else
    printf "\n"
    printf "\033[31m Couldn't start the agent, please check /var/log/amplify-agent/agent.log\033[0m\n\n"
    exit 1
fi

exit 0