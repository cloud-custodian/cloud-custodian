# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
# -*- coding: utf-8 -*-

import builtins
from datetime import datetime
from importlib import reload
import os
from time import sleep
import unittest
import jinja2
import logging
from mock import Mock, patch

import c7n_mailer
from c7n_mailer import utils
from c7n_mailer.azure_mailer.azure_queue_processor import MailerAzureQueueProcessor
from c7n_mailer.gcp_mailer.gcp_queue_processor import MailerGcpQueueProcessor
from c7n_mailer.sqs_queue_processor import MailerSqsQueueProcessor
from common import MAILER_CONFIG, SQS_MESSAGE_1, RESOURCE_1


class FormatStruct(unittest.TestCase):
    def test_formats_struct(self):
        expected = '{\n  "foo": "bar"\n}'
        actual = utils.format_struct({"foo": "bar"})
        self.assertEqual(expected, actual)


class StripPrefix(unittest.TestCase):
    def test_strip_prefix(self):
        self.assertEqual(utils.strip_prefix("aws.internet-gateway", "aws."), "internet-gateway")
        self.assertEqual(utils.strip_prefix("aws.s3", "aws."), "s3")
        self.assertEqual(utils.strip_prefix("aws.webserver", "aws."), "webserver")
        self.assertEqual(utils.strip_prefix("nothing", "aws."), "nothing")
        self.assertEqual(utils.strip_prefix("azure.azserver", "azure."), "azserver")
        self.assertEqual(utils.strip_prefix("gcp.instance", "gcp."), "instance")
        self.assertEqual(utils.strip_prefix("", "aws."), "")


def test_config_defaults():
    config = {}
    utils.setup_defaults(config)
    for k, v in list(config.items()):
        if v is None:
            config.pop(k)
    assert config == dict(
        region="us-east-1",
        ses_region="us-east-1",
        memory=1024,
        timeout=300,
        runtime="python3.11",
        contact_tags=[],
    )


class GetResourceTagTargets(unittest.TestCase):
    def test_target_tag_list(self):
        self.assertEqual(
            utils.get_resource_tag_targets(
                {"Tags": [{"Key": "Creator", "Value": "alice"}]}, ["Creator"]
            ),
            ["alice"],
        )

    def test_target_tag_map(self):
        r = {"Tags": {"Creator": "Bob"}}
        self.assertEqual(utils.get_resource_tag_targets(r, ["Creator"]), ["Bob"])


