# Copyright 2017-2018 Capital One Services, LLC
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

import json

from mock import Mock

from c7n.config import Bag
from c7n.exceptions import PolicyValidationError
from c7n.resources import aws
from c7n import output

from .common import BaseTest


class TraceDoc(Bag):

    def serialize(self):
        return json.dumps(dict(self))


class OutputXrayTracerTest(BaseTest):

    def test_emitter(self):
        emitter = aws.XrayEmitter()
        emitter.client = m = Mock()
        doc = TraceDoc({'good': 'morning'})
        emitter.send_entity(doc)
        emitter.flush()
        m.put_trace_segments.assert_called_with(
            TraceSegmentDocuments=[doc.serialize()])


class ArnTest(BaseTest):

    def test_eb_arn(self):
        arn = aws.Arn.parse(
            'arn:aws:elasticbeanstalk:us-east-1:123456789012:environment/My App/MyEnv')
        self.assertEqual(arn.service, 'elasticbeanstalk')
        self.assertEqual(arn.account_id, '123456789012')
        self.assertEqual(arn.region, 'us-east-1')
        self.assertEqual(arn.resource_type, 'environment')
        self.assertEqual(arn.resource, 'My App/MyEnv')

    def test_iam_arn(self):
        arn = aws.Arn.parse(
            'arn:aws:iam::123456789012:user/David')
        self.assertEqual(arn.service, 'iam')
        self.assertEqual(arn.resource, 'David')
        self.assertEqual(arn.resource_type, 'user')

    def test_rds_arn(self):
        arn = aws.Arn.parse(
            'arn:aws:rds:eu-west-1:123456789012:db:mysql-db')
        self.assertEqual(arn.resource_type, 'db')
        self.assertEqual(arn.resource, 'mysql-db')
        self.assertEqual(arn.region, 'eu-west-1')

    def test_s3_key_arn(self):
        arn = aws.Arn.parse(
            'arn:aws:s3:::my_corporate_bucket/exampleobject.png')
        self.assertEqual(arn.resource, 'my_corporate_bucket/exampleobject.png')


class UtilTest(BaseTest):

    def test_default_account_id_assume(self):
        config = Bag(assume_role='arn:aws:iam::644160558196:role/custodian-mu')
        aws._default_account_id(config)
        self.assertEqual(config.account_id, '644160558196')

    def test_validate(self):
        self.assertRaises(
            PolicyValidationError,
            aws.shape_validate,
            {'X': 1},
            'AwsSecurityFindingFilters',
            'securityhub')
        self.assertEqual(
            aws.shape_validate(
                {'Id': [{'Value': 'abc', 'Comparison': 'EQUALS'}]},
                'AwsSecurityFindingFilters',
                'securityhub'),
            None)


class TracerTest(BaseTest):

    def test_tracer(self):
        session_factory = self.replay_flight_data('output-xray-trace')
        policy = Bag(name='test', resource_type='ec2')
        ctx = Bag(
            policy=policy,
            session_factory=session_factory,
            options=Bag(account_id='644160558196'))
        ctx.get_metadata = lambda *args: {}
        config = Bag()
        tracer = aws.XrayTracer(ctx, config)

        with tracer:
            try:
                with tracer.subsegment('testing') as w:
                    raise ValueError()
            except ValueError:
                pass
            self.assertNotEqual(w.cause, {})


class OutputMetricsTest(BaseTest):

    def test_metrics(self):
        session_factory = self.replay_flight_data('output-aws-metrics')
        policy = Bag(name='test', resource_type='ec2')
        ctx = Bag(session_factory=session_factory, policy=policy)
        sink = output.metrics_outputs.select('aws', ctx)
        self.assertTrue(isinstance(sink, aws.MetricsOutput))
        sink.put_metric('ResourceCount', 101, 'Count')
        sink.flush()
