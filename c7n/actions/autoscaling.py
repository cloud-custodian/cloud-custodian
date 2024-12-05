# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .core import BaseAction
from c7n.utils import local_session, type_schema

# parameters to save to/restore from a tag
tag_params = ['Min', 'Max', 'Desired']


class AutoscalingBase(BaseAction):
    """Action to resize the min/max/desired count in an application autoscaling target

    There are several ways to use this action:

    1. apply a fixed resize of min, max or desired, optionally saving the
       previous values to a named tag (for restoring later):

    .. code-block:: yaml

            policies:
              - name: offhours-ecs-off
                resource: ecs-service
                filters:
                  - type: offhour
                    offhour: 19
                    default_tz: bst
                actions:
                  - type: resize
                    min-capacity: 0
                    desired: 0
                    save-options-tag: OffHoursPrevious
                    suspend-scaling: true

    2. restore previous values for min/max/desired from a tag:

    .. code-block:: yaml

            policies:
              - name: offhours-ecs-on
                resource: ecs-service
                filters:
                  - type: onhour
                    onhour: 8
                    default_tz: bst
                actions:
                  - type: resize
                    restore-options-tag: OffHoursPrevious
                    restore-scaling: true

    """

    schema = type_schema(
        'resize',
        **{
            'min-capacity': {'type': 'integer', 'minimum': 0},
            'max-capacity': {'type': 'integer', 'minimum': 0},
            'desired': {
                "anyOf": [
                    {'enum': ["current"]},
                    {'type': 'integer', 'minimum': 0}
                ]
            },
            'save-options-tag': {'type': 'string'},
            'restore-options-tag': {'type': 'string'},
            'suspend-scaling': {'type': 'boolean'},
            'restore-scaling': {'type': 'boolean'},
        }
    )
    autoscaling_permissions = (
        'application-autoscaling:DescribeScalableTargets',
        'application-autoscaling:RegisterScalableTarget',
    )

    def get_permissions(self):
        return self.autoscaling_permissions + self.permissions

    @property
    def scalable_dimension(self):
        """ the scalable dimension for the Application Autoscaling target """

    @property
    def service_namespace(self):
        """ the service namespace for interacting with Application Autoscaling """

    def get_resource_id(self, resource):
        """ return the id for the provided resource """
        raise NotImplementedError

    def get_resource_tag(self, resource, key):
        """ return the tag for the provided resource """
        raise NotImplementedError

    def get_resource_desired(self, resource):
        """ return the current desired value for the provided resource """
        raise NotImplementedError

    def set_resource_tag(self, resource, key, value):
        """ set the tag for the provided resource """
        """ default implementation is to use `UniversalTag` """
        tag_action = self.manager.action_registry.get('tag')
        tag_action({'key': key, 'value': value}, self.manager).process([resource])

    def set_resource_desired(self, resource, desired):
        """ set the desired for the provided resource """
        raise NotImplementedError

    def process_suspend_scaling(self, target):
        self.update_scaling_suspended_state(target, True)

    def process_restore_scaling(self, target):
        self.update_scaling_suspended_state(target, False)

    def update_scaling_suspended_state(self, target, suspended_value):
        resource_id = target['ResourceId']
        update_suspended_state = {}
        for state, suspended in target['SuspendedState'].items():
            if suspended != suspended_value:
                update_suspended_state[state] = suspended_value

        if update_suspended_state:
            self.log.debug('Target %s updating suspended_state=%s' %
                (resource_id, update_suspended_state))

            client = local_session(self.manager.session_factory).client(
                'application-autoscaling')
            client.register_scalable_target(
                ServiceNamespace=self.service_namespace,
                ResourceId=resource_id,
                ScalableDimension=self.scalable_dimension,
                SuspendedState=update_suspended_state,
            )

    def update_scaling_options(self, resource, target, new_min, new_max, new_desired):
        updated = False

        cur_min = target['MinCapacity']
        cur_max = target['MaxCapacity']
        cur_desired = self.get_resource_desired(resource)

        if new_desired is not None and new_desired != cur_desired:
            self.log.debug('Target %s updating desired=%d' %
                (target['ResourceId'], new_desired))
            self.set_resource_desired(resource, new_desired)
            updated = True

            # Lower MinCapacity if desired is below
            if new_min is not None:
                new_min = min(new_desired, new_min)
            else:
                new_min = min(new_desired, cur_min)

        capacity_changes = {}
        if new_min is not None and new_min != cur_min:
            capacity_changes['MinCapacity'] = new_min
        if new_max is not None and new_max != cur_max:
            capacity_changes['MaxCapacity'] = new_max

        if capacity_changes:
            resource_id = target['ResourceId']
            self.log.debug('Target %s updating min=%s, max=%s'
                % (resource_id, new_min, new_max))
            client = local_session(self.manager.session_factory).client(
                'application-autoscaling')
            client.register_scalable_target(
                ServiceNamespace=self.service_namespace,
                ResourceId=resource_id,
                ScalableDimension=self.scalable_dimension,
                **capacity_changes,
            )
            updated = True

        return updated

    def process_restore_scaling_options_from_tag(self, resource, target):
        # we want to restore all ASG size params from saved data
        self.log.debug(
            'Want to restore resource %s from tag %s' %
            (target['ResourceId'], self.data['restore-options-tag']))
        restore_options = self.get_resource_tag(
            resource,
            self.data['restore-options-tag'])

        new_min, new_max, new_desired = None, None, None
        if restore_options is not None:
            for field in restore_options.split(':'):
                (param, value) = field.split('=')
                if param == 'Min':
                    new_min = int(value)
                elif param == 'Max':
                    new_max = int(value)
                elif param == 'Desired':
                    new_desired = int(value)

            return self.update_scaling_options(resource, target, new_min, new_max, new_desired)

        return False

    def process_update_scaling_options(self, resource, target):
        new_min = self.data.get('min-capacity', None)
        new_max = self.data.get('max-capacity', None)
        new_desired = self.data.get('desired', None)
        return self.update_scaling_options(resource, target, new_min, new_max, new_desired)

    def process_save_scaling_options_to_tag(self, resource, target):
        current_desired = self.get_resource_desired(resource)
        # save existing params to a tag before changing them
        self.log.debug('Saving resource %s size to tag %s' %
            (target['ResourceId'], self.data['save-options-tag']))
        self.set_resource_tag(
            resource,
            self.data['save-options-tag'],
            'Min=%d:Max=%d:Desired=%d' % (
                target['MinCapacity'],
                target['MaxCapacity'],
                current_desired))

    def process(self, resources):
        resources_by_id = {self.get_resource_id(r): r for r in resources}
        resource_ids = list(resources_by_id.keys())
        client = local_session(self.manager.session_factory).client(
            'application-autoscaling')
        paginator = client.get_paginator('describe_scalable_targets')
        response_iterator = paginator.paginate(
            ServiceNamespace=self.service_namespace,
        )

        for response in response_iterator:
            for target in response['ScalableTargets']:
                resource_id = target['ResourceId']

                if resource_id not in resource_ids:
                    continue

                if target['ScalableDimension'] != self.scalable_dimension:
                    continue

                resource = resources_by_id[resource_id]

                if self.data.get('suspend-scaling'):
                    # suspend scaling activities
                    self.process_suspend_scaling(target)
                if self.data.get('restore-scaling'):
                    # restore scaling activities
                    self.process_restore_scaling(target)

                if 'restore-options-tag' in self.data:
                    # resize based on prior TAG values
                    updated = self.process_restore_scaling_options_from_tag(resource, target)
                else:
                    # resize based on params in policy
                    updated = self.process_update_scaling_options(resource, target)

                    if 'save-options-tag' in self.data and updated:
                        # save prior values as tags
                        self.process_save_scaling_options_to_tag(resource, target)
