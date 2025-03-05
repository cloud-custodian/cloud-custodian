# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json
import time
import threading
import socket
import sys
from urllib.error import URLError, HTTPError
from unittest.mock import Mock, patch

from c7n.config import Bag, Config
from c7n.exceptions import PolicyValidationError, InvalidOutputConfig
from c7n.resources import aws, load_resources
from c7n.schema import StructureParser
from c7n import output, schema

# resolver test needs to patch out thread usage
from c7n.resources.sqs import SQS
from c7n.executor import MainThreadExecutor

from .common import BaseTest

from aws_xray_sdk.core.models.segment import Segment
from aws_xray_sdk.core.models.subsegment import Subsegment

import pytest
import vcr


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

    def test_invalid_arn(self):
        try:
            aws.Arn.parse('arn:aws')
        except ValueError:
            pass


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

    def test_metrics_query_params(self):
        # Test metrics filter when 'metrics' and 'ignore_zero' is present in query parameters
        conf = Bag(
            {'active_metrics': 'ResourceCount,ApiCalls', 'scheme': 'aws', 'ignore_zero': 'true'})
        ctx = Bag(session_factory=self.replay_flight_data('output-aws-metrics'),
                  options=Bag(account_id='123456789012', region='us-east-1'),
                  policy=Bag(name='test', resource_type='ec2'))
        moutput = aws.MetricsOutput(ctx, conf)

        with patch("botocore.client.BaseClient._make_api_call") as aws_api:
            moutput.put_metric('ResourceCount', 0, 'Count', Scope='Policy', Food='Pizza')
            moutput.flush()
            assert aws_api.call_count == 0

            moutput.put_metric('Calories', 400, 'Count', Scope='Policy', Food='Pizza')
            moutput.flush()
            assert aws_api.call_count == 0

            moutput._put_metrics("ns", [{'MetricName': 'Calls'}, {'MetricName': 'ResourceCount'}])
            assert aws_api.call_args[0][0] == "PutMetricData"
            assert aws_api.call_args[0][1]["MetricData"] == [{'MetricName': 'ResourceCount'}]
            assert aws_api.call_count == 1


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


def test_url_socket_retry(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda x: x)

    # case for unknown error
    fvalues = [URLError(socket.error(104, 'Connection reset by peer')),
               URLError(socket.gaierror(8, 'Name or node unknown'))]

    def freturns():
        ret = fvalues.pop()
        if isinstance(ret, URLError):
            raise ret
        return ret

    with pytest.raises(URLError) as ecm:
        aws.url_socket_retry(freturns)

    assert 'Name or node unknown' in str(ecm.value)

    # case for retry exhaustion
    fvalues[:] = [
        URLError(socket.error(110, 'Connection timed out')),
        URLError(socket.error(110, 'Connection timed out')),
        URLError(socket.error(110, 'Connection timed out')),
        URLError(socket.error(110, 'Connection timed out')),
    ]

    with pytest.raises(URLError) as ecm:
        aws.url_socket_retry(freturns)

    # case for success
    fvalues[:] = [
        URLError(socket.error(110, 'Connection timed out')),
        42
    ]


@pytest.mark.skipif(sys.version_info < (3, 9), reason="requires python3.9 or higher")
def test_http_socket_retry(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda x: x)

    # case for unknown error
    fvalues = [HTTPError('https://lwn.net', 404, 'Unknown', {}, None)]

    def freturns():
        ret = fvalues.pop()
        if isinstance(ret, URLError):
            raise ret
        return ret

    with pytest.raises(URLError) as ecm:
        aws.url_socket_retry(freturns)

    assert 'Unknown' in str(ecm.value)

    # case for retry exhaustion
    fvalues[:] = [
        HTTPError('https://lwn.net', 503, 'Slow Down', {}, None),
        HTTPError('https://lwn.net', 503, 'Slow Down', {}, None),
        HTTPError('https://lwn.net', 503, 'Slow Down', {}, None),
        HTTPError('https://lwn.net', 503, 'Slow Down', {}, None),
    ]

    # this is really an indirect assertion that is ascertained via
    # coverage.
    with pytest.raises(URLError) as ecm:
        aws.url_socket_retry(freturns)

    # case for success
    fvalues[:] = [
        HTTPError('https://lwn.net', 503, 'Slow Down', {}, None),
        42
    ]

    assert aws.url_socket_retry(freturns) == 42


def test_default_bucket_region_with_no_s3():
    output_dir = "/tmp"
    conf = Config.empty(output_dir=output_dir)
    aws._default_bucket_region(conf)
    assert output_dir == conf.output_dir


def test_default_bucket_region_with_explicit_region():
    output_dir = "s3://aws?region=xyz"
    conf = Config.empty(output_dir=output_dir)
    aws._default_bucket_region(conf)
    assert output_dir == conf.output_dir


def test_join_output():
    output_dir = aws.join_output("s3://aws?region=xyz", "suffix")
    assert output_dir == "s3://aws/suffix?region=xyz"


