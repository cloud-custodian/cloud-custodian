# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
import itertools

from c7n.filters import Filter, ValueFilter, OPERATORS
from c7n.utils import type_schema


class Traverse(Filter):
    """Traverse the resource graph.

    This filter allows going from a source node across multiple hops
    to a set of related nodes with multi attributes matching at
    destination.


    .. code-block:: yaml

      policies:
        - name: s3-encryption
          description: ensure buckets are using kms encryption
          resource: terraform.aws_s3_bucket
          filters:
            - not:
               - type: traverse
                 resources: aws_s3_bucket_server_side_encryption_configuration
                 attrs:
                  - rule.apply_server_side_encryption_by_default.sse_algorithm: aws:kms


    This example will traverse multiple hops from and verify attributes at the destination.

    .. code-block:: yaml

      policies:
        - name: app-runner-check-vpc
          description: ensure app runner instances are only connected to the dev vpc
          resource: terraform.aws_app_runner
          filters:
            - network_configuration: present
            - type: traverse
              resources: [aws_apprunner_vpc_connector, aws_subnet, aws_vpc]
              attrs:
               - type: value
                 key: tag:Env
                 value: Dev
                 op: not-equal
    """

    schema = type_schema(
        "traverse",
        resources={
            "oneOf": [
                {"type": "array", "items": {"type": "string"}},
                {"type": "string"},
            ]
        },
        count={"type": "integer"},
        attrs={
            "type": "array",
            "items": {
                "oneOf": [
                    {"$ref": "#/definitions/filters/valuekv"},
                    {"$ref": "#/definitions/filters/value"},
                ]
            },
        },
        required=("resources",),
        **{"count-op": {"$ref": "#/definitions/filters_common/comparison_operators"}},
    )

    _vfilters = None

    @property
    def annotation_key(self):
        return "c7n:%s" % ("-".join(self.type_chain))

    @property
    def type_chain(self):
        type_chain = self.data["resources"]
        if isinstance(type_chain, str):
            type_chain = [type_chain]
        return type_chain

    def process(self, resources, event):
        results = []
        for r in resources:
            working_set = (r,)
            for target_type in self.type_chain:
                working_set = self.resolve_refs(target_type, working_set, event["graph"])
            matched = self.match_attrs(working_set)
            if not self.match_cardinality(matched):
                continue
            if matched:
                r[self.annotation_key] = matched
            results.append(r)
        return results

    def get_attr_filters(self):
        if self._vfilters:
            return self._vfilters
        vfilters = []
        filter_class = ValueFilter
        for v in self.data.get("attrs", []):
            if isinstance(v, dict) and v.get("type"):
                filter_class = self.manager.filter_registry[v["type"]]
            vf = filter_class(v, self.manager)
            vf.annotate = False
            vfilters.append(vf)
        self._vfilters = vfilters
        return vfilters

    def match_cardinality(self, matched):
        count = self.data.get("count", None)
        if count is None:
            if not matched:
                return False
            return True
        op = OPERATORS[self.data.get("count-op", "eq")]
        if op(len(matched), count):
            return True
        return False

    def match_attrs(self, working_set):
        vfilters = self.get_attr_filters()
        results = []
        for w in working_set:
            found = True
            for v in vfilters:
                if not v(w):
                    found = False
                    break
            if not found:
                continue
            results.append(w)
        return results

    def resolve_refs(self, target_type, working_set, graph):
        return itertools.chain(*[graph.get_refs(w, target_type) for w in working_set])
