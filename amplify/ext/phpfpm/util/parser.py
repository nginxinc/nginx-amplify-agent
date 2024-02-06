# -*- coding: utf-8 -*-
import glob
import os
from collections import defaultdict


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


IGNORED_CHARACTERS = ("'", '"')


class PHPFPMConfig(object):
    """
    An in memory representation of a PHPFPM config file.  Older versions used
    ConfigParser objects but our experience has shown that this is prone to
    errors since PHPFPM configs are technically INI files rather than YAML.than

    This parser will do the "simple" thing and traverse files looking for key
    indicators and directives constructing a very limited representation of
    a PHPFPM configuraiton.
    """
    def __init__(self, path=None):
        """
        :param path: String Optional config path.  If provided parsing will be
                            done during the init process.
        """
        self.path = path
        self.folder = os.path.dirname(self.path)
        # raw dict structure to save contextual info
        self._structure = defaultdict(lambda: defaultdict(list))
        self._parsed = {
            'file': self.path,
            'include': set(),
            'pools': []
        }  # parsed result dict

        if self.path is not None:
            self.read(self.path)

    @property
    def structure(self):
        return self._structure

    @property
    def parsed(self):
        return self._parsed

    def read(self, root):
        """
        Read the PHPConfig and populate self._structure.  Follows includes.

        :param root: String Path to root config/entry point
        """
        parsed_files = []

        # parse the root file
        self._parse_file(root)
        parsed_files.append(root)

        # since included files can also have include directives, loop until we
        # parse each incrementally found include
        included_files = set()
        while included_files != self._find_includes():
            included_files = self._find_includes()

            for path in included_files:
                # avoid expensive re-parsing
                if path not in parsed_files:
                    self._parse_file(path)
                    parsed_files.append(path)

        # for readability/backwards compatability/json convert set() to list
        self._parsed['include'] = list(self._parsed['include'])

        # finally parse the now complete structure representation of the files
        self._parse_structure()

    def _parse_file(self, path):
        """
        Takes a file path, opens a file, and parses over it.  We do not concern
        ourselves with managing the flie lifecycle here.
        """
        context = 'global'  # default context is global at start of every file

        def _get_value(line):
            """
            Take an INI line and parse the value out of it, removing spaces.
            """
            raw_value = line.split('=', 1)[-1]

            # replace quotes
            for char in IGNORED_CHARACTERS:
                raw_value = raw_value.replace(char, '')

            # handle comments
            raw_value = raw_value.split(';')[0]

            # strip
            raw_value = raw_value.strip()

            return raw_value

        with open(path, 'r', encoding='utf-8') as conf_file:
            for line in conf_file:
                # strip spaces
                line = line.strip()

                if line.startswith('['):
                    # found a new context
                    context = line.replace('[', '').replace(']', '').strip()
                    self._structure[context]['file'] = path
                elif line.startswith('include'):
                    # found an include
                    self._structure[context]['include'].append(
                        _get_value(line)
                    )
                elif line.startswith('listen') and 'listen.' not in line:
                    self._structure[context]['listen'].append(
                        _get_value(line)
                    )
                elif line.startswith('pm.status_path'):
                    self._structure[context]['pm.status_path'].append(
                        _get_value(line)
                    )
                elif line.startswith('pm.status_listen'):
                    self._structure[context]['pm.status_listen'].append(
                        _get_value(line)
                    )

    def _find_includes(self):
        """
        Build a list of inculded files from a list of directive rules.
        """
        includes = set()  # avoid circular imports with set()

        for context, entity in self._structure.items():
            # NOTE: By iterating over all items (including the 'global' key
            # word) we effectively obey all includes equally regardless of
            # location.
            for include_rule in entity.get('include', []):
                # add the rule to the parse result includes
                self._parsed['include'].add(include_rule)

                # resolve local paths
                relative_rule = self._resolve_local_path(include_rule)

                if '*' in relative_rule:
                    # if it is a unix-expansion, find mathcing files
                    for filepath in glob.glob(relative_rule):
                        includes.add(filepath)
                else:
                    # perhaps it is already a file path
                    includes.add(relative_rule)

        return includes

    def _resolve_local_path(self, path):
        """
        Resolves local path
        :param path: str path
        :return: absolute path
        """
        result = path.replace('"', '')
        if not result.startswith('/'):
            result = '%s/%s' % (self.folder, result)
        return result

    def _parse_structure(self):
        """
        Once a read has completed and we have a final structure, we should now
        parse IT and retrieve/organize the "bare minimum" information we need
        to set up collectors and such.

        At the moment, this just means parsing out pool information.
        """
        pool_names = filter(lambda x: x != 'global', self._structure.keys())

        for pool_name in pool_names:
            # Get first found value for interesting directives.  If there are
            # no found directives just set to None
            listen = self._structure[pool_name]['pm.status_listen'][0] \
                if len(self._structure[pool_name]['pm.status_listen']) else \
                self._structure[pool_name]['listen'][0] \
                if len(self._structure[pool_name]['listen']) else None
            status_path = self._structure[pool_name]['pm.status_path'][0] \
                if len(self._structure[pool_name]['pm.status_path']) else None

            pool = dict(
                name=pool_name,
                file=self._structure[pool_name]['file'],
                listen=listen,
                status_path=status_path
            )

            self._parsed['pools'].append(pool)
