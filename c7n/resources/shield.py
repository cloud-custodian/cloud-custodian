# Copyright 2015-2017 Capital One Services, LLC
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

from botocore.exceptions import ClientError
from c7n.actions import BaseAction
from c7n.filters import Filter
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, type_schema


@resources.register('shield-protection')
class ShieldProtection(QueryResourceManager):

    class resource_type(object):
        service = 'shield'
        enum_spec = ('list_protections', 'Protections', None)
        id = 'Id'
        name = 'Name'
        dimension = None
        filter_name = None


@resources.register('shield-attack')
class ShieldAttack(QueryResourceManager):

    class resource_type(object):
        service = 'shield'
        enum_spec = ('list_attacks', 'Attacks', None)
        detail_spec = ('describe_attack', 'AttackId', 'AttackId', 'Attack')
        name = id = 'AttackId'
        date = 'StartTime'
        dimension = None
        filter_name = 'ResourceArns'
        filter_type = 'list'


class IsShieldProtected(Filter):

    permissions = ('shield:ListProtections',)
    schema = type_schema('shield-enabled', state={'type': 'boolean'})

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client(
            'shield', region_name='us-east-1')
        protections = client.list_protections().get('Protections', ())
        protected_resources = {p['ResourceArn'] for p in protections}

        state = self.data.get('state', False)
        results = []

        for r in resources:
            arn = self.manager.get_arn(r)
            r['c7n:ShieldProtected'] = shielded = arn in protected_resources
            if shielded and state:
                results.append(r)
            elif not shielded and not state:
                results.append(r)
        return results


class SetShieldProtection(BaseAction):
    """Enable shield protection on applicable resource.
    """

    permissions = ('shield:CreateProtection', 'shield:ListProtections',)
    schema = type_schema(
        'set-shield',
        state={'type': 'boolean'})

    def process(self, resources):
        client = local_session(self.manager.session_factory).client(
            'shield', region_name='us-east-1')
        model = self.manager.get_model()
        protections = client.list_protections().get('Protections', ())
        protected_resources = {p['ResourceArn'] for p in protections}

        for r in resources:
            arn = self.manager.get_arn(r)
            if arn in protected_resources:
                continue
            try:
                client.create_protection(
                    Name=r[model.name],
                    ResourceArn=arn)
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceAlreadyExistsException':
                    continue
                raise
