# -*- coding: utf-8 -*-
import re
import copy

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


RE_TYPE = type(re.compile('amplify'))


class Filter(object):
    def __init__(self, data=None, metric=None, filter_rule_id=None):
        self.metric = metric
        self.filter_rule_id = filter_rule_id
        self.filename = None
        self.filenamematch = None
        self.data = {}
        self._negated_conditions = {}
        self.original_data = data

        # normalize vars
        for key, operator, value in data or []:
            if key == 'logname':
                self.filename = value
                self.filenamematch = bool(operator == '~')
                continue
            elif key == '$request_method':
                normalized_value = value.upper()
            else:
                normalized_value = value

            # try to treat any value as a regex
            try:
                normalized_value = re.compile(normalized_value)
            except:
                pass

            normalized_key = key.replace('$', '')
            self.data[normalized_key] = normalized_value
            self._negated_conditions[normalized_key] = (operator == '!~')

        self.empty = not self.data and not self.filename

    def __deepcopy__(self, memodict=None):
        return Filter(data=copy.deepcopy(self.original_data), metric=self.metric, filter_rule_id=self.filter_rule_id)

    def match(self, parsed):
        """
        Checks if a parsed string matches a filter
        :param parsed: {} of parsed string
        :return: True of False
        """
        for filter_key, filter_value in self.data.items():
            # if the key isn't in parsed, then it's irrelevant
            if filter_key not in parsed:
                return False

            negated = self._negated_conditions[filter_key]
            value = str(parsed[filter_key])

            string_equals = isinstance(filter_value, str) and filter_value == value
            regex_matches = isinstance(filter_value, RE_TYPE) and bool(re.match(filter_value, value))
            values_match = (string_equals or regex_matches)

            if not values_match and not negated:
                return False
            elif values_match and negated:
                return False

        return True

    def matchfile(self, filename):
        """
        Checks to see if filter should apply to filename.

        :param filename: String filename
        :return: Boolean
        """
        if self.filename is None and self.filenamematch is None:
            return True
        elif self.filenamematch and filename == self.filename:
            return True
        elif not self.filenamematch and not filename == self.filename:
            return True
        else:
            return False
