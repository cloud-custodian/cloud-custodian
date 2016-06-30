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
from botocore.exceptions import ClientError

from c7n.iamaccess import CrossAccountAccessFilter
from c7n.manager import resources
from c7n.utils import local_session
from c7n.query import QueryResourceManager


@resources.register('sqs')
class SQS(QueryResourceManager):

    resource_type = 'aws.sqs.queue'

    def augment(self, resources):

        def _augment(r):
            client = local_session(self.session_factory).client('sqs')
            try:
                queue = client.get_queue_attributes(
                    QueueUrl=r,
                    AttributeNames=['All'])['Attributes']
            except ClientError as e:
                if e.response['Error']['Code'] == 'AccessDenied':
                    self.log.warning("Denied access to sqs %s" % r)
                    return
                raise

            queue['QueueUrl'] = r
            return queue

        self.log.debug('retrieving details for %d queues' % len(resources))
        with self.executor_factory(max_workers=4) as w:
            return filter(None, w.map(_augment, resources))


SQS.filter_registry.register('cross-account', CrossAccountAccessFilter)
