# Copyright 2016-2019 Capital One Services, LLC
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

from c7n.actions import (
    ActionRegistry, BaseAction)
from c7n.manager import resources
from c7n.query import QueryResourceManager, ChildResourceManager
from c7n.utils import local_session, type_schema

actions = ActionRegistry('globalaccelerator.actions')

# as of now the only region global accelerator is available is us-west-2
available_ga_region = 'us-west-2'


@resources.register('global-accelerator')
class GlobalAccelerator(QueryResourceManager):

    class resource_type(object):
        service = 'globalaccelerator'
        enum_spec = ('list_accelerators', 'Accelerators', None)
        detail_spec = (
            'describe_accelerator', 'AcceleratorArn',
            'AcceleratorArn', None)
        id = 'AcceleratorArn'
        name = 'Name'
        date = 'CreatedTime'
        dimension = None
        filter_name = None

    def augment(self, resources):
        client = local_session(self.session_factory).client('globalaccelerator',
            region_name=available_ga_region)

        for r in resources:
            extra_ = self.retry(client.describe_accelerator_attributes,
                AcceleratorArn=r['AcceleratorArn'])['AcceleratorAttributes']

            for i in extra_:
                r[i] = extra_[i]

        return resources


@resources.register('global-accelerator-listener')
class AcceleratorListener(ChildResourceManager):

    class resource_type(object):
        service = 'globalaccelerator'
        enum_spec = ('list_listeners', 'Listeners', None)
        detail_spec = (
            'describe_listener', 'ListenerArn',
            'ListenerArn', None)
        id = name = 'ListenerArn'
        date = 'CreatedTime'
        dimension = None
        filter_name = None
        parent_spec = ('global-accelerator', 'AcceleratorArn', None)


@resources.register('global-accelerator-endpoint-group')
class AcceleratorEndpointGroup(ChildResourceManager):

    class resource_type(object):
        service = 'globalaccelerator'
        enum_spec = ('list_endpoint_groups', 'EndpointGroups', None)
        detail_spec = (
            'describe_endpoint_group', 'EndpointGroupArn',
            'EndpointGroupArn', None)
        id = name = 'EndpointGroupArn'
        date = 'CreatedTime'
        dimension = None
        filter_name = None
        parent_spec = ('global-accelerator-listener', 'ListenerArn', None)


@AcceleratorEndpointGroup.action_registry.register('delete')
class DeleteEndpointGroup(BaseAction):
    '''Deletes global-accelerator-endpoint(s)

    :example:

    .. code-block: yaml

        policies:
          - name: delete-global-accelerator-endpoint
            resource: global-accelerator-endpoint
            actions:
              - delete
            filters:
              - EndpointGroupRegion: us-west-2
    '''
    schema = type_schema('delete')
    permissions = ('globalaccelerator:DeleteEndpointGroup',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('globalaccelerator',
            region_name=available_ga_region)
        for m in resources:
            # this API doesn't really throw any exceptions, even if somehow the endpoint group
            # doesn't exist
            client.delete_endpoint_group(
                EndpointGroupArn=m['EndpointGroupArn'])


@AcceleratorListener.action_registry.register('delete')
class DeleteListener(BaseAction):
    '''Deletes global-accelerator-listener(s)

    :example:

    .. code-block: yaml

        policies:
          - name: delete-global-accelerator-listener
            resource: global-accelerator-listener
            actions:
              - delete
            filters:
              - ClientAffinity: NONE
    '''
    schema = type_schema('delete')
    permissions = ('globalaccelerator:DeleteListener',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('globalaccelerator',
            region_name=available_ga_region)
        for m in resources:
            try:
                client.delete_listener(ListenerArn=m['ListenerArn'])
            # deleting a listener with endpoints is forbidden
            except client.exceptions.AssociatedEndpointGroupFoundException as e:
                msg = "Can not delete listener with endpoint groups ListenerArn: %s error:%s" % (
                    m['ListenerArn'], e)
                self.log.warning(msg)


@GlobalAccelerator.action_registry.register('delete')
class DeleteAccelerator(BaseAction):
    '''Deletes global-accelerator(s)

    :example:

    .. code-block: yaml

        policies:
          - name: delete-global-accelerator
            resource: global-accelerator
            filters:
              - Enabled: False
            actions:
              - delete
    '''
    schema = type_schema('delete')
    permissions = ('globalaccelerator:DeleteAccelerator',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('globalaccelerator',
            region_name=available_ga_region)

        for m in resources:
            try:
                client.delete_accelerator(AcceleratorArn=m['AcceleratorArn'])
            except client.exceptions.AcceleratorNotDisabledException as e:
                msg = "Can not delete enabled accelerator AcceleratorArn: %s error:%s" % (
                    m['AcceleratorArn'], e)
                self.log.warning(msg)


@GlobalAccelerator.action_registry.register('set-global-accelerator')
class ModifyAccelerator(BaseAction):
    '''Modifies an accelerator instance based on specified parameter
    using UpdateAccelerator and UpdateAcceleratorAttributes.

    'update-accelerator-attributes' and 'uppate-accelerator' are arrays with
    key value pairs that should be set to the property and value you wish to
    modify.

    :example:

    .. code-block:: yaml

            policies:
              - name: disable-accelerator-protection
                resource: global-accelerator-listener
                filters:
                  - enabled: true
                actions:
                  - type: set-global-accelerator
                    update:
                      - property: 'Enabled'
                        value: false

    .. code-block:: yaml

            policies:
              - name: disable-accelerator-flowlogs-protection
                resource: global-accelerator-listener
                actions:
                  - type: update-accelerator-attributes
                    update:
                      - property: 'FlowLogsEnabled'
                        value: false
    '''

    schema = type_schema(
        'set-global-accelerator', **{
            'update-accelerator-attributes': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'property': {'type': 'string', 'enum': [
                            'FlowLogsEnabled',
                            'FlowLogsS3Bucket',
                            'FlowLogsS3Prefix']},
                        'value': {}
                    },
                },
            },
            'update-accelerator': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'property': {'type': 'string', 'enum': [
                            'Enabled']},
                        'value': {}
                    },
                },
            }
        }
    )

    permissions = ('globalaccelerator:UpdateAccelerator',
        'globalaccelerator:UpdateAcceleratorAttributes')

    def process(self, resources):
        c = local_session(self.manager.session_factory).client(
            'globalaccelerator', region_name=available_ga_region)
        update_iteration = (
            ('update-accelerator-attributes', c.update_accelerator_attributes),
            ('update-accelerator', c.update_accelerator))

        for (key, update_method) in update_iteration:

            for r in resources:
                param = {}
                schema_attributes = []

                if key in self.data:
                    schema_attributes = self.data.get(key)

                for update in schema_attributes:
                    update_prop = update['property']
                    if r.get(update_prop) != update['value']:
                        param[update_prop] = update['value']

                if not param:
                    continue
                param['AcceleratorArn'] = r['AcceleratorArn']
                update_method(**param)


