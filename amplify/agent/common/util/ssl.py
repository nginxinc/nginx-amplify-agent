# -*- coding: utf-8 -*-
import datetime
import os
import re
import time

from amplify.agent.common.context import context
from amplify.agent.common.util import subp

__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


ssl_regexs = (
    re.compile('.*/C=(?P<country>[\w]+).*'),
    re.compile('.*/ST=(?P<state>[\w\s]+).*'),
    re.compile('.*/L=(?P<location>[\w\s]+).*'),
    re.compile('.*/O=(?P<organization>[\w\s,\'\-\.]+).*'),
    re.compile('.*/OU=(?P<unit>[\w\s,\-\.]+).*'),
    re.compile('.*/CN=(?P<common_name>[\w\s\'\-\.]+).*'),
)

ssl_subject_map = {
    'C': 'country',
    'ST': 'state',
    'L': 'location',
    'O': 'organization',
    'OU': 'unit',
    'CN': 'common_name'
}


ssl_text_regexs = (
    re.compile('.*Public Key Algorithm: (?P<public_key_algorithm>.*)'),
    re.compile('.*Public-Key: \((?P<length>\d+).*\)'),
    re.compile('.*Signature Algorithm: (?P<signature_algorithm>.*)')
)


ssl_dns_regex = re.compile('DNS:[\w\s\-\.]+')


def certificate_dates(filename):
    keys = {
        'notBefore': 'start',
        'notAfter': 'end'
    }
    results = {}

    openssl_out, _ = subp.call("openssl x509 -in %s -noout -dates" % filename, check=False)
    for line in openssl_out:
        if line:
            key, value = line.split('=')
            if key in keys:
                results[keys[key]] = int(datetime.datetime.strptime(value, '%b %d %H:%M:%S %Y %Z').strftime('%s'))

    return results or None


def certificate_subject_old(filename):
    """
    This older method for parsing SSL subject proved unreliable because of output structure differences between systems.
    Instead we implemented a new, simpler method below that uses structured text interpretation and string splits
    instead of stand-alone regular expressions.
    """
    results = {}

    openssl_out, _ = subp.call("openssl x509 -in %s -noout -subject" % filename, check=False)
    for line in openssl_out:
        if line:
            for regex in ssl_regexs:
                match_obj = regex.match(line)
                if match_obj:
                    results.update(match_obj.groupdict())

    return results or None


def parse_raw_certificate_subject(openssl_out):
    """
    :param openssl_out: list of strings - output from subp.call()
    :return: dict
    """
    results = {}
    for line in openssl_out:
        if line:
            output = line[8:]  # trim "subject=" or "Subject:" from output
            factors = output.split(',')  # split output into distinct groups
            prev_factor = None
            for factor in factors:
                if '=' in factor:
                    key, value = factor.split('=', 1)  # only split on the first equal sign
                    key = key.lstrip().upper()  # remove leading spaces (if any) and capitalize (if lowercase)
                    if key in ssl_subject_map:
                        results[ssl_subject_map[key]] = value
                    prev_factor = key
                elif prev_factor in ssl_subject_map:
                    # If there wasn't an '=' in the current factor, go back the previous factor and append the current
                    # factor to the result in order to account for values where a ',' was part of the value.
                    results[ssl_subject_map[prev_factor]] += (',' + factor)

                    # Replace escaped \ (workaround)
                    results[ssl_subject_map[prev_factor]] = results[ssl_subject_map[prev_factor]].replace('\\', '')
    return results or None


def certificate_subject(filename):
    """
    :param filename: string
    :return: dict
    """
    # -nameopt RFC2253 escapes characters where there is no ASCII value
    # so we turn off the sub-option responsible for that, which is esc_msb
    openssl_out, _ = subp.call("openssl x509 -in %s -noout -subject -nameopt RFC2253 -nameopt -esc_msb" % filename, check=False)
    results = parse_raw_certificate_subject(openssl_out)
    return results


def certificate_issuer(filename):
    results = {}

    openssl_out, _ = subp.call("openssl x509 -in %s -noout -issuer" % filename, check=False)
    for line in openssl_out:
        if line:
            for regex in ssl_regexs:
                match_obj = regex.match(line)
                if match_obj:
                    results.update(match_obj.groupdict())

    return results or None


def certificate_purpose(filename):
    results = {}

    openssl_out, _ = subp.call("openssl x509 -in %s -noout -purpose" % filename, check=False)
    for line in openssl_out:
        if line:
            split = line.split(' : ')
            if len(split) == 2:
                key, value = line.split(' : ')
                results[key] = value

    return results or None


def certificate_ocsp_uri(filename):
    result = None

    openssl_out, _ = subp.call("openssl x509 -in %s -noout -ocsp_uri" % filename, check=False)
    if openssl_out[0]:
        result = openssl_out[0]

    return result


def certificate_full(filename):
    results = {}

    openssl_out, _ = subp.call("openssl x509 -in %s -noout -text" % filename, check=False)
    for line in openssl_out:
        for regex in ssl_text_regexs:
            match_obj = regex.match(line)
            if match_obj:
                results.update(match_obj.groupdict())
                continue  # If a match was made skip the DNS check.

            dns_matches = ssl_dns_regex.findall(line)
            if dns_matches:
                results['names'] = list(map(lambda x: x.split(':')[1], dns_matches))
    return results or None


def ssl_analysis(filename):
    """
    Get information about SSL certificates found by NginxConfigParser.

    :param filename: String Path/filename
    :return: Dict Information dict about ssl certificate
    """
    results = dict()

    start_time = time.time()
    context.log.info('ssl certificate found %s' % filename)

    # Check if we can open certificate file
    try:
        cert_handler = open(filename, 'r')
        cert_handler.close()
    except IOError:
        context.log.info('could not read %s (maybe permissions?)' % filename)
        return None

    try:
        # Modified date/time
        results['modified'] = int(os.path.getmtime(filename))

        # Certificate dates
        results['dates'] = certificate_dates(filename)

        # Subject information
        results['subject'] = certificate_subject(filename)

        # Issuer information
        results['issuer'] = certificate_issuer(filename)

        # Purpose information
        results['purpose'] = certificate_purpose(filename)

        # OCSP URI
        results['ocsp_uri'] = certificate_ocsp_uri(filename)

        # Domain names, etc
        additional_info = certificate_full(filename)
        if additional_info:
            results.update(additional_info)

        if 'length' in results:
            results['length'] = int(results['length'])

        if results.get('names'):
            if results['subject']['common_name'] not in results['names']:
                results['names'].append(results['subject']['common_name'])  # add subject name
        else:
            results['names'] = [results['subject']['common_name']]  # create a new list of 1
    except Exception as e:
        exception_name = e.__class__.__name__
        message = 'failed to analyze certificate %s due to: %s' % (filename, exception_name)
        context.log.debug(message, exc_info=True)
        return None
    finally:
        end_time = time.time()
        context.log.debug('ssl analysis took %.3f seconds for %s' % (end_time-start_time, filename))

    return results

