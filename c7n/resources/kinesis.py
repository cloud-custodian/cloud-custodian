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

from c7n.actions import BaseAction as Action
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session


@resources.register('kinesis')
class KinesisStream(QueryResourceManager):

    resource_type = "aws.kinesis.stream"


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
