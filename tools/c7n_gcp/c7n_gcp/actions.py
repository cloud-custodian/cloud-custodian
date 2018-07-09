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

from c7n.actions import Action as BaseAction
from c7n.utils import local_session, chunks


class Action(BaseAction):
    pass


class MethodAction(Action):
    """Invoke an api call on each resource.

    Quite a number of procedural actions are simply invoking an api
    call on a filtered set of resources. The exact handling is mostly
    boilerplate at that point following an 80/20 rule. This class is
    an encapsulation of the 80%.
    """

    # method we'll be invoking
    method_spec = ()

    # batch size
    chunk_size = 20

    # implicitly filter resources by state, (attr_name, (valid_enum))
    attr_filter = ()

    def validate(self):
        if not self.method_spec:
            raise NotImplementedError("subclass must define method_spec")
        return self

    def filter_resources(self, resources):
        rcount = len(resources)
        attr_name, valid_enum = self.attr_filter
        resources = [r for r in resources if r.get(attr_name) in valid_enum]
        if len(resources) != rcount:
            self.log.warning(
                "%s implicity filtered %d resources to %d by values %s",
                rcount,
                len(resources),
                ", ".join(map(str, valid_enum))
            )
        return resources

    def process(self, resources):
        if self.attr_filter:
            resources = self.filter_resources(resources)
        m = self.manager.get_model()
        session = local_session(self.manager.session_factory)
        client = session.client(m.service, m.version, m.component)
        for resource_set in chunks(resources, self.chunk_size):
            self.process_resource_set(client, m, resource_set)

    def process_resource_set(self, client, model, resources):
        op_name = self.method_spec['op']
        result_key = self.method_spec.get('result_key')
        annotation_key = self.method_spec.get('annotation_key')
        for r in resources:
            params = self.get_resource_params(model, r)
            result = client.execute_command(op_name, params)
            if result_key and annotation_key:
                r[annotation_key] = result.get(result_key)

    def get_resource_params(self, m, r):
        raise NotImplementedError("subclass responsibility")