class ResourceFormat(unittest.TestCase):
    def test_efs(self):
        self.assertEqual(
            utils.resource_format(
                {"Name": "abc", "FileSystemId": "fsid", "LifeCycleState": "available"}, "efs"
            ),
            "name: abc  id: fsid  state: available",
        )

    def test_eip(self):
        self.assertEqual(
            utils.resource_format(
                {"PublicIp": "8.8.8.8", "Domain": "vpc", "AllocationId": "eipxyz"}, "network-addr"
            ),
            "ip: 8.8.8.8  id: eipxyz  scope: vpc",
        )

    def test_nat(self):
        self.assertEqual(
            utils.resource_format(
                {"NatGatewayId": "nat-xyz", "State": "available", "VpcId": "vpc-123"}, "nat-gateway"
            ),
            "id: nat-xyz  state: available  vpc: vpc-123",
        )

    def test_igw(self):
        self.assertEqual(
            utils.resource_format(
                {"InternetGatewayId": "igw-x", "Attachments": []}, "aws.internet-gateway"
            ),
            "id: igw-x  attachments: 0",
        )

    def test_lambda(self):
        image_func = {
            "FunctionName": "my-image-based-function",
            "PackageType": "Image",
        }
        zip_func = {
            "FunctionName": "my-zip-based-function",
            "Runtime": "python3.8",
            "PackageType": "Zip",
        }
        self.assertEqual(
            utils.resource_format(image_func, "aws.lambda").strip(),
            "Name: my-image-based-function  Package Type: Image  Runtime: N/A",
        )
        self.assertEqual(
            utils.resource_format(zip_func, "aws.lambda").strip(),
            "Name: my-zip-based-function  Package Type: Zip  Runtime: python3.8",
        )

    def test_rds_cluster(self):
        self.assertEqual(
            utils.resource_format(
                {
                    "DBClusterIdentifier": "database-2",
                    "Engine": "mysql-aurora",
                    "EngineVersion": "5.7.mysql_aurora.2.07.2",
                    "AllocatedStorage": "1",
                },
                "rds-cluster",
            ),
            "database-2 mysql-aurora-5.7.mysql_aurora.2.07.2 1",
        )

    def test_s3(self):
        self.assertEqual(utils.resource_format({"Name": "bucket-x"}, "aws.s3"), "bucket-x")

    def test_alb(self):
        self.assertEqual(
            utils.resource_format(
                {
                    "LoadBalancerArn": "arn:aws:elasticloadbalancing:us-east-1:367930536793"
                    ":loadbalancer/app/dev/1234567890",
                    "AvailabilityZones": [],
                    "Scheme": "internal",
                },
                "app-elb",
            ),
            "arn: arn:aws:elasticloadbalancing:us-east-1:367930536793:"
            "loadbalancer/app/dev/1234567890"
            "  zones: 0  scheme: internal",
        )

    def test_cloudtrail(self):
        self.assertEqual(
            utils.resource_format(
                {
                    "Name": "trail-x",
                    "S3BucketName": "trail-x-bucket",
                    "IncludeGlobalServiceEvents": True,
                    "IsMultiRegionTrail": False,
                    "HomeRegion": "eu-west-2",
                    "TrailARN": "arn:aws:cloudtrail:eu-west-2:123456789012:trail/trail-x",
                    "LogFileValidationEnabled": True,
                    "HasCustomEventSelectors": False,
                    "HasInsightSelectors": False,
                    "IsOrganizationTrail": False,
                    "Tags": [],
                },
                "aws.cloudtrail",
            ),
            "trail-x",
        )

    def test_service_quota(self):
        self.assertEqual(
            utils.resource_format(
                {
                    "ServiceName": "Amazon EC2 Auto Scaling",
                    "QuotaName": "Auto Scaling groups per region",
                    "c7n:UsageMetric": {"metric": 54, "quota": 200},
                },
                "service-quota",
            ),
            "ServiceName: Amazon EC2 Auto Scaling QuotaName: Auto Scaling groups per region "
            "Quota: 200 Usage: 54\n",
        )

    def test_service_quota_none_usagemetric(self):
        self.assertEqual(
            utils.resource_format(
                {
                    "ServiceName": "AWS Cloud Map",
                    "QuotaName": "Namespaces per Region",
                    "c7n:MatchedFilters": ["UsageMetric"],
                },
                "service-quota",
            ),
            "ServiceName: AWS Cloud Map QuotaName: Namespaces per Region\n",
        )


