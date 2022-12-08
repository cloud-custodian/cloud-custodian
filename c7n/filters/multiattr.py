# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.exceptions import PolicyValidationError
from .core import Filter, ValueFilter


class MultiAttrFilter(Filter):

    multi_attrs = set()

    def validate(self):
        delta = set(self.data.keys()).difference(self.multi_attrs)
        delta.remove('type')
        if 'match-operator' in delta:
            delta.remove('match-operator')
        if delta:
            raise PolicyValidationError(
                "filter:{} unknown keys {} on {}".format(
                    self.type, ", ".join(delta), self.manager.data))

    def process(self, resources, event=None):
        matched = []
        attr_filters = list(self.get_attr_filters())
        match_op = self.data.get('match-operator', 'and') == 'and' and all or any
        for r in resources:
            target = self.get_target(r)
            if match_op([bool(af(target)) for af in attr_filters]):
                matched.append(r)
        return matched

    def get_target(self, resource):
        """Return the resource, or related resource that should be attribute matched.
        """
        return resource

    def get_attr_filters(self):
        """Return an iterator resource attribute filters configured.
        """
        for f in self.data.keys():
            if f not in self.multi_attrs:
                continue
            fv = self.data[f]
            if isinstance(fv, dict):
                fv['key'] = f
            else:
                fv = {f: fv}
            vf = ValueFilter(fv)
            vf.annotate = False
            yield vf
