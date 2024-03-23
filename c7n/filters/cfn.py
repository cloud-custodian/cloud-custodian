from c7n.filters import ValueFilter
from c7n.manager import resources
from c7n.utils import type_schema


class CloudFormationStackResourceFilter(ValueFilter):
    annotation_key = "c7n:cfn-stack-resource"
    schema = type_schema("cfn-stack-resource", rinherit=ValueFilter.schema)

    def process(self, resources, event=None):
        stack_resource_manager = self.manager.get_resource_manager("cfn-stack-resource")
        stack_resources = {
            (r["ResourceType"], r["PhysicalResourceId"]): r
            for r in stack_resource_manager.resources()
        }
        results = []
        for r in resources:
            if self.annotation_key not in r:
                r[self.annotation_key] = stack_resources.get(
                    (self.manager.get_model().cfn_type, r[self.manager.get_model().id])
                )
            if self.match(r[self.annotation_key]):
                results.append(r)
        return results

    @classmethod
    def register_resources(klass, registry, resource_class):
        if getattr(resource_class.resource_type, "cfn_type", None):
            resource_class.filter_registry.register("cfn-stack-resource", klass)


resources.subscribe(CloudFormationStackResourceFilter.register_resources)
