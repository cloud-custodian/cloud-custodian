# Copyright 2016 Capital One Services, LLC
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

from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session


@resources.register('shield-protection')
class ShieldProtection(QueryResourceManager):

    class resource_type(object):
        service = 'shield'
        enum_spec = ('list_projections', 'Protections', None)
        id = 'Id'
        name = 'Name'
        dimension = None


@resources.register('shield-attack')
class ShieldAttack(QueryResourceManager):

    class resource_type(object):
        service = 'shield'
        enum_spec = ('list_attacks', 'Attacks', None)
        id = 'AttackId'
        date = 'StartTime'
        dimension = None

    def augment(self, resources):
        def _augment(r):
            client = local_session(self.session_factory).client('shield')
            attrs = client.describe_attack(AttackId=r['AttackId'])['Attack']
            r.update(attrs)
            return r
        with self.executor_factory(max_workers=2) as w:
            return list(w.map(_augment, resources))
        
        
        
