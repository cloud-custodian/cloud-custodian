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
from c7n.filters import CrossAccountAccessFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session


@resources.register('sns')
class SNS(QueryResourceManager):

    resource_type = 'aws.sns.topic'

    def augment(self, resources):

        def _augment(r):
            client = local_session(self.session_factory).client('sns')
            attrs = client.get_topic_attributes(
                TopicArn=r['TopicArn'])['Attributes']
            r.update(attrs)
            return r

        self.log.debug("retrieving details for %d topics" % len(resources))
        with self.executor_factory(max_workers=4) as w:
            return list(w.map(_augment, resources))


SNS.filter_registry.register('cross-account', CrossAccountAccessFilter)
