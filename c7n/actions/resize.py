# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from abc import abstractmethod
from .core import BaseAction
from c7n.utils import local_session, type_schema

class ResizeAutoscalingTarget(BaseAction):
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
    @abstractmethod
    def scalable_dimension(self):
      """ the scalable dimension for the Application Autoscaling target """

    @property
    @abstractmethod
    def service_namespace(self):
      """ the service namespace for interacting with Application Autoscaling """

    @abstractmethod
    def get_resource_id(self, resource):
      """ return the id for the provided resource """
      raise NotImplementedError

    @abstractmethod
    def get_resource_tag(self, resource, key):
      """ return the tag for the provided resource """
      raise NotImplementedError

    @abstractmethod
    def get_resource_desired(self, resource):
      """ return the current desired value for the provided resource """
      raise NotImplementedError

    @abstractmethod
    def set_resource_tag(self, resource, key, value):
      """ set the tag for the provided resource """
      raise NotImplementedError

    @abstractmethod
    def set_resource_desired(self, resource, desired):
      """ set the desired for the provided resource """
      raise NotImplementedError

    def process(self, resources):
        # parameters to save to/restore from a tag
        tag_params = ['Min', 'Max', 'Desired']

        resources_by_id = {self.get_resource_id(r):r for r in resources}

        client = local_session(self.manager.session_factory).client(
            'application-autoscaling')
        paginator = client.get_paginator('describe_scalable_targets')
        response_iterator = paginator.paginate(
            ServiceNamespace=self.service_namespace,
            ResourceIds=list(resources_by_id.keys()),
            ScalableDimension=self.scalable_dimension,
        )

        for response in response_iterator:
          for target in response['ScalableTargets']:
            resource_id = target['ResourceId']
            resource = resources_by_id[resource_id]
            current_desired = self.get_resource_desired(resource)
            update = {
              'Min': target['MinCapacity'],
              'Max': target['MaxCapacity'],
              'Desired': current_desired,
            }

            if 'restore-options-tag' in self.data:
                # we want to restore all ASG size params from saved data
                self.log.debug(
                    'Want to restore target %s size from tag %s' %
                    (resource_id, self.data['restore-options-tag']))
                restore_options = self.get_resource_tag(resource, self.data['restore-options-tag'])
                if restore_options is not None:
                    for field in restore_options.split(':'):
                        (param, value) = field.split('=')
                        if param in tag_params:
                            update[param] = int(value)

            else:
                # we want to resize, parse provided params
                if 'min-capacity' in self.data:
                    update['Min'] = self.data['min-capacity']

                if 'max-capacity' in self.data:
                    update['Max'] = self.data['max-capacity']

                if 'desired' in self.data and type(self.data['desired']) == int:
                    update['Desired'] = self.data['desired']
                    # Lower MinCapacity if desired is below 
                    update['Min'] = min(self.data['desired'], update['Min'])

            if update['Min'] == target['MinCapacity']:
                del update['Min']
            if update['Max'] == target['MaxCapacity']:
                del update['Max']
            if update['Desired'] == current_desired:
                del update['Desired']

            suspended_state = {}
            if 'suspend-scaling' in self.data and self.data['suspend-scaling']:
              for state, suspended in target['SuspendedState'].items():
                if not suspended:
                  suspended_state[state] = True
                client.register_scalable_target(
                  ServiceNamespace=self.service_namespace,
                  ResourceId=resource_id,
                  ScalableDimension=self.scalable_dimension,
                  SuspendedState={
                    'DynamicScalingInSuspended': True,
                    'DynamicScalingOutSuspended': True,
                    'ScheduledScalingSuspended': True,
                  }
                )
            elif 'restore-scaling' in self.data and self.data['restore-scaling']:
              for state, suspended in target['SuspendedState'].items():
                if suspended:
                  suspended_state[state] = False

            if suspended_state:
                self.log.debug('Target %s updating suspended_state=%s' % 
                    (resource_id, suspended_state))
                self.set_resource_desired(resource, update['Desired'])
            client.register_scalable_target(
                  ServiceNamespace=self.service_namespace,
                  ResourceId=resource_id,
                  ScalableDimension=self.scalable_dimension,
                  SuspendedState=suspended_state,
                )

            if update:
                if 'Desired' in update:
                    self.log.debug('Target %s updating desired=%d' % 
                        (resource_id, update['Desired']))
                    self.set_resource_desired(resource, update['Desired'])
                if 'Min' in update or 'Max' in update:
                  self.log.debug('Target %s updating min=%s, max=%s'
                      % (resource_id, update.get('Min', target['MinCapacity']),
                      update.get('Max', target['MaxCapacity'])))

                  client.register_scalable_target(
                    ServiceNamespace=self.service_namespace,
                    ResourceId=resource_id,
                    ScalableDimension=self.scalable_dimension,
                    MinCapacity=update.get('Min', target['MinCapacity']),
                    MaxCapacity=update.get('Max', target['MaxCapacity']),
                  )

                if 'save-options-tag' in self.data:
                    # save existing params to a tag before changing them
                    self.log.debug('Saving target %s size to tag %s' %
                        (resource_id, self.data['save-options-tag']))
                    self.set_resource_tag(
                      resource, 
                      self.data['save-options-tag'], 
                      'Min=%d:Max=%d:Desired=%d' % (target['MinCapacity'], target['MaxCapacity'], current_desired)
                    )

            else:
                self.log.debug('nothing to resize')
