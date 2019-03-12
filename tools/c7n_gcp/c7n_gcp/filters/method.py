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

import logging

from c7n.filters import Filter as BaseFilter, ValueFilter
from c7n.utils import local_session, chunks


log = logging.getLogger('custodian.gcp.filters')


class Filter(BaseFilter):
    pass


class MethodFilter(Filter):
    """Filter resources via an api call per resource.

    Also annotate the resource for subsequent filters of the same type
    to bypass the api calls.
    """

    # method we'll be invoking
    method_spec = ()

    # batch size
    chunk_size = 20

    value_filter = None

    def __init__(self, data, manager):
        super(MethodFilter, self).__init__(data, manager)
        self.value_filter = ValueFilter(data, manager)

    def validate(self):
        if not self.method_spec:
            raise NotImplementedError("subclass must define method_spec")
        if ('annotation_key' not in self.method_spec or
                'op' not in self.method_spec):
            raise NotImplementedError("missing required in method_spec")
        return self

    def process(self, resources, event=None):
        m = self.manager.get_model()
        session = local_session(self.manager.session_factory)
        client = session.client(m.service, m.version, m.component)
        result_set = []

        for resource_set in chunks(resources, self.chunk_size):
            result_set.extend(
                list(self.process_resource_set(client, m, resource_set)))
        return result_set

    def process_resource_set(self, client, model, resources):
        op_name = self.method_spec['op']
        result_key = self.method_spec.get('result_key')
        annotation_key = self.method_spec.get('annotation_key')
        for r in resources:
            params = self.get_resource_params(model, r)
            result = client.execute_command(op_name, params)
            if result_key:
                r[annotation_key] = result.get(result_key)
            else:
                r[annotation_key] = result
            if self.process_resource(r):
                yield r

    def process_resource(self, r):
        annotation_key = self.method_spec.get('annotation_key')
        return self.value_filter(r[annotation_key])

    def get_resource_params(self, m, r):
        raise NotImplementedError("subclass responsibility")
