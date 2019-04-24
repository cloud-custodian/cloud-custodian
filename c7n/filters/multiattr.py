# Copyright 2019 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
