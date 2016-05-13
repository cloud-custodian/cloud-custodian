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
from c7n.filters import FilterRegistry, AgeFilter

from c7n.manager import ResourceManager, resources
from c7n.utils import local_session, type_schema


log = logging.getLogger('custodian.ami')


filters = FilterRegistry('ami.filters')
actions = ActionRegistry('ami.actions')


@resources.register('ami')
class AMI(ResourceManager):

    filter_registry = filters
    action_registry = actions

    def resources(self):
        c = self.session_factory().client('ec2')
        query = self.resource_query()
        if self._cache.load():
            images = self._cache.get(
                {'region': self.config.region, 'resource': 'ami', 'q': query})
            if images is not None:
                self.log.debug("Using cached images: %d" % len(images))
                return self.filter_resources(images)
        self.log.info("Querying images")
        images = c.describe_images(Owners=['self'], Filters=query)['Images']
        self._cache.save(
            {'region': self.config.region, 'resource': 'ami', 'q': query},
            images)
        return self.filter_resources(images)


@actions.register('deregister')
class Deregister(BaseAction):

    schema = type_schema('deregister')

    def process(self, images):
        with self.executor_factory(max_workers=10) as w:
            list(w.map(self.process_image, images))

    def process_image(self, image):
        client = local_session(self.manager.session_factory).client('ec2')
        client.deregister_image(ImageId=image['ImageId'])


@filters.register('image-age')
class ImageAgeFilter(AgeFilter):

    date_attribute = "CreationDate"
    schema = type_schema(
        'image-age', days={'type': 'integer', 'minimum': 0})