@AcceleratorEndpointGroup.action_registry.register('modify')
class ModifyAcceleratorEndpoint(BaseAction):
    '''Modifies an accelerator endpoint based on specified parameter
    using UpdateEndpointGroup.


    :example:

    .. code-block:: yaml
        policies:
          - name: set-global-accelerator-endpoint-threshold
            resource: global-accelerator-endpoint-group
            actions:
              - type: modify
                update:
                  - property: 'ThresholdCount'
                    value: 5
    '''

    update_accelerator_endpoint = {
        'type': 'array',
        'items': {
            'type': 'object',
            'properties': {
                'property': {
                    'type': 'string',
                    'enum': [
                        'TrafficDialPercentage',
                        'HealthCheckPort',
                        'HealthCheckProtocol',
                        'HealthCheckPath',
                        'HealthCheckIntervalSeconds',
                        'ThresholdCount',
                    ]
                },
                'value': {},
                'EndpointConfigurations': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'property': {'type': 'string', 'enum': ['EndpointId', 'Weight']},
                            'value': {},
                        }
                    },
                },
            },
        },
    }
    schema = type_schema(
        'modify', **{
            'update-accelerator-endpoint': update_accelerator_endpoint
        }
    )

    permissions = ('globalaccelerator:UpdateEndpointGroup')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('globalaccelerator',
            region_name=available_ga_region)

        for endpoint_group_resource in resources:

            existing_endpoint_ids = set(())
            param = {}

            for endpoint_data in endpoint_group_resource['EndpointDescriptions']:
                existing_endpoint_ids.add(endpoint_data['EndpointId'])

            for update in self.data.get('update-accelerator-endpoint'):
                if 'property' in update:
                    update_prop = update['property']
                    if update_prop in endpoint_group_resource and (
                            endpoint_group_resource[update_prop] != update['value']):
                        param[update_prop] = update['value']

                elif 'EndpointConfigurations' in update:
                    for i in update['EndpointConfigurations']:

                        # the EndpointId has to be in the resource
                        if i['EndpointId'] in existing_endpoint_ids:
                            if 'EndpointConfigurations' not in param:
                                param['EndpointConfigurations'] = []

                            param['EndpointConfigurations'].append({
                                'EndpointId': i['EndpointId'],
                                'Weight': i['Weight']
                            })

            if not param:
                continue

            param['EndpointGroupArn'] = endpoint_group_resource['EndpointGroupArn']

            # there's no exceptions to catch here. Bad update parameters are ignored and
            # a non existant ARN wouldn't make it this far
            client.update_endpoint_group(**param)


@AcceleratorListener.action_registry.register('modify')
class ModifyAcceleratorListener(BaseAction):
    '''Modifies an accelerator listener based on specified parameter
    using UpdateListener.


    :example:

    .. code-block:: yaml
        policies:
          - name: set-global-accelerator-listener-protocol
            resource: global-accelerator-listener
            actions:
              - type: modify
                update:
                  - property: Protocol
                    value: TCP
            filters:
                  - Health: UDP
    '''
    schema = type_schema('modify',
        **{'update-accelerator-listener': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'property': {'type': 'string', 'enum': [
                        'PortRanges',
                        'Protocol',
                        'ClientAffinity',
                    ]},
                    'value': {},
                    'PortRanges': {
                        'type': 'arrary',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'FromPort': {'type': 'string'},
                                'ToPort': {'type': 'string'},
                            }
                        },
                    },
                },
            },
        }})

    permissions = ('globalaccelerator:UpdateListener')

    def process(self, resources):

        c = local_session(self.manager.session_factory).client('globalaccelerator',
        region_name=available_ga_region)

        for r in resources:
            param = {}
            for update in self.data.get('update-accelerator-listener'):
                port_ranges = update.get('PortRanges', [])
                if port_ranges:
                    param['PortRanges'] = port_ranges
                else:
                    if r[update['property']] != update['value']:
                        param[update['property']] = update['value']
            if not param:
                continue
            param['ListenerArn'] = r['ListenerArn']
            try:
                c.update_listener(**param)
            except c.exceptions.ListenerNotFoundException:
                raise