class GetAwsUsernameFromEvent(unittest.TestCase):
    # note principalId is very org/domain specific for federated?, it would be
    # good to get confirmation from capone on this event / test.
    CLOUDTRAIL_EVENT = {
        "detail": {
            "userIdentity": {
                "type": "IAMUser",
                "principalId": "AIDAJ45Q7YFFAREXAMPLE",
                "arn": "arn:aws:iam::123456789012:user/michael_bolton",
                "accountId": "123456789012",
                "accessKeyId": "AKIAIOSFODNN7EXAMPLE",
                "userName": "michael_bolton",
            }
        }
    }

    def test_get(self):
        username = utils.get_aws_username_from_event(Mock(), self.CLOUDTRAIL_EVENT)
        self.assertEqual(username, "michael_bolton")

    def test_get_username_none(self):
        self.assertEqual(utils.get_aws_username_from_event(Mock(), None), None)

    def test_get_username_identity_none(self):
        evt = {"detail": {}}
        self.assertEqual(utils.get_aws_username_from_event(Mock(), evt), None)

    def test_get_username_assumed_role(self):
        evt = {"detail": {"userIdentity": {"type": "AssumedRole", "arn": "foo"}}}
        self.assertEqual(utils.get_aws_username_from_event(Mock(), evt), "foo")

    def test_get_username_assumed_role_instance(self):
        evt = {"detail": {"userIdentity": {"type": "AssumedRole", "arn": "foo/i-12345678"}}}
        self.assertEqual(utils.get_aws_username_from_event(Mock(), evt), None)

    def test_get_username_assumed_role_lambda(self):
        evt = {"detail": {"userIdentity": {"type": "AssumedRole", "arn": "foo/awslambda"}}}
        self.assertEqual(utils.get_aws_username_from_event(Mock(), evt), None)

    def test_get_username_assumed_role_colons(self):
        evt = {"detail": {"userIdentity": {"type": "AssumedRole", "arn": "foo/bar:baz:blam"}}}
        self.assertEqual(utils.get_aws_username_from_event(Mock(), evt), "baz:blam")

    def test_get_username_iam(self):
        evt = {"detail": {"userIdentity": {"type": "IAMUser", "userName": "bar"}}}
        self.assertEqual(utils.get_aws_username_from_event(Mock(), evt), "bar")

    def test_get_username_root(self):
        evt = {"detail": {"userIdentity": {"type": "Root"}}}
        self.assertEqual(utils.get_aws_username_from_event(Mock(), evt), None)

    def test_get_username_principalColon(self):
        evt = {"detail": {"userIdentity": {"type": "foo", "principalId": "bar:baz"}}}
        self.assertEqual(utils.get_aws_username_from_event(Mock(), evt), "baz")

    def test_get_username_principal(self):
        evt = {"detail": {"userIdentity": {"type": "foo", "principalId": "blam"}}}
        self.assertEqual(utils.get_aws_username_from_event(Mock(), evt), "blam")


class ProviderSelector(unittest.TestCase):
    azure_config = {"queue_url": "asq://"}
    aws_config = {"queue_url": "sqs://", "region": "us-east-1"}
    gcp_config = {"queue_url": "projects"}

    def test_get_providers(self):
        self.assertEqual(utils.get_provider(self.azure_config), utils.Providers.Azure)
        self.assertEqual(utils.get_provider(self.aws_config), utils.Providers.AWS)
        self.assertEqual(utils.get_provider(self.gcp_config), utils.Providers.GCP)

    def test_get_processor(self):
        logger = logging.getLogger()
        params = [
            (self.azure_config, MailerAzureQueueProcessor),
            (self.aws_config, MailerSqsQueueProcessor),
            (self.gcp_config, MailerGcpQueueProcessor),
        ]
        for mailer_config, processor in params:
            self.assertIsInstance(utils.get_processor(mailer_config, logger), processor)

    def test_missing_deps_guidance(self):
        """Make sure we catch failed imports and provide guidance around installing
        missing dependencies."""
        _real_import = builtins.__import__

        def fake_import_missing_deps(name, *args, **kwargs):
            if name.startswith("c7n_gcp") or name.startswith("c7n_azure"):
                raise ImportError()
            return _real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=fake_import_missing_deps):
            with self.assertRaisesRegex(ImportError, r"pip install c7n-mailer\[azure\]"):
                reload(c7n_mailer.azure_mailer.azure_queue_processor)
            with self.assertRaisesRegex(ImportError, r"pip install c7n-mailer\[gcp\]"):
                reload(c7n_mailer.gcp_mailer.gcp_queue_processor)


