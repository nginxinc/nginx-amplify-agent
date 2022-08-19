# -*- coding: utf-8 -*-
from collections import defaultdict


from amplify.agent.common.config.abstract import AbstractConfig


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class ConfigTank(object):
    """
    AbstractConfig manager that is able to initialize and abstractly access any
    of the managed configs.
    """

    def __init__(self):
        self._configs = {} if '_configs' not in self.__dict__ else self._configs
        self._path_index = {} if '_path_index' not in self.__dict__ else self._path_index
        self._name_index = {} if '_name_index' not in self.__dict__ else self._name_index
        self._section_index = {} if '_section_index' not in self.__dict__ else self._section_index

    def __idx(self, config):
        path = config.filename

        if path in self._path_index:
            _current_idx = self._path_index[path]
        else:
            _current_idx = len(self._configs)

        # save the config
        self._configs.update({
            _current_idx: config
        })

        # index the pathname
        if path not in self._path_index:
            self._path_index.update({
                path: _current_idx
            })

        # index the filename
        filename = path.split('/')[-1]
        if filename not in self._name_index:
            self._name_index.update({
                filename: _current_idx
            })

        # index the sections
        for section in config.config:
            # only index if section has not been indexed before
            if section not in self._section_index:
                self._section_index[section] = _current_idx

    def __unidx(self, config):
        path = config.filename

        if path in self._path_index:
            _current_idx = self._path_index[path]
        else:
            return  # config not in tank

        del self._path_index[path]

        filename = path.split('/')[-1]
        del self._name_index[filename]

        for section, idx in list(self._section_index.items()):
            if idx == _current_idx:
                del self._section_index[section]

        del self._configs[_current_idx]

    def reindex(self):
        for config in list(self._configs.values()):
            self.__idx(config)

    def full_index(self):
        configs = self._configs.values()

        self._configs = {}
        self._path_index = {}
        self._name_index = {}
        self._section_index = {}

        for config in configs:
            self.__idx(config)

    @property
    def default(self):
        """Returns the first (agent) config if it exists"""
        return self._configs[0] if len(self._configs) else None

    def __getattr__(self, attr):
        if 0 in self._configs:
            return getattr(self._configs[0], attr)
        else:
            raise AttributeError(
                "'%s' object has no attribute '%s'" % (
                    self.__class__.__name__,
                    attr
                )
            )

    def __getitem__(self, section):
        """Get implementation which calls .get and raises KeyError if DNE"""
        result = self.get(section)

        if result is None:
            raise KeyError(section)

        return result

    def __setitem__(self, section, value):
        if section in self._section_index:
            config = self._configs[self._section_index[section]]
        else:
            config = self._configs[0]

        config[section] = value

        self.__idx(config)

    def get(self, section, default=None):
        """
        Simple get method that is designed to operate like dict.get().  Will
        map a section to a config and then return the section from said config
        as if the config was directly referenced.
        """
        # re-index just in case
        self.reindex()

        if section in self._section_index:
            return self._configs[self._section_index[section]][section]
        else:
            return default

    def get_config(self, filename):
        """
        Simple method for returning the direct config object (pierce the
        abstracton).
        """
        if filename in self._path_index:
            return self._configs[self._path_index[filename]]
        elif filename in self._name_index:
            return self._configs[self._name_index[filename]]
        elif filename in self._configs:
            return self._configs[filename]
        else:
            raise KeyError(filename)

    def load(self, filename):
        """
        Try to intialize, and then index/store a config from a file.

        :param filename: String Filepath to try and read from.
        """
        config = AbstractConfig(config_file=filename)

        self.__idx(config)

    def add(self, config):
        """
        Index/store an already initialized config.

        :param config: AbstractConfig Initialized AbstractConfig instance
        """
        self.__idx(config)

    def remove(self, config):
        self.__unidx(config)
        self.full_index()

    def save(self, section, key, value, target=None):
        """
        Maps section to a config and then passes save call to that config.
        """
        if section in self._section_index:
            config = self._configs[self._section_index[section]]
        elif target is not None:
            if target in self._path_index:
                config = self._configs[self._path_index[target]]
            elif target in self._name_index:
                config = self._configs[self._name_index[target]]
            elif target in self._configs:
                config = self._configs[0]
            else:
                raise KeyError(target)
        else:
            raise KeyError(section)

        config.save(section, key, value)

        # reindex in case new sections were added
        self.__idx(config)

    def apply(self, patch, target=None):
        """
        Iterates through a prospective patch, separating 1st level sections by
        config and then passes the patch call to those configs individually.
        """
        changes = 0
        indexed_patch = defaultdict(dict)

        if target is None:
            # split the patch into sub-patches based on config they apply to
            for section in patch.keys():
                if section in self._section_index:
                    # if the section is known, link the update to the config
                    indexed_patch[self._section_index[section]].update(
                        patch[section]
                    )
                else:
                    # if the section is unknown, link the update to the 0 config
                    indexed_patch[0].update(patch[section])
        else:
            if target in self._path_index:
                indexed_patch[self._path_index[target]].update(patch)
            elif target in self._name_index:
                indexed_patch[self._name_index[target]].update(patch)
            elif target in self._configs:
                indexed_patch[0].update(patch)
            else:
                raise KeyError(target)

        # iterate through the now split patches and apply them
        for index, patch in indexed_patch.items():
            config = self._configs[index]
            changes += config.apply(patch)

            # reindex in case sections were added
            self.__idx(config)

        return changes
