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
from __future__ import absolute_import, division, print_function, unicode_literals

from c7n.manager import resources
from c7n.query import QueryResourceManager


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
        detail_spec = ('describe_attack', 'AttackId', 'AttackId', 'Attack')
        id = 'AttackId'
        date = 'StartTime'
        dimension = None
