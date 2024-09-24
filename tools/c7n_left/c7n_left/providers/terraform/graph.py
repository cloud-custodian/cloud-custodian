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
            if types and (type_name not in types and f"data.{type_name}" not in types):
                continue
            elif type_name == "module":
                yield type_name, [self.as_resource(type_name, d, "module") for d in type_items]
            elif type_name == "moved":
                yield type_name, [self.as_resource(type_name, d, "moved") for d in type_items]
            elif type_name == "locals":
                yield type_name, [self.as_resource(type_name, d, "local") for d in type_items]
            elif type_name == "terraform":
                yield type_name, [self.as_resource(type_name, d, "terraform") for d in type_items]
            elif type_name == "provider":
                yield type_name, [self.as_resource(type_name, d, "provider") for d in type_items]
            elif type_name == "variable":
                yield type_name, [self.as_resource(type_name, d, "variable") for d in type_items]
            elif type_name == "output":
                yield type_name, [self.as_resource(type_name, d, "output") for d in type_items]
            else:
                data_resources = []
                resources = []
                for item in type_items:
                    name = item["__tfmeta"]["path"]
                    resource = self.as_resource(name, item)
                    if item["__tfmeta"].get("type", "resource") == "data":
                        data_resources.append(resource)
                    else:
                        resources.append(resource)

                if resources:
                    if types and type_name in types:
                        yield type_name, resources
                    elif not types:
                        yield type_name, resources
                if data_resources:
                    if types and f"data.{type_name}" in types:
                        yield f"data.{type_name}", data_resources
                    elif not types:
                        yield f"data.{type_name}", data_resources

    def as_resource(self, name, data, type_name=None):
        if type_name and "type" not in data["__tfmeta"]:
            data["__tfmeta"]["type"] = type_name
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
            if not "__tfmeta" in r:
                continue
            rtype = r["__tfmeta"]["label"]
            if r["__tfmeta"].get("type") == "data":
                rtype = f"data.{rtype}"
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
