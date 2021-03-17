# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json
import threading

from mock import Mock

from c7n.config import Bag
from c7n.exceptions import PolicyValidationError
from c7n.resources import aws, load_resources
from c7n import output

# resolver test needs to patch out thread usage
from c7n.resources.sqs import SQS
from c7n.executor import MainThreadExecutor

from .common import BaseTest

from aws_xray_sdk.core.models.segment import Segment
from aws_xray_sdk.core.models.subsegment import Subsegment


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


class TestArnResolver:

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

    def test_arn_resolve_resources(self, test):
        arns = [
            'arn:aws:sqs:us-east-1:644160558196:origin-dev',
            'arn:aws:lambda:us-east-1:644160558196:function:custodian-sg-modified',
            'arn:aws:lambda:us-east-1:644160558196:function:custodian-s3-tag-creator:$LATEST',
        ]

        factory = test.replay_flight_data('test_arn_resolve_resources')
        p = test.load_policy(
            {'name': 'resolve', 'resource': 'aws.ec2'},
            session_factory=factory)
        resolver = aws.ArnResolver(p.resource_manager)
        load_resources(('aws.sqs', 'aws.lambda'))
        test.patch(SQS, 'executor_factory', MainThreadExecutor)
        arn_map = resolver.resolve(arns)
        assert len(arn_map) == 3
        assert None not in arn_map.values()

    def test_arn_meta(self):

        legacy = set()
        for k, v in aws.AWS.resources.items():
            if getattr(v.resource_type, 'type', None) is not None:
                legacy.add(k)
        assert not legacy

    def test_arn_resolve_type(self):
        for value, expected in self.table:
            # load the resource types to enable resolution.
            aws.AWS.get_resource_types(("aws.%s" % expected,))
            arn = aws.Arn.parse(value)
            result = aws.ArnResolver.resolve_type(arn)
            assert result == expected

    def test_arn_cwe_resolver(self):

        evars = dict(
            Partition='aws',
            Region='us-east-1',
            Account='662108712480',
            FunctionName='func',
            Version='1.1',
            VersionId='1.1',
            ClusterName='abc',
            AutomationDefinitionName='adf',
            TaskDefinitionFamilyName='abc',
            TaskDefinitionRevisionNumber='yz',
            StreamName='kstream',
            AutomationDefinition='abc',
            LogGroupName='loggroup',
            JobQueueName='batchq',
            JobDefinitionName='jobdef',
            Revision='1.1',
            QueueName='inboundq',
            TopicName='outboundt',
            ProjectName="buildstuff",
            PipelineName='pushit',
            StateMachineName='sfxorch'
        )

        event_targets = dict(
            sqs=("arn:{Partition}:sqs:{Region}:{Account}:{QueueName}", 'sqs'),
            function=("arn:{Partition}:lambda:{Region}:{Account}:function:{FunctionName}",
                      'lambda'),
            function_qual=(
                "arn:{Partition}:lambda:{Region}:{Account}:function:{FunctionName}:{Version}",
                "lambda"),
            ecs_cluster=(
                "arn:{Partition}:ecs:{Region}:{Account}:cluster/{ClusterName}",
                "ecs"),
            ecs_task=(
                ("arn:{Partition}:ecs:{Region}:{Account}:task-definition/"
                "{TaskDefinitionFamilyName}:{TaskDefinitionRevisionNumber}"),
                "ecs-task-definition"),
            kinesis=("arn:{Partition}:kinesis:{Region}:{Account}:stream/{StreamName}",
                     "kinesis"),
            log=("arn:{Partition}:logs:{Region}:{Account}:log-group:{LogGroupName}",
                 "log-group"),
            # ssm_adoc=(("arn:{Partition}:ssm:{Region}:{Account}:automation-definition"
            #           "/{AutomationDefinitionName}:{VersionId}"),
            batch_job_def=(
                ("arn:{Partition}:batch:{Region}:{Account}:job-definition"
                 "/{JobDefinitionName}:{Revision}"),
                "batch-definition"),
            batch_queue=("arn:{Partition}:batch:{Region}:{Account}:job-queue/{JobQueueName}",
                         "batch-queue"),
            step_func=(
                "arn:{Partition}:states:{Region}:{Account}:stateMachine:{StateMachineName}",
                "step-machine"),
            code_pipe=(
                "arn:{Partition}:codepipeline:{Region}:{Account}:{PipelineName}",
                "codepipeline"),
            code_build=(
                "arn:{Partition}:codebuild:{Region}:{Account}:project/{ProjectName}",
                "codebuild"),
            sns_topics=(
                "arn:{Partition}:sns:{Region}:{Account}:{TopicName}",
                "sns"),
            sqs_queue=(
                "arn:{Partition}:sqs:{Region}:{Account}:{QueueName}",
                "sqs")
        )
        load_resources(('aws.*',))
        for k, (arn_template, rtype) in event_targets.items():
            rarn = arn_template.format(**evars)
            assert aws.ArnResolver.resolve_type(rarn) == rtype


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

    def test_context(self):
        store = aws.XrayContext()
        self.assertEqual(store.handle_context_missing(), None)
        x = Segment('foo')
        y = Segment('foo')
        a = Subsegment('bar', 'boo', x)
        b = Subsegment('bar', 'boo', x)
        b.thread_id = '123'
        store.put_segment(x)
        store.put_subsegment(a)
        store.put_subsegment(b)

        self.assertEqual(store._local.entities, [x, a, b])
        self.assertEqual(store.get_trace_entity(), a)
        store.end_subsegment(a)
        self.assertEqual(store.get_trace_entity(), x)
        store.put_segment(y)
        self.assertEqual(store._local.entities, [y])
        self.assertEqual(store.get_trace_entity(), y)
        self.assertFalse(store.end_subsegment(42))

    def test_context_worker_thread_main_acquire(self):
        store = aws.XrayContext()
        x = Segment('foo')
        a = Subsegment('bar', 'boo', x)
        store.put_segment(x)
        store.put_subsegment(a)

        def get_ident():
            return 42

        self.patch(threading, 'get_ident', get_ident)
        self.assertEqual(store.get_trace_entity(), a)

    def test_tracer(self):
        session_factory = self.replay_flight_data('output-xray-trace')
        policy = Bag(name='test', resource_type='ec2')
        ctx = Bag(
            policy=policy,
            session_factory=session_factory,
            options=Bag(account_id='644160558196', region='us-east-1',))
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
