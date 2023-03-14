# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from importlib.abc import MetaPathFinder, Loader
from importlib.machinery import ModuleSpec
import os
import sys

from .manager import initialize_resource


class ResourceFinder(MetaPathFinder):
    """python importer for virtual resource modules from json data files."""

    @classmethod
    def attach(cls):
        found = False
        for s in sys.meta_path:
            if s == cls:
                found = True
                break

        if not found:
            sys.meta_path.append(cls)
        else:
            return False
        return True

    @staticmethod
    def find_spec(fullname, path, target=None):
        if not fullname.startswith("c7n_awscc.resources."):
            return
        module_attrs = initialize_resource(fullname.rsplit(".", 1)[-1])
        if module_attrs is None:
            return
        return ModuleSpec(
            fullname,
            ResourceLoader(module_attrs),
            origin=path[0] + os.sep + fullname.rsplit(".", 1)[-1] + ".py",
        )


class ResourceLoader(Loader):
    def __init__(self, module_attrs):
        self.module_attrs = module_attrs

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        for k, v in self.module_attrs.items():
            setattr(module, k, v)
