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


from c7n.exceptions import PolicyValidationError
from c7n.query import QueryResourceManager
from c7n.manager import resources
from c7n.utils import chunks, get_retry, local_session, type_schema
from c7n.actions import Action

from .aws import shape_validate
from .ec2 import EC2


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
        type = "parameter"

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
        type = "managed-instance"

    permissions = ('ssm:DescribeInstanceInformation',)


@EC2.action_registry.register('send-command')
@ManagedInstance.action_registry.register('send-command')
class SendCommand(Action):
    """Run an SSM Automation Document on an instance.

    :Example:

    Find ubuntu 18.04 instances are active with ssm.

    .. code-block:: yaml

        policies:
          - name: ec2-osquery-install
            resource: ec2
            filters:
              - type: ssm
                key: PingStatus
                value: Online
              - type: ssm
                key: PlatformName
                value: Ubuntu
              - type: ssm
                key: PlatformVersion
                value: 18.04
            actions:
              - type: send-command
                command:
                  DocumentName: AWS-RunShellScript
                  Parameters:
                    commands:
                      - wget https://pkg.osquery.io/deb/osquery_3.3.0_1.linux.amd64.deb
                      - dpkg -i osquery_3.3.0_1.linux.amd64.deb
    """

    schema = type_schema(
        'send-command',
        command={'type': 'object'},
        required=('command',))

    permissions = ('ssm:SendCommand',)
    shape = "SendCommandRequest"
    annotation = 'c7n:SendCommand'

    def validate(self):
        shape_validate(self.data['command'], self.shape, 'ssm')
        # If used against an ec2 resource, require an ssm status filter
        # to ensure that we're not trying to send commands to instances
        # that aren't in ssm.
        if self.manager.type != 'ec2':
            return

        found = False
        for f in self.manager.iter_filters():
            if f.type == 'ssm':
                found = True
                break
        if not found:
            raise PolicyValidationError(
                "send-command requires use of ssm filter on ec2 resources")

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ssm')
        for resource_set in chunks(resources, 50):
            self.process_resource_set(client, resource_set)

    def process_resource_set(self, client, resources):
        command = dict(self.data['command'])
        command['InstanceIds'] = [
            r['InstanceId'] for r in resources]
        result = client.send_command(**command).get('Command')
        for r in resources:
            r.setdefault('c7n:SendCommand', []).append(result['CommandId'])


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
        arn = False
    permissions = ('ssm:DescribeActivations',)


@SSMActivation.action_registry.register('delete')
class DeleteSSMActivation(Action):
    schema = type_schema('delete')
    permissions = ('ssm:DeleteActivation',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ssm')
        for a in resources:
            client.delete_activation(ActivationId=a["ActivationId"])
