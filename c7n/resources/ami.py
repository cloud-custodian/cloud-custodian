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

import itertools
import logging

from concurrent.futures import as_completed

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import (
    FilterRegistry, AgeFilter, Filter, OPERATORS, CrossAccountAccessFilter)
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.resolver import ValuesFrom
from c7n.utils import local_session, type_schema, get_retry, chunks


log = logging.getLogger('custodian.ami')


filters = FilterRegistry('ami.filters')
actions = ActionRegistry('ami.actions')


@resources.register('ami')
class AMI(QueryResourceManager):

    class resource_type(object):
        service = 'ec2'
        type = 'image'
        enum_spec = (
            'describe_images', 'Images', None)
        detail_spec = None
        id = 'ImageId'
        filter_name = 'ImageIds'
        filter_type = 'list'
        name = 'Name'
        dimension = None
        date = 'CreationDate'

    filter_registry = filters
    action_registry = actions

    def resources(self, query=None):
        query = query or {}
        if query.get('Owners') is None:
            query['Owners'] = ['self']
        return super(AMI, self).resources(query=query)


@actions.register('deregister')
class Deregister(BaseAction):
    """Action to deregister AMI

    To prevent deregistering all AMI, it is advised to use in conjunction with
    a filter (such as image-age)

    :example:

    .. code-block:: yaml

            policies:
              - name: ami-deregister-old
                resource: ami
                filters:
                  - type: image-age
                    days: 90
                actions:
                  - deregister
    """

    schema = type_schema('deregister')
    permissions = ('ec2:DeregisterImage',)

    def process(self, images):
        with self.executor_factory(max_workers=10) as w:
            list(w.map(self.process_image, images))

    def process_image(self, image):
        retry = get_retry((
            'RequestLimitExceeded', 'Client.RequestLimitExceeded'))

        client = local_session(self.manager.session_factory).client('ec2')
        retry(client.deregister_image, ImageId=image['ImageId'])


@actions.register('remove-launch-permissions')
class RemoveLaunchPermissions(BaseAction):
    """Action to remove the ability to launch an instance from an AMI

    This action will remove any launch permissions granted to other
    AWS accounts from the image, leaving only the owner capable of
    launching it

    :example:

    .. code-block:: yaml

            policies:
              - name: ami-remove-launch-permissions
                resource: ami
                filters:
                  - type: image-age
                    days: 60
                actions:
                  - remove-launch-permissions

    """

    schema = type_schema('remove-launch-permissions')
    permissions = ('ec2:ResetImageAttribute',)

    def process(self, images):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_image, images))

    def process_image(self, image):
        client = local_session(self.manager.session_factory).client('ec2')
        client.reset_image_attribute(
            ImageId=image['ImageId'], Attribute="launchPermission")


@actions.register('copy')
class Copy(BaseAction):
    """Action to copy AMIs with optional encryption

    This action can copy AMIs while optionally encrypting or decrypting
    the target AMI. It is advised to use in conjunction with a filter.

    :example:

    .. code-block:: yaml

            policies:
              - name: ami-ensure-encrypted
                resource: ami
                filters:
                  - not:
                    - type: encrypted
                actions:
                  - type: copy
                    encrypt: true
                    key-id: 00000000-0000-0000-0000-000000000000
    """

    permissions = ('ec2:CopyImage',)
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['copy']},
            'name': {'type': 'string'},
            'description': {'type': 'string'},
            'region': {'type': 'string'},
            'encrypt': {'type': 'boolean'},
            'key-id': {'type': 'string'}
        }
    }

    def process(self, images):
        session = local_session(self.manager.session_factory)
        client = session.client(
            'ec2',
            region_name=self.data.get('region', None))

        for image in images:
            client.copy_image(
                Name=self.data.get('name', image['Name']),
                Description=self.data.get('description', image['Description']),
                SourceRegion=session.region_name,
                SourceImageId=image['ImageId'],
                Encrypted=self.data.get('encrypt', False),
                KmsKeyId=self.data.get('key-id', ''))


@filters.register('image-age')
class ImageAgeFilter(AgeFilter):
    """Filters images based on the age (in days)

    :example:

    .. code-block:: yaml

            policies:
              - name: ami-remove-launch-permissions
                resource: ami
                filters:
                  - type: image-age
                    days: 30
    """

    date_attribute = "CreationDate"
    schema = type_schema(
        'image-age',
        op={'type': 'string', 'enum': list(OPERATORS.keys())},
        days={'type': 'number', 'minimum': 0})


@filters.register('unused')
class ImageUnusedFilter(Filter):
    """Filters images based on usage

    true: image has no instances spawned from it
    false: image has instances spawned from it

    :example:

    .. code-block:: yaml

            policies:
              - name: ami-unused
                resource: ami
                filters:
                  - type: unused
                    value: true
    """

    schema = type_schema('unused', value={'type': 'boolean'})

    def get_permissions(self):
        return list(itertools.chain([
            self.manager.get_resource_manager(m).get_permissions()
            for m in ('asg', 'launch-config', 'ec2')]))

    def _pull_asg_images(self):
        asgs = self.manager.get_resource_manager('asg').resources()
        lcfgs = set(a['LaunchConfigurationName'] for a in asgs)
        lcfg_mgr = self.manager.get_resource_manager('launch-config')
        return set([
            lcfg['ImageId'] for lcfg in lcfg_mgr.resources()
            if lcfg['LaunchConfigurationName'] in lcfgs])

    def _pull_ec2_images(self):
        ec2_manager = self.manager.get_resource_manager('ec2')
        return set([i['ImageId'] for i in ec2_manager.resources()])

    def process(self, resources, event=None):
        images = self._pull_ec2_images().union(self._pull_asg_images())
        if self.data.get('value', True):
            return [r for r in resources if r['ImageId'] not in images]
        return [r for r in resources if r['ImageId'] in images]


@filters.register('cross-account')
class AmiCrossAccountFilter(CrossAccountAccessFilter):

    schema = type_schema(
        'cross-account',
        # white list accounts
        whitelist_from=ValuesFrom.schema,
        whitelist={'type': 'array', 'items': {'type': 'string'}})

    permissions = ('ec2:DescribeImageAttribute',)

    def process_resource_set(self, client, accounts, resource_set):
        results = []
        for r in resource_set:
            attrs = self.manager.retry(
                client.describe_image_attribute,
                ImageId=r['ImageId'],
                Attribute='launchPermission')['LaunchPermissions']
            image_accounts = {a.get('Group') or a.get('UserId') for a in attrs}
            delta_accounts = image_accounts.difference(accounts)
            if delta_accounts:
                r['c7n:CrossAccountViolations'] = list(delta_accounts)
                results.append(r)
        return results

    def process(self, resources, event=None):
        results = []
        client = local_session(self.manager.session_factory).client('ec2')
        accounts = self.get_accounts()

        with self.executor_factory(max_workers=2) as w:
            futures = []
            for resource_set in chunks(resources, 20):
                futures.append(
                    w.submit(
                        self.process_resource_set, client, accounts, resource_set))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception checking cross account access \n %s" % (
                            f.exception()))
                    continue
                results.extend(f.result())
        return results
