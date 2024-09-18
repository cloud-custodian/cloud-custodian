# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest
import time
import json
from c7n.exceptions import PolicyValidationError
from .common import event_data


class TestGlueConnections(BaseTest):

    def test_connections_query(self):
        session_factory = self.replay_flight_data("test_glue_query_resources")
        p = self.load_policy(
            {"name": "list-glue-connections", "resource": "glue-connection"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_connection_subnet_filter(self):
        session_factory = self.replay_flight_data("test_glue_subnet_filter")
        p = self.load_policy(
            {
                "name": "glue-connection",
                "resource": "glue-connection",
                "filters": [
                    {"type": "subnet", "key": "tag:Name", "value": "Default-48"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(
            resources[0]["PhysicalConnectionRequirements"]["SubnetId"],
            "subnet-3a334610",
        )

    def test_connection_sg_filter(self):
        session_factory = self.replay_flight_data("test_glue_sg_filter")
        p = self.load_policy(
            {
                "name": "glue-connection",
                "resource": "glue-connection",
                "filters": [
                    {"type": "security-group", "key": "GroupName", "value": "default"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(
            resources[0]["PhysicalConnectionRequirements"]["SecurityGroupIdList"],
            ["sg-6c7fa917"],
        )

    def test_connection_delete(self):
        session_factory = self.replay_flight_data("test_glue_delete_connection")
        p = self.load_policy(
            {
                "name": "glue-connection",
                "resource": "glue-connection",
                "filters": [{"ConnectionType": "JDBC"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("glue")
        connections = client.get_connections()["ConnectionList"]
        self.assertFalse(connections)

    def test_connection_password_hidden(self):
        session_factory = self.replay_flight_data("test_connection_password_hidden")
        p = self.load_policy(
            {
                "name": "glue-connection",
                "resource": "glue-connection",
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual('PASSWORD' in resources[0].get('ConnectionProperties'), False)

    def test_glue_connection_tag_untag(self):
        session_factory = self.replay_flight_data("test_glue_connection_tag_untag")
        p = self.load_policy(
            {
                "name": "glue-connection-tags",
                "resource": "glue-connection",
                "filters": [{"tag:owner": "pratyush"}],
                "actions": [{"type": "remove-tag", 'tags': ['owner']}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("glue")
        arn = p.resource_manager.generate_arn(resources[0]['Name'])
        tags = client.get_tags(ResourceArn=arn)
        self.assertEqual(tags.get('Tags'), {})

    def test_glue_query_resources_no_subnet(self):
        session_factory = self.replay_flight_data("test_glue_query_resources_no_subnet")
        p = self.load_policy(
            {
                "name": "list-glue-connections",
                "resource": "glue-connection",
                "filters": [
                    {
                        "type": "subnet",
                        "key": "tag:c7n-internal",
                        "op": "ne",
                        "value": "True",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)


class TestGlueDevEndpoints(BaseTest):

    def test_dev_endpoints_query(self):
        session_factory = self.replay_flight_data("test_dev_endpoints_query")
        p = self.load_policy(
            {"name": "list-glue-dev-endpoints", "resource": "glue-dev-endpoint"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_dev_endpoints_delete(self):
        session_factory = self.replay_flight_data("test_glue_dev_endpoint_delete")
        p = self.load_policy(
            {
                "name": "glue-dev-endpoint-delete",
                "resource": "glue-dev-endpoint",
                "filters": [{"PublicAddress": "present"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("glue")
        dev_endpoints = client.get_dev_endpoints()["DevEndpoints"]
        self.assertFalse(dev_endpoints)


class TestGlueTag(BaseTest):

    def test_glue_tags(self):
        session_factory = self.replay_flight_data("test_glue_tags")
        client = session_factory().client("glue")

        tags = client.get_tags(ResourceArn='arn:aws:glue:us-east-1:644160558196:devEndpoint/test')
        self.assertEqual(tags.get('Tags'), {})

        policy = {
            'name': 'test',
            'resource': 'glue-dev-endpoint',
            'actions': [
                {
                    'type': 'tag',
                    'key': 'abcd',
                    'value': 'xyz'
                },
            ]
        }
        p = self.load_policy(
            policy,
            config={'account_id': '644160558196'},
            session_factory=session_factory)

        resources = p.run()
        arn = p.resource_manager.generate_arn(resources[0]['EndpointName'])
        self.assertEqual(arn, 'arn:aws:glue:us-east-1:644160558196:devEndpoint/test')
        tags = client.get_tags(ResourceArn=arn)
        self.assertEqual(len(resources), 1)
        self.assertEqual(tags.get('Tags'), {'abcd': 'xyz'})

    def test_glue_untag(self):
        session_factory = self.replay_flight_data("test_glue_untag")

        policy = {
            'name': 'test',
            'resource': 'glue-dev-endpoint',
            'actions': [{'type': 'remove-tag', 'tags': ['abcd']}]
        }
        p = self.load_policy(
            policy,
            config={'account_id': '644160558196'},
            session_factory=session_factory)

        resources = p.run()
        client = session_factory().client("glue")
        arn = p.resource_manager.generate_arn(resources[0]['EndpointName'])
        tags = client.get_tags(ResourceArn=arn)

        self.assertEqual(arn, 'arn:aws:glue:us-east-1:644160558196:devEndpoint/test')
        self.assertEqual(tags.get('Tags'), {})
        self.assertEqual(len(resources), 1)

    def test_glue_job_tag(self):
        session_factory = self.replay_flight_data("test_glue_job_tags")
        client = session_factory().client("glue")

        policy = {
            'name': 'test',
            'resource': 'glue-job',
            'filters': [{'tag:abcd': 'absent'}],
            'actions': [
                {
                    'type': 'tag',
                    'key': 'abcd',
                    'value': 'xyz'
                },
            ]
        }
        p = self.load_policy(
            policy,
            config={'account_id': '644160558196'},
            session_factory=session_factory)

        resources = p.run()
        arn = p.resource_manager.generate_arn(resources[0]['Name'])
        self.assertEqual(arn, 'arn:aws:glue:us-east-1:644160558196:job/test')
        tags = client.get_tags(ResourceArn=arn)
        self.assertEqual(len(resources), 1)
        self.assertEqual(tags.get('Tags'), {'abcd': 'xyz'})

    def test_glue_job_untag(self):
        session_factory = self.replay_flight_data("test_glue_job_untag")
        policy = {
            'name': 'test',
            'resource': 'glue-job',
            'filters': [{'tag:abcd': 'present'}],
            'actions': [{'type': 'remove-tag', 'tags': ['abcd']}]
        }
        p = self.load_policy(
            policy,
            config={'account_id': '644160558196'},
            session_factory=session_factory)

        resources = p.run()
        client = session_factory().client("glue")
        arn = p.resource_manager.generate_arn(resources[0]['Name'])
        tags = client.get_tags(ResourceArn=arn)

        self.assertEqual(arn, 'arn:aws:glue:us-east-1:644160558196:job/test')
        self.assertEqual(tags.get('Tags'), {})
        self.assertEqual(len(resources), 1)

    def test_glue_crawler_tag(self):
        session_factory = self.replay_flight_data("test_crawler_tags")
        client = session_factory().client("glue")

        policy = {
            'name': 'test',
            'resource': 'glue-crawler',
            'filters': [{'tag:abcd': 'absent'}],
            'actions': [
                {
                    'type': 'tag',
                    'key': 'abcd',
                    'value': 'xyz'
                },
            ]
        }
        p = self.load_policy(
            policy,
            config={'account_id': '644160558196'},
            session_factory=session_factory)

        resources = p.run()
        arn = p.resource_manager.generate_arn(resources[0]['Name'])
        self.assertEqual(arn, 'arn:aws:glue:us-east-1:644160558196:crawler/test')
        tags = client.get_tags(ResourceArn=arn)
        self.assertEqual(len(resources), 1)
        self.assertEqual(tags.get('Tags'), {'abcd': 'xyz'})

    def test_glue_crawler_untag(self):
        session_factory = self.replay_flight_data("test_glue_crawler_untag")

        policy = {
            'name': 'test',
            'resource': 'glue-crawler',
            'filters': [{'tag:abcd': 'present'}],
            'actions': [{'type': 'remove-tag', 'tags': ['abcd']}]
        }
        p = self.load_policy(
            policy,
            config={'account_id': '644160558196'},
            session_factory=session_factory)

        resources = p.run()
        client = session_factory().client("glue")
        arn = p.resource_manager.generate_arn(resources[0]['Name'])
        tags = client.get_tags(ResourceArn=arn)

        self.assertEqual(arn, 'arn:aws:glue:us-east-1:644160558196:crawler/test')
        self.assertEqual(tags.get('Tags'), {})
        self.assertEqual(len(resources), 1)


class TestGlueJobs(BaseTest):

    def test_jobs_delete(self):
        session_factory = self.replay_flight_data("test_glue_job_delete")
        p = self.load_policy(
            {
                "name": "glue-job-delete",
                "resource": "glue-job",
                "filters": [{"Name": "test"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("glue")
        jobs = client.get_jobs()["Jobs"]
        self.assertFalse(jobs)

    def test_enable_metrics(self):
        session_factory = self.replay_flight_data("test_glue_job_enable_metrics")
        p = self.load_policy(
            {
                "name": "glue-job-enable-metrics",
                "resource": "glue-job",
                "filters": [
                    {
                        "type": "value",
                        "key": 'DefaultArguments."--enable-metrics"',
                        "value": "absent",
                    }
                ],
                "actions": [{"type": "toggle-metrics", "enabled": True}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)
        client = session_factory().client("glue")
        jobs = client.get_jobs()["Jobs"]
        for job in jobs:
            self.assertIn("--enable-metrics", job["DefaultArguments"])

    def test_disable_metrics(self):
        session_factory = self.replay_flight_data("test_glue_job_disable_metrics")
        p = self.load_policy(
            {
                "name": "glue-job-disable-metrics",
                "resource": "glue-job",
                "filters": [
                    {
                        "type": "value",
                        "key": 'DefaultArguments."--enable-metrics"',
                        "value": "present",
                    }
                ],
                "actions": [{"type": "toggle-metrics", "enabled": False}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)
        client = session_factory().client("glue")
        jobs = client.get_jobs()["Jobs"]
        for job in jobs:
            self.assertNotIn("--enable-metrics", job["DefaultArguments"])


class TestGlueCrawlers(BaseTest):

    def test_crawlers_delete(self):
        session_factory = self.replay_flight_data("test_glue_crawler_delete")
        p = self.load_policy(
            {
                "name": "glue-crawler-delete",
                "resource": "glue-crawler",
                "filters": [{"Name": "test"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("glue")
        crawlers = client.get_crawlers()["Crawlers"]
        self.assertFalse("test" in [c.get("Name") for c in crawlers])

    def test_security_config_missing_filter(self):
        p = self.load_policy(
            {
                "name": "glue-crawler-security-config",
                "resource": "glue-crawler",
                "filters": [{
                    "type": "security-config",
                    "missing": True}]
            },
        )
        resources = p.resource_manager.filter_resources([{
            'Name': 'bad-crawler',
            'S3Targets': [{'Path': 's3://wicked'}]}])
        assert len(resources) == 1
        assert resources[0]['Name'] == 'bad-crawler'

    def test_security_config_filter(self):
        session_factory = self.replay_flight_data("test_glue_sec_config_filter")
        p = self.load_policy(
            {
                "name": "glue-crawler-security-config",
                "resource": "glue-crawler",
                "filters": [
                    {"type": "security-config",
                     "key": "EncryptionConfiguration.CloudWatchEncryption.CloudWatchEncryptionMode",
                     "value": "SSE-KMS",
                     "op": "eq"},
                    {"type": "security-config",
                     "key": "EncryptionConfiguration.CloudWatchEncryption.KmsKeyArn",
                     "value": "arn:aws:kms:us-east-1:123456789123:key/358f7699-4ea5-455a-9c78-1c868301e5a8", # noqa
                     "op": "eq"}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'test-filter-crawler')


class TestGlueTables(BaseTest):
    def test_tables_delete(self):
        session_factory = self.replay_flight_data("test_glue_table_delete")
        p = self.load_policy(
            {
                "name": "glue-table-delete",
                "resource": "glue-table",
                "filters": [{"Name": "test"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("glue")
        tables = client.get_tables(DatabaseName='test')["TableList"]
        self.assertFalse("test" in [t.get("Name") for t in tables])


class TestGlueDatabases(BaseTest):

    def test_databases_delete(self):
        session_factory = self.replay_flight_data("test_glue_database_delete")
        p = self.load_policy(
            {
                "name": "glue-database-delete",
                "resource": "glue-database",
                "filters": [{"Name": "test"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("glue")
        databases = client.get_databases()
        self.assertFalse("test" in [t.get("Name") for t in databases.get("DatabaseList", [])])


class TestGlueClassifiers(BaseTest):

    def test_classifiers_delete(self):
        session_factory = self.replay_flight_data("test_glue_classifier_delete")
        p = self.load_policy(
            {
                "name": "glue-classifier-delete",
                "resource": "glue-classifier",
                "filters": [{"CsvClassifier.Name": "test"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("glue")
        classifiers = client.get_classifiers()
        self.assertFalse("test" in [t.get('CsvClassifier').get("Name")
            for t in classifiers.get("Classifiers", [])])


class GlueMLTransform(BaseTest):

    def test_ml_transforms_delete(self):
        session_factory = self.replay_flight_data("test_glue_ml_transform_delete")
        p = self.load_policy(
            {
                "name": "glue-ml-transform-delete",
                "resource": "glue-ml-transform",
                "filters": [{"Name": 'test'}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("glue")
        ml_transforms = client.get_ml_transforms()
        self.assertFalse("test" in [t.get("Name") for t in ml_transforms.get("Transforms", [])])


class TestGlueSecurityConfiguration(BaseTest):

    def test_security_configurations_delete(self):
        session_factory = self.replay_flight_data("test_glue_security_configuration_delete")
        p = self.load_policy(
            {
                "name": "glue-security-configuration-delete",
                "resource": "glue-security-configuration",
                "filters": [{"Name": "test"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("glue")
        security_configrations = client.get_security_configurations()
        self.assertFalse("test" in [t.get("Name")
            for t in security_configrations.get("SecurityConfigurations", [])])

    def test_kms_alias(self):
        factory = self.replay_flight_data("test_glue_security_configuration_kms_key_filter")
        p = self.load_policy(
            {
                "name": "glue-security-configuration-s3-kms-alias",
                "resource": "glue-security-configuration",
                "filters": [
                    {
                        "type": "kms-key",
                        "key": "c7n:AliasName",
                        "value": "^(alias/)",
                        "op": "regex",
                        "key-type": "cloudwatch"
                    }
                ]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['EncryptionConfiguration']['CloudWatchEncryption']['KmsKeyArn'],
            'arn:aws:kms:us-east-1:0123456789012:key/358f7699-4ea5-455a-9c78-1c868301e5a8')


class TestGlueTriggers(BaseTest):

    def test_triggers_delete(self):
        session_factory = self.replay_flight_data("test_glue_trigger_delete")
        p = self.load_policy(
            {
                "name": "glue-trigger-delete",
                "resource": "glue-trigger",
                "filters": [{"Name": "test"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        if self.recording:
            time.sleep(60)
        client = session_factory().client("glue")
        triggers = client.get_triggers()
        self.assertFalse("test" in [t.get("Name") for t in triggers.get("Triggers", [])])


class TestGlueWorkflows(BaseTest):

    def test_workflows_delete(self):
        session_factory = self.replay_flight_data("test_glue_workflow_delete")
        p = self.load_policy(
            {
                "name": "glue-workflow-delete",
                "resource": "glue-workflow",
                "filters": [{"Name": "test"}],
                "actions": [{"type": "delete"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("glue")
        workflows = client.list_workflows()
        self.assertFalse("test" in [t.get("Name") for t in workflows.get("Workflows", [])])


class TestGlueDataCatalog(BaseTest):

    def test_glue_datacat_put_encryption(self):
        session_factory = self.replay_flight_data("test_glue_datacat_put_encryption")
        client = session_factory().client("glue")
        cat_setting = client.get_data_catalog_encryption_settings()
        self.assertEqual(cat_setting.get('DataCatalogEncryptionSettings').get(
            'EncryptionAtRest').get('SseAwsKmsKeyId'), 'alias/skunk/trails')
        p = self.load_policy(
            {
                "name": "glue-security-config",
                "resource": "glue-catalog",
                'filters': [{
                    'type': 'value',
                    'key': 'DataCatalogEncryptionSettings.EncryptionAtRest.SseAwsKmsKeyId',
                    'value': 'alias/skunk/trails',
                    'op': 'eq'},
                ],
                "actions": [{
                    "type": "set-encryption",
                    "attributes": {
                        "EncryptionAtRest": {
                            "CatalogEncryptionMode": "SSE-KMS",
                            "SseAwsKmsKeyId": "alias/skunk/glue/encrypted"},
                    },
                }]
            },
            session_factory=session_factory,)

        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("glue")
        datacatlog = client.get_data_catalog_encryption_settings()
        self.assertEqual(datacatlog.get('DataCatalogEncryptionSettings').get(
            'EncryptionAtRest'),
            {'CatalogEncryptionMode': 'SSE-KMS', 'SseAwsKmsKeyId': 'alias/skunk/glue/encrypted'})

    def test_glue_datacat_key_alias_apply_enc(self):
        session_factory = self.replay_flight_data("test_glue_datacat_key_alias_apply_enc")
        c = session_factory().client('kms')
        key_id = 'arn:aws:kms:us-east-1:644160558196:key/7d9388c0-8c78-4acb-ad3c-b9d1764522b2'
        key_alias = c.list_aliases(KeyId=key_id)
        self.assertEqual(key_alias.get('Aliases')[0].get('AliasName'), 'alias/data-sync-kms-key')
        client = session_factory().client('glue')
        enc_setting = client.get_data_catalog_encryption_settings()
        self.assertEqual(enc_setting.get('DataCatalogEncryptionSettings').get(
            'EncryptionAtRest').get('SseAwsKmsKeyId'), key_id)
        self.assertEqual(enc_setting.get('DataCatalogEncryptionSettings').get(
            'ConnectionPasswordEncryption').get(
              'ReturnConnectionPasswordEncrypted'), False)
        p = self.load_policy(
            {
                'name': 'glue-catalog-encryption',
                "resource": 'glue-catalog',
                'filters': [{
                    'type': 'kms-key',
                    'key-type': 'EncryptionAtRest',
                    'key': 'c7n:AliasName',
                    'value': 'alias/data-sync-kms-key',
                    'op': 'eq'},
                ],
                'actions': [{
                    'type': 'set-encryption',
                    'attributes': {
                        'ConnectionPasswordEncryption': {
                            'ReturnConnectionPasswordEncrypted': True,
                            'AwsKmsKeyId': 'alias/skunk/glue/encrypted'},
                    },
                }]
            },
            session_factory=session_factory,)

        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client("glue")
        datacatlog = client.get_data_catalog_encryption_settings()
        self.assertEqual(datacatlog.get('DataCatalogEncryptionSettings').get(
            'EncryptionAtRest'),
            {'CatalogEncryptionMode': 'SSE-KMS', 'SseAwsKmsKeyId': key_id})
        self.assertEqual(datacatlog.get('DataCatalogEncryptionSettings').get(
            'ConnectionPasswordEncryption'),
            {'ReturnConnectionPasswordEncrypted': True,
             'AwsKmsKeyId': 'alias/skunk/glue/encrypted'})

    def test_glue_catalog_cross_account(self):
        session_factory = self.replay_flight_data("test_glue_catalog_cross_account")
        p = self.load_policy(
            {
                "name": "glue-catalog-cross-account",
                "resource": "glue-catalog",
                "filters": [{"type": "cross-account"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_catalog_remove_matched(self):
        session_factory = self.replay_flight_data("test_catalog_remove_matched")
        client = session_factory().client("glue")
        client.put_resource_policy(PolicyInJson=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "SpecificAllow",
                        "Effect": "Allow",
                        "Principal": {"AWS": "arn:aws:iam::644160558196:root"},
                        "Action": "glue:GetDatabase",
                        "Resource": "arn:aws:glue:us-east-1:644160558196:catalog"
                    },
                    {
                        "Sid": "CrossAccount",
                        "Effect": "Allow",
                        "Principal": {"AWS": "arn:aws:iam::123456789123:root"},
                        "Action": "glue:GetDatabase",
                        "Resource": "arn:aws:glue:us-east-1:644160558196:catalog"
                    },
                ]
            }))
        p = self.load_policy(
            {
                "name": "glue-catalog-rm-matched",
                "resource": "glue-catalog",
                "filters": [{"type": "cross-account"}],
                "actions": [{"type": "remove-statements", "statement_ids": "matched"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        data = json.loads(client.get_resource_policy().get("PolicyInJson"))
        self.assertEqual(len(data.get('Statement')), 1)
        self.assertEqual([s['Sid'] for s in data.get('Statement')], ["SpecificAllow"])

    def test_remove_statements_validation_error(self):
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {
                "name": "glue-catalog-remove-matched",
                "resource": "glue-catalog",
                "actions": [{"type": "remove-statements", "statement_ids": "matched"}],
            }
        )

    def test_catalog_change_encryption_event(self):
        session_factory = self.replay_flight_data("test_catalog_change_encryption_event")
        session = session_factory()
        client = session.client("glue")
        before_cat_setting = client.get_data_catalog_encryption_settings()
        self.assertJmes(
            'DataCatalogEncryptionSettings.EncryptionAtRest.CatalogEncryptionMode',
            before_cat_setting,
            'DISABLED'
        )
        self.assertJmes(
            'DataCatalogEncryptionSettings.EncryptionAtRest.SseAwsKmsKeyId',
            before_cat_setting,
            None
        )
        p = self.load_policy(
            {
                "name": "net-change-rbp-cross-account",
                "resource": "glue-catalog",
                "mode": {
                    "type": "cloudtrail",
                    "role": "arn:aws:iam::644160558196:role/CloudCustodianRole",
                    "events": [
                        {
                            "source": "glue.amazonaws.com",
                            "event": "PutDataCatalogEncryptionSettings",
                            "ids": "userIdentity.accountId"
                        }
                    ],
                },
                'filters': [{
                    'type': 'value',
                    'key': 'DataCatalogEncryptionSettings.EncryptionAtRest.SseAwsKmsKeyId',
                    'value': 'alias/skunk/trails',
                    'op': 'ne'},
                ],
                "actions": [
                    {
                        "type": "set-encryption",
                        "attributes": {
                            "EncryptionAtRest": {
                                "CatalogEncryptionMode": "SSE-KMS"
                            }
                        }
                    }
                ],
            },
            session_factory=session_factory,
        )
        p.push(event_data("event-cloud-trail-catalog-set-encryption.json"), None)
        after_cat_setting = client.get_data_catalog_encryption_settings()
        self.assertJmes(
            'DataCatalogEncryptionSettings.EncryptionAtRest.CatalogEncryptionMode',
            after_cat_setting,
            'SSE-KMS'
        )
        self.assertJmes(
            'DataCatalogEncryptionSettings.EncryptionAtRest.SseAwsKmsKeyId',
            after_cat_setting,
            'alias/aws/glue'
        )

    def test_catalog_change_rbp_event(self):
        session_factory = self.replay_flight_data("test_catalog_change_rbp_event")
        session = session_factory()
        client = session.client("glue")
        before_cat_setting = client.get_resource_policy()
        assert 'o-4amkskbcf3' in before_cat_setting.get('PolicyInJson')
        p = self.load_policy(
            {
                "name": "net-change-rbp-cross-account",
                "resource": "glue-catalog",
                "mode": {
                    "type": "cloudtrail",
                    "role": "arn:aws:iam::644160558196:role/CloudCustodianRole",
                    "events": [
                        {
                            "source": "glue.amazonaws.com",
                            "event": "PutResourcePolicy",
                            "ids": "awsRegion"
                        }
                    ],
                },
                "filters": [
                    {
                        "type": "cross-account",
                        "whitelist_orgids": [
                            "o-4amkskbcf1"
                        ]
                    }
                ],
                "actions": [{"type": "remove-statements", "statement_ids": "matched"}],
            },
            session_factory=session_factory,
        )
        p.push(event_data("event-cloud-trail-catalog-put-resource-policy.json"), None)
        after_cat_setting = client.get_resource_policy()
        assert 'o-4amkskbcf3' not in after_cat_setting.get('PolicyInJson')
