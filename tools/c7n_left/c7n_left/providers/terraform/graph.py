# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#

from ...core import ResourceGraph
from .resource import TerraformResource


class TerraformGraph(ResourceGraph):


    def __len__(self):
        return sum(map(len, self.resource_data.values()))

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
                for name, data in type_items.items():
                    resources.append(self.as_resource(name, data))
                yield type_name, resources

    def as_resource(self, name, data):
        if isinstance(data["__tfmeta"], list):
            for m in data["__tfmeta"]:
                m["src_dir"] = self.src_dir
        else:
            data["__tfmeta"]["src_dir"] = self.src_dir
        return TerraformResource(name, data)



class NodeVisitor:

    def __init__(self):
        self.graph = {}
        self._index = {}

    @property
    def id_node_map(self):
        return self._index

    def visit(self, block):
        for k, v in list(block.items()):
            if k == 'id' and isinstance(v, int):
                self._index[v] = block
            if isinstance(v, list) and v and len(v) == 1 and '__tfmeta' in v[0]:
                block[k] = v[0]
            if isinstance(v, dict):
                self.visit(block)

    def resolve_refs(self, block):
        for k, v in list(block.items()):
            if instance(v, int) and v in self.graph:
                block[k] = self.graph[v]

        
        
            
