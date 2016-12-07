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
import itertools

from botocore.exceptions import ClientError

from c7n.actions import Action
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, type_schema, chunks


@resources.register('kinesis')
class KinesisStream(QueryResourceManager):

    resource_type = "aws.kinesis.stream"

    def augment(self, resources):

        def _augment(resource_set):
            resources = []
            client = local_session(self.session_factory).client('kinesis')
            for stream_name in resource_set:
                resources.append(
                    client.describe_stream(
                        StreamName=stream_name)['StreamDescription'])
            return resources
                        
        with self.executor_factory(max_workers=2) as w:
            return list(itertools.chain(
                *w.map(_augment, chunks(resources, 20))))


@KinesisStream.action_registry.register('delete')
class Delete(Action):

    schema = type_schema('delete')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('kinesis')
        not_active = [r['StreamName'] for r in resources
                      if r['StreamStatus'] != 'ACTIVE']
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

    def augment(self, resources):

        def _augment(resource_set):
            resources = []
            client = local_session(self.session_factory).client('firehose')
            for stream_name in resource_set:
                resources.append(
                    client.describe_delivery_stream(
                        DeliveryStreamName=stream_name)[
                            'DeliveryStreamDescription'])
            return resources

        with self.executor_factory(max_workers=2) as w:
            return list(itertools.chain(
                *w.map(_augment, chunks(resources, 20))))        


@DeliveryStream.action_registry.register('delete')
class FirehoseDelete(Action):

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('firehose')
        creating = [r['DeliveryStreamName'] for r in resources
                    if r['DeliveryStreamStatus'] == 'CREATING']
        if creating:
            self.log.warning(
                "These delivery streams can't be deleted (wrong state): %s" % (
                    ", ".join(creating)))
        for r in resources:
            if not r['DeliveryStreamStatus'] == 'ACTIVE':
                continue
            client.delete_delivery_stream(
                DeliveryStreamName=r['DeliveryStreamName'])
        
        
@resources.register('kinesis-analytics')
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


@AnalyticsApp.action_registry.register('delete')
class AppDelete(Action):

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('kinesisanalytics')
        for r in resources:
            client.delete_application(
                ApplicationName=r['ApplicationName'],
                CreateTimestamp=r['CreateTimestamp'])
        
