# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#

from ...core import ResourceGraph
from .resource import TerraformResource


class TerraformGraph(ResourceGraph):

    resolver = None

    def __len__(self):
        return sum([len(v) for k, v in self.resource_data.items() if "_" in k])

    def get_resources_by_type(self, types=()):
        if isinstance(types, str):
            types = (types,)
        for type_name, type_items in self.resource_data.items():
            if types and type_name not in types:
                continue
            if type_name == "data":
                for data_type, data_items in type_items.items():
                    resources = []
                    for name, data in data_items.items():
                        resources.append(self.as_resource(name, data))
                    yield "%s.%s" % (type_name, data_type), resources
            elif type_name == "moved":
                yield type_name, self.as_resource(type_name, data)
            elif type_name == "locals":
                yield type_name, self.as_resource(type_name, data)
            elif type_name == "terraform":
                yield type_name, self.as_resource(type_name, data)
            else:
                resources = []
                for data in type_items:
                    name = data["__tfmeta"]["path"]
                    resources.append(self.as_resource(name, data))
                yield type_name, resources

    def as_resource(self, name, data):
        data["__tfmeta"]["src_dir"] = self.src_dir
        return TerraformResource(name, data)

    def build(self):
        self.resolver = Resolver()
        self.resolver.build(self.resource_data)
        return self.resolver

    def get_refs(self, resource, target_type):
        return self.resolver.resolve_refs(resource, (target_type,))


class Resolver:
    def __init__(self):
        self._id_map = {}
        self._ref_map = {}

    @staticmethod
    def is_id_ref(v):
        if len(v) != 36:
            return False
        if v.count("-") != 4:
            return False
        return True

    def resolve_refs(self, block, types=None):
        refs = self._ref_map.get(block["id"], ())
        for rid in refs:
            r = self._id_map[rid]
            rtype = r["__tfmeta"]["label"]
            if types and rtype not in types:
                continue
            yield r

    def visit(self, block, root=False):
        if not isinstance(block, dict):
            return ()

        bid = None
        refs = set()

        for k, v in list(block.items()):
            if k == "id":
                bid = v
                self._id_map[v] = block
            elif isinstance(v, str) and self.is_id_ref(v):
                refs.add(v)
            if isinstance(v, (str, int, float, bool)):
                continue
            if isinstance(v, dict) and k != "__tfmeta":
                refs.update(self.visit(v))
            if isinstance(v, list):
                list(map(self.visit, v))

        if refs and block.get("__tfmeta", {}).get("label"):
            self._ref_map.setdefault(bid, []).extend(refs)
            for r in refs:
                self._ref_map.setdefault(r, []).append(bid)

        return refs

    build = visit
