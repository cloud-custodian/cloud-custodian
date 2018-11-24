# Copyright 2016-2017 Capital One Services, LLC
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


from c7n.query import QueryResourceManager
from c7n.manager import resources
from c7n.utils import get_retry, local_session, type_schema
from c7n.actions import Action


@resources.register('ssm-parameter')
class SSMParameter(QueryResourceManager):
    class resource_type(object):
        service = 'ssm'
        enum_spec = ('describe_parameters', 'Parameters', None)
        name = "Name"
        id = "Name"
        filter_name = None
        dimension = None
        universal_taggable = True

    retry = staticmethod(get_retry(('Throttled',)))
    permissions = ('ssm:GetParameters',
                   'ssm:DescribeParameters')


@resources.register('ssm-managed-instance')
class ManagedInstance(QueryResourceManager):
    class resource_type(object):
        service = 'ssm'
        enum_spec = ('describe_instance_information', 'InstanceInformationList', None)
        id = 'InstanceId'
        name = 'Name'
        date = 'RegistrationDate'
        dimension = None
        filter_name = None
    permissions = ('ssm:DescribeInstanceInformation',)


@resources.register('ssm-activation')
class SSMActivation(QueryResourceManager):
    class resource_type(object):
        service = 'ssm'
        enum_spec = ('describe_activations', 'ActivationList', None)
        id = 'ActivationId'
        name = 'Description'
        date = 'CreatedDate'
        dimension = None
        filter_name = None
    permissions = ('ssm:DescribeActivations',)


@SSMActivation.action_registry.register('delete')
class DeleteSSMActivation(Action):
    schema = type_schema('delete')
    permissions = ('ssm:DeleteActivation',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ssm')
        for a in resources:
            client.delete_activation(ActivationId=a["ActivationId"])
