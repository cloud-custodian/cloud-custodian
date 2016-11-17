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

from c7n.actions import Action
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, type_schema


@resources.register('kinesis')
class KinesisStream(QueryResourceManager):

    resource_type = "aws.kinesis.stream"


@KinesisStream.action_registry.register('delete')
class Delete(Action):

    schema = type_schema('delete')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('kinesis')

        not_active = [r['StreamName'] for r in resources if r['StreamStatus'] != 'ACTIVE']
        self.log.warning(
            "The following streams cannot be deleted (wrong state): %s" % (
                ", ".join(not_active)))
        for r in resources:
            if not r['StreamStatus'] == 'ACTIVE':
                continue
            client.delete_stream(
                StreamName=r['StreamName'])


@resources.register('firehose')
class DeliveryStream(QueryResourceManager):

    resource_type = "aws.firehose.deliverystream"


@resources.register('analytics')
class AnalyticsApp(QueryResourceManager):

    class resource_type(object):
        service = "kinesisanalytics"
        enum_spec = ('list_applications', 'ApplicationSummaries', None)
        name = "ApplicationName"
        id = "ApplicationARN"
        dimension = None

    def augment(self, resources):
        client = local_session(
            self.session_factory).client('kinesisanalytics')
        results = []
        for r in resources:
            try:
                info = client.describe_application(
                    ApplicationName=r['ApplicationName'])['ApplicationDetail']
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFound':
                    continue
            r.update(info)
        return resources
