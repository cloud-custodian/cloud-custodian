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

from c7n.actions import Action as BaseAction
from c7n.utils import local_session, chunks

log = logging.getLogger('custodian.k8s.actions')


class Action(BaseAction):
    pass


class MethodAction(Action):
    method_spec = ()
    chunk_size = 20

    def validate(self):
        if not self.method_spec:
            raise NotImplementedError("subclass must define method_spec")
        return self

    def process(self, resources):
        m = self.manager.get_model()
        session = local_session(self.manager.session_factory)
        client = session.client(m.group, m.version)
        for resource_set in chunks(resources, self.chunk_size):
            self.process_resource_set(client, m, resource_set)

    def process_resource_set(self, client, model, resources):
        op_name = self.method_spec['op']
        for r in resources:
            log.info('%s %s' % (op_name, r))
        pass
