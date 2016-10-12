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
import logging

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import FilterRegistry, AgeFilter, OPERATORS

from c7n.manager import resources
from c7n.query import QueryResourceManager, ResourceQuery
from c7n.utils import local_session, type_schema


log = logging.getLogger('custodian.ami')


filters = FilterRegistry('ami.filters')
actions = ActionRegistry('ami.actions')


@resources.register('ami')
class AMI(QueryResourceManager):

    class resource_type(ResourceQuery.resolve('aws.ec2.image')):
        date = 'CreationDate'
        taggable = True

    filter_registry = filters
    action_registry = actions


@actions.register('deregister')
class Deregister(BaseAction):

    schema = type_schema('deregister')

    def process(self, images):
        with self.executor_factory(max_workers=10) as w:
            list(w.map(self.process_image, images))

    def process_image(self, image):
        client = local_session(self.manager.session_factory).client('ec2')
        client.deregister_image(ImageId=image['ImageId'])

@actions.register('remove-launch-permissions')
class RemoveLaunchPermissions(BaseAction):

    schema = type_schema('remove-launch-permissions')

    def process(self, images):
        with self.executor_factory(max_workers=10) as w:
            list(w.map(self.process_image, images))

    def process_image(self, image):
        client = local_session(self.manager.session_factory).client('ec2')
        client.reset_image_attribute(ImageId=image['ImageId'],Attribute="launchPermission")


@filters.register('image-age')
class ImageAgeFilter(AgeFilter):

    date_attribute = "CreationDate"
    schema = type_schema(
        'image-age',
        op={'type': 'string', 'enum': OPERATORS.keys()},
        days={'type': 'number', 'minimum': 0})
