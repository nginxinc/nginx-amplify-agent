# -*- coding: utf-8 -*-
import copy

from collections import defaultdict

from amplify.agent import Singleton
from amplify.agent.common.context import context


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


# TODO: Add custom exceptions.


class ObjectsTank(Singleton):
    """
    Coordinating entity that coordinates running objects by providing interfaces for interacting with the entire
    collection of objects.  This is a registry only, it does not actually manage or call object methods.
    """

    # TODO: Is it possible to refactor our process so that we don't store ID in the object itself?  This is repeat info.

    def __init__(self):
        self._ID_SEQUENCE = 0

        self.objects = {}
        self.objects_by_type = defaultdict(list)
        self.relations = defaultdict(list)

        self.root_id = 0  # Integer ID of the "root" object.

    @property
    def root_object(self):
        return self.objects[self.root_id] if self.root_id in self.objects else None

    def _get_uid(self):
        self._ID_SEQUENCE += 1
        return self._ID_SEQUENCE

    def _recursive_find_children(self, obj_id):
        result = []

        for child_id in self.relations[obj_id]:
            result.append(child_id)
            result + self._recursive_find_children(child_id)

        return result

    def _recursive_create_struct(self, base_id):
        """
        Constructs a tree of objects starting from the base object specified.

        :param base_id: Int ID of base object to start tree from.
        :return: Dict of objects in a parent-child hierarchy

        {
            'object': Obj
            'children': [
                {
                    'object': Obj,
                    'children': [
                        ...
                    ]
                },
                {
                    'object': Obj,
                    'children': [
                        ...
                    ]
                },
                ...
            ]
        }
        """
        if base_id not in self.objects:
            return

        template = {
            'object': None,
            'children': []
        }
        struct = copy.deepcopy(template)
        struct['object'] = self.objects[base_id]

        for child_id in self.relations[base_id]:
            hierarchy = self._recursive_create_struct(child_id)
            if hierarchy:
                struct['children'].append(hierarchy)

        return struct

    def tree(self, base_id=None):
        if not base_id:
            base_id = self.root_id
        return self._recursive_create_struct(base_id)

    def register(self, obj, parent_obj=None, parent_id=None):
        """
        Registers some object to the tank (adds it).

        :param obj: Obj
        :param parent_id: Int Assigned ID from ID_SEQUENCE for parent object
        """
        obj_id = self._get_uid()

        # Set obj.id property to assigned ID.
        obj.id = obj_id

        # Add object to flat objects store.
        self.objects[obj.id] = obj

        # Add object_id to object type tracker
        self.objects_by_type[obj.type].append(obj.id)

        # If detected root object type, set to root.
        if obj.type in ('system', 'container'):
            self.root_id = obj.id

        # Init relation list
        self.relations[obj.id]

        # Parent handling...
        if parent_obj or parent_id:
            parent_id = parent_obj.id if parent_obj else parent_id

        # If parent_id, add obj_id to appropriate obj list
        if parent_id:
            self.relations[parent_id].append(obj.id)

        context.default_log.debug(
            '"%s" object registered with %s (id: %s, name: %s)' % (
                obj.type, self.__class__.__name__, obj.id, obj.display_name
            )
        )

        return obj.id

    def unregister(self, obj=None, obj_id=None):
        """
        Unregisters object (removes it).

        :param obj: Obj
        :param obj_id: Int Assigned ID from ID_SEQUENCE for object
        """
        if obj or obj_id:
            obj_id = obj.id if obj else obj_id
            obj_name = obj.display_name if obj else obj_id
            obj = self.objects[obj_id] if not obj else obj

        if not obj or obj_id not in self.objects:
            context.default_log.error('failed to unregister object')
            context.default_log.debug(
                'additional info: (obj: %s, obj_id: %s, name: %s)' % (
                    obj, obj_id, obj_name)
            )
            return

        # cache relations since it will change as children remove themselves
        starting_relations = copy.deepcopy(self.relations[obj_id])
        # Recursively unregister children since we will be removing the parent.
        for child_id in starting_relations:
            self.unregister(obj_id=child_id)

        obj_type = obj.type

        # stop obj
        obj.stop()

        # Remove object from flat objects store
        del self.objects[obj_id]

        # Remove obj_id from type tracker
        self.objects_by_type[obj_type].remove(obj_id)

        # Remove relation list for object
        del self.relations[obj_id]

        # Remove obj_id from parent's child list (if any).  This means by
        # default unregister linearly scans all relations looking for obj_id of
        # unregistered object.
        for parent_id, children in self.relations.items():
            if obj_id in children:
                children.remove(obj_id)
                break

        # If obj_id is root...
        if obj_id == self.root_id:
            self.root_id = 0

        context.default_log.debug(
            '"%s" object unregistered with %s (id: %s, name: %s)' % (
                obj.type, self.__class__.__name__, obj_id, obj_name
            )
        )

    def find_one(self, obj_id=None):
        return self.objects[obj_id] if obj_id in self.objects else None

    def find_all(self, obj_id=None, parent_id=None, children=False, types=None, include_self=True):
        """
        Returns a list of registered objects meeting criteria.  First finds all id's matching criteria and then

        :param obj_id: Int Assigned ID of object
        :param parent_id: Int Assigned ID of parent object (returns its children)
        :param children: Bool Whether or not to return children and children's children of the object as well.
        :param types: List/Tuple Iterable of Str object types.
        :param include_self: Bool Whether or not to return the primary obj as well.
        :return: List of Objects
        """
        found_ids = set()

        if obj_id and obj_id in self.objects:
            found_ids.add(obj_id)

        if parent_id and parent_id in self.relations:
            for child_id in self.relations[parent_id]:
                found_ids.add(child_id)

        if children:
            for child_id in self._recursive_find_children(obj_id):
                if child_id in self.objects:
                    found_ids.add(child_id)

        if types:
            for type in types:
                for type_id in self.objects_by_type[type]:
                    if type_id in self.objects:
                        found_ids.add(type_id)

        if not include_self and obj_id in found_ids:
            found_ids.remove(obj_id)

        return [self.objects[found_id] for found_id in found_ids]

    def find_parent(self, obj=None, obj_id=None):
        if obj or obj_id:
            obj_id = obj.id if obj else obj_id

        if not obj_id or obj_id not in self.objects:
            context.default_log.error('Failed to find parent object, object not found (obj_id: %s)' % obj_id)
            return

        found_parent_id = None
        for parent_id, children_ids in self.relations.items():
            if obj_id in children_ids:
                found_parent_id = parent_id
                break

        # make sure the parent_id is still a valid object
        if found_parent_id is not None:
            if found_parent_id in self.objects:
                return self.objects[found_parent_id]
            else:
                context.default_log.error(
                    'Found an invalid parent object_id for child '
                    '(child_id: %s, parent_id: %s)' % (obj_id, parent_id)
                )
                return None
            # This is one of those situations where an action might release the
            # GIL for an extended time, during which an object gets removed
        else:
            return None
