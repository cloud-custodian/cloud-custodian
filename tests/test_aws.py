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


class ArnResolverTest(BaseTest):

    table = [
        ('arn:aws:waf::123456789012:webacl/3bffd3ed-fa2e-445e-869f-a6a7cf153fd3', 'waf'),
        ('arn:aws:waf-regional:us-east-1:123456789012:webacl/3bffd3ed-fa2e-445e-869f-a6a7cf153fd3', 'waf-regional'), # NOQA
        ('arn:aws:acm:region:account-id:certificate/certificate-id', 'acm-certificate'),
        ('arn:aws:cloudwatch:region:account-id:alarm:alarm-name', 'alarm'),
        ('arn:aws:logs:us-east-1:123456789012:log-group:my-log-group', 'log-group'),
        ('arn:aws:codebuild:us-east-1:123456789012:project/my-demo-project', 'codebuild'),
        ('arn:aws:cognito-idp:region:account-id:userpool/user-pool-id', 'user-pool'),
        ('arn:aws:config:region:account-id:config-rule/config-rule-id', 'config-rule'),
        ('arn:aws:directconnect:us-east-1:123456789012:dxcon/dxcon-fgase048', 'directconnect'),
        ('arn:aws:dynamodb:region:account-id:table/tablename', 'dynamodb-table'),
        ('arn:aws:ec2:region:account-id:instance/instance-id', 'ec2'),
        ('arn:aws:ec2:region:account-id:vpc/vpc-id', 'vpc'),
        ('arn:aws:ds:region:account-id:directory/directoryId', 'directory'),
        ('arn:aws:elasticbeanstalk:region:account-id:application/applicationname', 'elasticbeanstalk'), # NOQA
        ('arn:aws:ecr:region:account-id:repository/repository-name', 'ecr'),
        ('arn:aws:elasticache:us-east-2:123456789012:cluster:myCluster', 'cache-cluster'),
        ('arn:aws:es:us-east-1:123456789012:domain/streaming-logs', 'elasticsearch'),
        ('arn:aws:elasticfilesystem:region:account-id:file-system/file-system-id', 'efs'),
        ('arn:aws:ecs:us-east-1:123456789012:task/my-cluster/1abf0f6d-a411-4033-b8eb-a4eed3ad252a', 'ecs-task'), # NOQA
        ('arn:aws:autoscaling:region:account-id:autoScalingGroup:groupid:autoScalingGroupName/groupfriendlyname', 'asg') # NOQA
    ]

    def test_arn_meta(self):

        legacy = set()
        for k, v in aws.AWS.resources.items():
            if getattr(v.resource_type, 'type', None) is not None:
                legacy.add(k)
        self.assertFalse(legacy)

    def test_arn_resolver(self):
        for value, expected in self.table:
            arn = aws.Arn.parse(value)
            result = aws.ArnResolver.resolve_type(arn)
            self.assertEqual(result, expected)


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
        config = Bag(assume_role='arn:aws:iam::644160558196:role/custodian-mu', account_id=None)
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

    def test_metrics_destination_dims(self):
        tmetrics = []

        class Metrics(aws.MetricsOutput):

            def _put_metrics(self, ns, metrics):
                tmetrics.extend(metrics)

        conf = Bag({'region': 'us-east-2', 'scheme': 'aws', 'netloc': 'master'})
        ctx = Bag(session_factory=None,
                  options=Bag(account_id='001100', region='us-east-1'),
                  policy=Bag(name='test', resource_type='ec2'))
        moutput = Metrics(ctx, conf)

        moutput.put_metric('Calories', 400, 'Count', Scope='Policy', Food='Pizza')
        moutput.flush()

        tmetrics[0].pop('Timestamp')
        self.assertEqual(tmetrics, [{
            'Dimensions': [{'Name': 'Policy', 'Value': 'test'},
                           {'Name': 'ResType', 'Value': 'ec2'},
                           {'Name': 'Food', 'Value': 'Pizza'},
                           {'Name': 'Region', 'Value': 'us-east-1'},
                           {'Name': 'Account', 'Value': '001100'}],
            'MetricName': 'Calories',
            'Unit': 'Count',
            'Value': 400}])

    def test_metrics(self):
        session_factory = self.replay_flight_data('output-aws-metrics')
        policy = Bag(name='test', resource_type='ec2')
        ctx = Bag(session_factory=session_factory, policy=policy)
        sink = output.metrics_outputs.select('aws', ctx)
        self.assertTrue(isinstance(sink, aws.MetricsOutput))
        sink.put_metric('ResourceCount', 101, 'Count')
        sink.flush()


class OutputLogsTest(BaseTest):
    # cloud watch logging

    def test_default_log_group(self):
        ctx = Bag(session_factory=None,
                  options=Bag(account_id='001100', region='us-east-1'),
                  policy=Bag(name='test', resource_type='ec2'))

        log_output = output.log_outputs.select('custodian/xyz', ctx)
        self.assertEqual(log_output.log_group, 'custodian/xyz')
        self.assertEqual(log_output.construct_stream_name(), 'test')

        log_output = output.log_outputs.select('/custodian/xyz/', ctx)
        self.assertEqual(log_output.log_group, 'custodian/xyz')

        log_output = output.log_outputs.select('aws://somewhere/out/there', ctx)
        self.assertEqual(log_output.log_group, 'somewhere/out/there')

        log_output = output.log_outputs.select('aws:///somewhere/out', ctx)
        self.assertEqual(log_output.log_group, 'somewhere/out')

        log_output = output.log_outputs.select('aws://somewhere', ctx)
        self.assertEqual(log_output.log_group, 'somewhere')

        log_output = output.log_outputs.select(
            "aws:///somewhere/out?stream={region}/{policy}", ctx)
        self.assertEqual(log_output.log_group, 'somewhere/out')
        self.assertEqual(log_output.construct_stream_name(), 'us-east-1/test')

    def test_master_log_handler(self):
        session_factory = self.replay_flight_data('test_log_handler')
        ctx = Bag(session_factory=session_factory,
                  options=Bag(account_id='001100', region='us-east-1'),
                  policy=Bag(name='test', resource_type='ec2'))
        log_output = output.log_outputs.select(
            'aws://master/custodian?region=us-east-2', ctx)
        stream = log_output.get_handler()
        self.assertTrue(stream.log_group == 'custodian')
        self.assertTrue(stream.log_stream == '001100/us-east-1/test')

    def test_stream_override(self):
        session_factory = self.replay_flight_data(
            'test_log_stream_override')
        ctx = Bag(session_factory=session_factory,
            options=Bag(account_id='001100', region='us-east-1'),
            policy=Bag(name='test', resource_type='ec2'))
        log_output = output.log_outputs.select(
            'aws://master/custodian?region=us-east-2&stream=testing', ctx)
        stream = log_output.get_handler()
        self.assertTrue(stream.log_stream == 'testing')