def test_shape_schema():
    policy_data = {"policies": [{
        "name": "update-eks-config",
        "resource": "eks",
        "actions": [{
                "type": "update-config",
                "resourcesVpcConfig": {
                    "endpointPublicAccess": "nay",
                    "endpointPrivateAccess": True, },
        }],
    }]}
    structure = StructureParser()
    load_resources(structure.get_resource_types(policy_data))
    schm = schema.generate()
    results = schema.validate(policy_data, schm)
    assert "'nay' is not of type 'boolean'" in str(results)

    policy_data = {"policies": [{
        "name": "update-eks-config",
        "resource": "eks",
        "actions": [{
            "type": "update-config",
            "upgradePolicy": {
                "supportType": "WRONG",
            }
        }],
    }]}

    results = schema.validate(policy_data, schm)
    assert "'WRONG' is not one of" in str(results)

    policy_data = {"policies": [{
        "name": "update-eks-config",
        "resource": "eks",
        "actions": [{
            "type": "update-config",
            "unknownOption": True,
        }],
    }]}

    results = schema.validate(policy_data, schm)
    assert "Additional properties are not allowed" in str(results)

    stage_update_schema = aws.shape_schema(
        'apigatewayv2', 'UpdateStageRequest', drop_fields=('ApiId', 'StageName')
    )
    assert "^.+$" in stage_update_schema["RouteSettings"]["patternProperties"].keys()


@patch('c7n.resources.aws.MODEL_SCHEMA_TYPE_MAP', {"string": "string"})
def test_shape_schema_error():
    policy_data = {"policies": [{
        "name": "update-eks-config",
        "resource": "eks",
        "actions": [{
            "type": "update-config",
            "upgradePolicy": {
                "supportType": "WRONG",
            }
        }],
    }]}
    structure = StructureParser()
    with pytest.raises(KeyError) as e:
        load_resources(structure.get_resource_types(policy_data))
    assert "Unknown type for" in str(e.value)


@vcr.use_cassette(
    'tests/data/vcr_cassettes/test_output/default_bucket_region_public.yaml')
def test_default_bucket_region_is_public():
    output_dir = "s3://awsapichanges.info"
    conf = Config.empty(output_dir=output_dir, regions=["us-east-1"])
    with pytest.raises(InvalidOutputConfig) as ecm:
        aws._default_bucket_region(conf)

    assert "is publicly accessible" in str(ecm.value)


@vcr.use_cassette(
    'tests/data/vcr_cassettes/test_output/default_bucket_region.yaml')
def test_default_bucket_region_s3():
    output_dir = "s3://slack.cloudcustodian.io"
    conf = Config.empty(output_dir=output_dir, regions=["all"])
    aws._default_bucket_region(conf)
    assert conf.output_dir == output_dir + "?region=us-east-1"


@vcr.use_cassette(
    'tests/data/vcr_cassettes/test_output/default_bucket_not_found.yaml')
def test_default_bucket_region_not_found():
    output_dir = "s3://myfakebucketdoesnotexist"
    conf = Config.empty(output_dir=output_dir, regions=["us-west-2"])
    with pytest.raises(InvalidOutputConfig) as ecm:
        aws._default_bucket_region(conf)

    assert "does not exist" in str(ecm.value)


@vcr.use_cassette(
    'tests/data/vcr_cassettes/test_output/bucket_not_found.yaml')
def test_get_bucket_url_s3_not_found():
    with pytest.raises(ValueError) as ecm:
        aws.get_bucket_url_with_region(
            "s3://myfakebucketdoesnotexist", None
        )
    assert "does not exist" in str(ecm.value)


@vcr.use_cassette(
    'tests/data/vcr_cassettes/test_output/cross_region.yaml')
def test_get_bucket_url_s3_cross_region():
    assert aws.get_bucket_url_with_region(
        "s3://slack.cloudcustodian.io",
        "us-west-2") == "s3://slack.cloudcustodian.io?region=us-east-1"
    assert aws.get_bucket_url_with_region(
        "s3://slack.cloudcustodian.io/",
        "us-west-2") == "s3://slack.cloudcustodian.io?region=us-east-1"


@vcr.use_cassette(
    'tests/data/vcr_cassettes/test_output/same_region.yaml')
def test_get_bucket_url_s3_same_region():
    assert aws.get_bucket_url_with_region(
        "s3://slack.cloudcustodian.io?",
        None) == "s3://slack.cloudcustodian.io?region=us-east-1"

    assert aws.get_bucket_url_with_region(
        "s3://slack.cloudcustodian.io?param=x",
        "us-east-1") == "s3://slack.cloudcustodian.io?param=x&region=us-east-1"

    assert aws.get_bucket_url_with_region(
        "s3://slack.cloudcustodian.io/logs/?param=x",
        "us-east-1") == "s3://slack.cloudcustodian.io/logs?param=x&region=us-east-1"
