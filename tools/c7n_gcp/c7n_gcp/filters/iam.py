# Copyright 2018 Capital One Services, LLC
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
#

from c7n.utils import type_schema

from .method import MethodFilter


class IamAccess(MethodFilter):
    """Filter resources by their iam policy.

    users:
      - allowed-domain
    service-account:
      - allowed-projects
      - allowed-project-ids
      - allowed-roles
    """

    schema = type_schema(
        'iam-policy',
        role={'type': 'string'},
        member={'type': 'string'},
        member_type={'enum': ['serviceAccount', 'user', 'group', 'domain']},
        scope={'enum': ['binding', 'member']})

    method_spec = {
        'op': 'getIamPolicy',
        'annotation_key': 'c7n:iam-policy'}

    def process_resource(self, r):
        scope = self.data.get('scope', 'binding')
        annotation_key = self.method_spec.get('annotation_key')

        bindings = r[annotation_key]['bindings']

        if scope == 'binding':
            entities = list(bindings.values())
        elif scope == 'member':
            entities = []
            for binding in bindings.values():
                for member in binding['members']:
                    entities.append(dict(member=member, role=binding['role']))
        self.value_filter.annotate = False
        matched = []
        for e in entities:
            matched.append(self.value_filter(e))

        if matched:
            r.setdefault('c7n:iam-matched-%s' % scope, []).extend(matched)
        return bool(matched)

    def get_resource_params(self, m, r):
        # subclass override
        raise NotImplementedError(
            "iam-filter requires resource implementation of get_resource_params")
