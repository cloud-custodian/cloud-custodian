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
from c7n.resources import aws
import copy

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

    'update-accelerator-attributes' and 'uppate-accelerator' are
    dictionaries with the values you wish to modify.

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
                      - 'Enabled': false

    .. code-block:: yaml

            policies:
              - name: disable-accelerator-flowlogs-protection
                resource: global-accelerator-listener
                actions:
                  - type: update-accelerator-attributes
                    update:
                      - 'FlowLogsEnabled': false
    '''

    schema = type_schema(
        'set-global-accelerator', **{
            'update-accelerator-attributes': {
                'type': 'object',
            },
            'update-accelerator': {
                'type': 'object',
            }
        }
    )

    permissions = ('globalaccelerator:UpdateAccelerator',
        'globalaccelerator:UpdateAcceleratorAttributes')

    def validate(self):
        for (type_schema_action, shape_name) in (
            ('update-accelerator-attributes', 'UpdateAcceleratorAttributesRequest'),
            ('update-accelerator', 'UpdateAcceleratorRequest')
        ):

            if type_schema_action not in self.data:
                continue

            api_call_shape = copy.deepcopy(self.data[type_schema_action])
            api_call_shape['AcceleratorArn'] = 'PlaceHolderARN'
            aws.shape_validate(api_call_shape, shape_name, 'globalaccelerator')

    def process(self, resources):
        c = local_session(self.manager.session_factory).client(
            'globalaccelerator', region_name=available_ga_region)

        update_iteration = (
            ('update-accelerator-attributes', c.update_accelerator_attributes),
            ('update-accelerator', c.update_accelerator))

        for (key, update_method) in update_iteration:
            for r in resources:
                api_call_param = {}
                requested_change_param = self.data.get(key, [])
                for update_prop, requested_val in requested_change_param.items():
                    if r.get(update_prop) != requested_val:
                        api_call_param[update_prop] = requested_val

                if not api_call_param:
                    continue
                api_call_param['AcceleratorArn'] = r['AcceleratorArn']

                update_method(**api_call_param)


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
                  - 'ThresholdCount': 5
    '''

    schema = type_schema(
        'modify', **{
            'update-accelerator-endpoint': {'type': 'object'}
        }
    )

    permissions = ('globalaccelerator:UpdateEndpointGroup')

    def validate(self):

        requested_change_param = self.data.get('update-accelerator-endpoint')
        if not requested_change_param:
            return

        api_call_shape = copy.deepcopy(requested_change_param)
        api_call_shape['EndpointGroupArn'] = 'PlaceHolderEndpointGroupArn'
        aws.shape_validate(api_call_shape, 'UpdateEndpointGroupRequest', 'globalaccelerator')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('globalaccelerator',
            region_name=available_ga_region)

        for endpoint_group_resource in resources:

            api_call_param = {}
            requested_change_param = self.data.get('update-accelerator-endpoint', [])

            for update_prop, requested_val in requested_change_param.items():
                if update_prop == 'EndpointConfigurations':
                    api_call_param[update_prop] = requested_val
                elif endpoint_group_resource.get(update_prop) != requested_val:
                    api_call_param[update_prop] = requested_val

            if not api_call_param:
                continue
            api_call_param['EndpointGroupArn'] = endpoint_group_resource['EndpointGroupArn']

            # there's no exceptions to catch here. Bad update parameters are ignored and
            # a non existant ARN wouldn't make it this far
            client.update_endpoint_group(**api_call_param)


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
                  - Protocol: TCP
            filters:
                  - Health: UDP
    '''
    schema = type_schema('modify',
        **{'update-accelerator-listener': {
            'type': 'object',
        }})

    permissions = ('globalaccelerator:UpdateListener')

    def validate(self):

        requested_change_param = self.data.get('update-accelerator-listener')
        if not requested_change_param:
            return

        api_call_shape = copy.deepcopy(requested_change_param)
        api_call_shape['ListenerArn'] = 'PlaceHolderARN'
        aws.shape_validate(api_call_shape, 'UpdateListenerRequest', 'globalaccelerator')

    def process(self, resources):

        c = local_session(self.manager.session_factory).client('globalaccelerator',
        region_name=available_ga_region)

        for r in resources:
            api_call_param = {}
            requested_change_param = self.data.get('update-accelerator-listener')
            for update_prop, requested_val in requested_change_param.items():
                if r.get(update_prop) != requested_val:
                    api_call_param[update_prop] = requested_val

            if not api_call_param:
                continue
            api_call_param['ListenerArn'] = r['ListenerArn']

            try:
                c.update_listener(**api_call_param)
            except c.exceptions.ListenerNotFoundException:
                msg = "Can not find listener to modify. ListenerArn: %s" % (r['ListenerArn'],)
                self.log.warning(msg)
