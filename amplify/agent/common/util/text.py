# -*- coding: utf-8 -*-


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


def construct_trie_dict(*args):
    """
    Helper function to construct a Trie dictionary based on a passed list of
    patterns to match.

    All Trie entries have a key 'end' that is True if it was the end of a
    pattern.

    :param args: list Of string patterns to add to the Trie dict.
    """
    trie_dict = {'end': False}

    index = 0
    for pattern in args:
        current_location = trie_dict  # each pattern starts at trie_dict root

        for char in pattern:
            # if char is not in the current_location add it
            if char not in current_location:
                current_location[char] = {'end': False, 'index': []}

            # navigate down the dict
            current_location = current_location[char]

        current_location['end'] = True
        current_location['index'].append(index)

        index += 1

    return trie_dict


def parse_key(string):
    """
    Takes a raw string of an nginx access log variable and parses the name out
    of it.

    :param string: str Raw value of nginx access log variable.
    :return: str Variable name
    """
    chars_to_remove = ['$', '{', '}']
    return string.translate((str.maketrans('', '', ''.join(chars_to_remove))))


def decompose_format(string, full=False):
    """
    Takes a raw string nginx access log definition and decomposes it into
    various elements useful for quick parsing.

    :param string: str Raw access log definition.
    :param full: bool Whether or not to return non-key patterns as well.
    :return keys: list Key name strings ordered by occurance.
    :return trie_dict: dict A Trie dictionary for matching the non-key patterns
    """
    keys = []
    non_key_patterns = []
    first_value_is_key = False

    current_pattern = ''

    for char in string:
        if char.isalpha() or char.isdigit() or char in ('_', '{'):

            # these values may be keys or not...so just add it to the pattern
            current_pattern += char

        elif char == '$':
            # a new variable key is starting
            # if this is the first value in the format mark it so
            if len(non_key_patterns) == 0 and current_pattern == '':
                first_value_is_key = True

            # save the current pattern as a "non key"
            if len(current_pattern):
                non_key_patterns.append(current_pattern)

            # start a new pattern with this char
            current_pattern = char

        else:

            # the rest of these characters might signal the end of a variable
            # key
            if current_pattern.startswith('$'):
                # if it is the end of a variable key parse the current pattern
                # for the key name
                keys.append(parse_key(current_pattern))

                # start a new pattern with this char if it isn't '}'
                current_pattern = char if char != '}' else ''
            else:
                # if it's not the end of a key, just keep adding it to the
                # pattern
                current_pattern += char

    # handle the last pattern
    if len(current_pattern):
        if current_pattern.startswith('$'):
            keys.append(parse_key(current_pattern))
        else:
            non_key_patterns.append(current_pattern)

    trie = construct_trie_dict(*non_key_patterns)

    if full:
        return keys, trie, non_key_patterns, first_value_is_key
    else:
        return keys, trie


def parse_line(line, keys=None, trie=None):
    """
    Take a raw access log line and parse it.  It works by using the Trie dict
    to replace all non-key patterns with an empty space (' ') and quickly
    splitting this more easily parsed line into values.  The Trie dict is
    important since it allows efficient single-pass pattern replacement.
    """
    stripped_line = ''

    current_location = trie  # start at the top of the Trie
    current_pattern = ''
    index = 0  # track variable postion

    for char in line:
        current_pattern += char

        if current_location['end'] and index in current_location['index']:
            if stripped_line != '':
                # only add '\n' if first value has been found
                stripped_line += '\n'
            current_pattern = ''
            index += 1

            if char in trie:
                current_pattern = char
                current_location = trie[char]
            else:
                stripped_line += char
                current_location = trie
        elif char in current_location:
            current_location = current_location[char]  # go down the trie
        else:
            # char is not in current_location or at the end of a known/correct
            # pattern...this might mean partial match or a non-matched
            # character at top of Trie

            stripped_line += current_pattern
            current_pattern = ''

            current_location = trie  # go back to top of the trie

    values = stripped_line.split('\n')

    return dict(zip(keys, values))


def parse_line_split(line, keys=None, non_key_patterns=None, first_value_is_key=False):
    """
    Take a raw access log line and parse it.  It works by taking all found
    non-key patterns and iteratively splitting the line.
    """
    values = []
    for i, pattern in enumerate(non_key_patterns):
        value, line = line.split(pattern, 1)

        # skip first split if it is a non_key_pattern
        if first_value_is_key or i > 0:
            values.append(value)

    # if there are characters in line or there's one more value left to find
    if len(line) or len(keys) == len(values) + 1:
        values.append(line)

    return dict(zip(keys, values))