class DecryptTests(unittest.TestCase):
    @patch("c7n_mailer.utils.kms_decrypt")
    def test_kms_decrypt(self, kms_decrypt_mock):
        utils.decrypt({"queue_url": "aws", "test": "test"}, Mock(), Mock(), "test")
        kms_decrypt_mock.assert_called_once()

    @patch("c7n_mailer.azure_mailer.utils.azure_decrypt")
    def test_azure_decrypt(self, azure_decrypt_mock):
        utils.decrypt({"queue_url": "asq://", "test": "test"}, Mock(), Mock(), "test")
        azure_decrypt_mock.assert_called_once()

    @patch("c7n_mailer.gcp_mailer.utils.gcp_decrypt")
    def test_gcp_decrypt(self, gcp_decrypt_mock):
        utils.decrypt({"queue_url": "projects", "test": "test"}, Mock(), Mock(), "test")
        gcp_decrypt_mock.assert_called_once()

    def test_decrypt_none(self):
        self.assertEqual(utils.decrypt({"queue_url": "aws"}, Mock(), Mock(), "test"), None)
        self.assertEqual(utils.decrypt({"queue_url": "asq://"}, Mock(), Mock(), "test"), None)
        self.assertEqual(utils.decrypt({"queue_url": "projects"}, Mock(), Mock(), "test"), None)


class OtherTests(unittest.TestCase):
    def test_config_defaults(self):
        config = MAILER_CONFIG
        utils.setup_defaults(config)
        self.assertEqual(
            [
                config.get("region"),
                config.get("ses_region"),
                config.get("memory"),
                config.get("runtime"),
                config.get("timeout"),
                config.get("subnets"),
                config.get("security_groups"),
                config.get("contact_tags"),
                config.get("ldap_uri"),
                config.get("ldap_bind_dn"),
                config.get("ldap_bind_user"),
                config.get("ldap_bind_password"),
                config.get("datadog_api_key"),
                config.get("slack_token"),
                config.get("slack_webhook"),
                config.get("queue_url"),
            ],
            [
                "us-east-1",
                config.get("region"),
                1024,
                "python3.11",
                300,
                None,
                None,
                MAILER_CONFIG["contact_tags"],
                MAILER_CONFIG["ldap_uri"],
                None,
                None,
                None,
                None,
                None,
                None,
                MAILER_CONFIG["queue_url"],
            ],
        )

    def test_get_jinja_env(self):
        env = utils.get_jinja_env(MAILER_CONFIG["templates_folders"])
        self.assertEqual(env.__class__, jinja2.environment.Environment)

    def test_get_rendered_jinja(self):
        # Jinja paths must always be forward slashes regardless of operating system
        template_abs_filename = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "example.jinja")
        )
        template_abs_filename = template_abs_filename.replace("\\", "/")
        SQS_MESSAGE_1["action"]["template"] = template_abs_filename
        body = utils.get_rendered_jinja(
            ["test@test.com"],
            SQS_MESSAGE_1,
            [RESOURCE_1],
            logging.getLogger("c7n_mailer.utils.email"),
            "template",
            "default",
            MAILER_CONFIG["templates_folders"],
        )
        self.assertIsNotNone(body)

    def test_get_date_age(self):
        now = datetime.utcnow().isoformat() + "Z"
        sleep(1.0)
        assert utils.get_date_age(now) == 0
        assert utils.get_date_age(now, "seconds") >= 1

    def test_get_message_subject(self):
        subject = utils.get_message_subject(SQS_MESSAGE_1)
        self.assertEqual(
            subject,
            SQS_MESSAGE_1["action"]["subject"].replace("{{ account }}", SQS_MESSAGE_1["account"]),
        )

    def test_kms_decrypt(self):
        config = {"test": {"secret": "mysecretpassword"}}
        session_mock = Mock()
        session_mock.client().get_secret().value = "value"
        session_mock.get_session_for_resource.return_value = session_mock

        self.assertEqual(utils.kms_decrypt(config, Mock(), session_mock, "test"), config["test"])
