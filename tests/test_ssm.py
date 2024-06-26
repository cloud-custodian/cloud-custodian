# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import time

from c7n.exceptions import PolicyValidationError
from pytest_terraform import terraform

from .common import BaseTest, functional


class TestOpsCenter(BaseTest):

    def test_post_ops_item(self):
        factory = self.replay_flight_data('test_post_ops_item')
        p = self.load_policy({
            'name': 'checking-lambdas',
            'description': 'something good',
            'resource': 'aws.lambda',
            'source': 'config',
            'query': [
                {'clause': "resourceId = 'custodian-aws'"}],
            'actions': [{
                'type': 'post-item'}]},
            session_factory=factory, config={'region': 'us-east-1'})
        resources = p.run()
        client = factory().client('ssm', region_name='us-east-1')
        item = client.get_ops_item(
            OpsItemId=resources[0]['c7n:opsitem']).get('OpsItem')
        arn = p.resource_manager.get_arns(resources)[0]
        self.assertTrue(
            arn in item['OperationalData']['/aws/resources']['Value'])
        self.assertTrue(item['OperationalData']['/aws/dedup'])
        self.assertEqual(item['Title'], p.name)
        self.assertEqual(item['Description'], p.data['description'])

    def test_ops_item_filter(self):
        factory = self.replay_flight_data('test_ops_item_filter')
        p = self.load_policy({
            'name': 'checking-lambdas',
            'description': 'something good',
            'resource': 'aws.lambda',
            'source': 'config',
            'query': [
                {'clause': "resourceId = 'custodian-aws'"}],
            'filters': [{
                'type': 'ops-item',
                'priority': [3, 4, 5],
                'title': 'checking-lambdas',
                'source': 'Cloud Custodian',
            }]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['c7n:opsitems'],
            ['oi-9be57440dcb3'])

    def test_post_ops_item_update(self):
        factory = self.replay_flight_data('test_post_ops_item_update')
        p = self.load_policy({
            'name': 'checking-lambdas',
            'description': 'something good',
            'resource': 'aws.lambda',
            'source': 'config',
            'query': [
                {'clause': "resourceId = 'custodian-nuke-emr'"}],
            'actions': [{
                'type': 'post-item'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client('ssm', region_name='us-east-1')
        item = client.get_ops_item(
            OpsItemId=resources[0]['c7n:opsitem']).get('OpsItem')
        self.assertEqual(
            json.loads(item['OperationalData']['/aws/resources']['Value']),
            [{'arn': 'arn:aws:lambda:us-east-1::function:custodian-aws'},
             {'arn': 'arn:aws:lambda:us-east-1::function:custodian-nuke-emr'}])

    def test_update_ops_item(self):
        factory = self.replay_flight_data('test_update_ops_item')
        p = self.load_policy({
            'name': 'checking-lambdas',
            'description': 'something good',
            'resource': 'aws.ops-item',
            'query': [
                {'Key': 'Status', 'Operator': 'Equal', 'Values': ['Open']}
            ],
            'actions': [{
                'type': 'update',
                'topics': ['arn:aws:sns:us-west-2:644160558196:aws-command'],
                'status': 'Resolved',
            }]},
            config={'region': 'us-west-2'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = factory().client('ssm', region_name='us-west-2')
        if self.recording:
            time.sleep(5)
        item = client.get_ops_item(
            OpsItemId=resources[0]['OpsItemId'])['OpsItem']
        self.assertEqual(item['Status'], 'Resolved')
        self.assertEqual(
            item['Notifications'],
            [{'Arn': 'arn:aws:sns:us-west-2:644160558196:aws-command'}])

    def test_invalid_resource_query(self):
        self.assertRaises(
            PolicyValidationError, self.load_policy,
            {'name': 'value',
             'resource': 'aws.ops-item',
             'query': [
                 {'Key': 'Status', 'Operator': 'Equals', 'Values': ['Open']}]},
            validate=True)

    def test_get_resources(self):
        factory = self.replay_flight_data('test_ops_item_get_resources')
        p = self.load_policy({
            'name': 'foo',
            'resource': 'aws.ops-item'},
            session_factory=factory,
            config={'region': 'us-east-1'})
        resources = p.resource_manager.get_resources('oi-5aa4c36439ed')
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['OpsItemId'], 'oi-5aa4c36439ed')


class TestSSM(BaseTest):

    def test_ec2_ssm_send_command_validate(self):
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {'name': 'ssm-instances',
             'resource': 'aws.ec2',
             'actions': [
                 {'type': 'send-command',
                  'command': {
                      'DocumentName': 'AWS-RunShellScript'}}]},
            validate=True)

    def test_ssm_send_command(self):
        factory = self.replay_flight_data('test_ssm_send_command')
        p = self.load_policy({
            'name': 'ssm-instances',
            'resource': 'ssm-managed-instance',
            'filters': [{"PingStatus": "Online"}],
            'actions': [
                {'type': 'send-command',
                 'command': {
                     'DocumentName': 'AWS-RunShellScript',
                     'Parameters': {
                         'commands': [
                             'wget https://pkg.osquery.io/deb/osquery_3.3.0_1.linux.amd64.deb',
                             'dpkg -i osquery_3.3.0_1.linux.amd64.deb']}}}]},
            session_factory=factory, config={'region': 'us-east-2'})
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue('c7n:SendCommand' in resources[0])

        if self.recording:
            time.sleep(5)

        result = factory().client('ssm').get_command_invocation(
            InstanceId=resources[0]['InstanceId'],
            CommandId=resources[0]['c7n:SendCommand'][0])
        self.assertEqual(result['Status'], 'Success')

    def test_ssm_parameter_delete(self):
        session_factory = self.replay_flight_data("test_ssm_parameter_delete")
        p = self.load_policy({
            'name': 'ssm-param-tags',
            'resource': 'ssm-parameter',
            'actions': ['delete']},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'not_secret')
        client = session_factory().client('ssm')
        if self.recording:
            time.sleep(1)
        self.assertEqual(
            client.describe_parameters(
                Filters=[{'Key': 'Name', 'Values': [resources[0]['Name']]}])['Parameters'],
            [])

    def test_ssm_parameter_delete_non_existant(self):
        session_factory = self.replay_flight_data("test_ssm_parameter_delete_non_existant")
        p = self.load_policy({
            'name': 'ssm-param-tags',
            'resource': 'ssm-parameter',
            'actions': ['delete']},
            session_factory=session_factory)

        # if it raises the test fails
        p.resource_manager.actions[0].process(
            [{'Name': 'unicorn'}])

    def test_ssm_parameter_tag_arn(self):
        session_factory = self.replay_flight_data("test_ssm_parameter_tag_arn")
        p = self.load_policy({
            'name': 'ssm-param-tags',
            'resource': 'ssm-parameter',
            'filters': [{'tag:Env': 'present'}]},
            config={'account_id': '123456789123'},
            session_factory=session_factory)
        resources = p.resource_manager.get_resources(['/gittersearch/token'])
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['Tags'],
            [{'Key': 'App', 'Value': 'GitterSearch'},
             {'Key': 'Env', 'Value': 'Dev'}])

    @functional
    def test_ssm_parameter_not_secure(self):
        session_factory = self.replay_flight_data("test_ssm_parameter_not_secure")
        client = session_factory().client("ssm")

        client.put_parameter(Name='test-name',
                             Type='String',
                             Overwrite=True,
                             Value='test-value')

        client.put_parameter(Name='secure-test-name',
                             Type='SecureString',
                             Overwrite=True,
                             Value='secure-test-value')

        p = self.load_policy(
            {
                "name": "ssm-parameter-not-secure",
                "resource": "ssm-parameter",
                "filters": [{"type": "value",
                             "op": "ne",
                             "key": "Type",
                             "value": "SecureString"}]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.addCleanup(client.delete_parameters, Names=['test-name', 'secure-test-name'])

    def test_ssm_activation_expired(self):
        session_factory = self.replay_flight_data("test_ssm_activation_expired")
        p = self.load_policy(
            {
                "name": "ssm-list-expired-activations",
                "resource": "ssm-activation",
                "filters": [{"type": "value",
                             "key": "Expired",
                             "value": True}]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_ssm_get_manager_instances(self):
        session_factory = self.replay_flight_data("test_ssm_get_managed_instances")
        p = self.load_policy(
            {
                "name": "ssm-get-managed-instances",
                "resource": "ssm-managed-instance"
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["InstanceId"], "mi-1111aa111aa11a111")

    def test_get_ssm_documents(self):
        session_factory = self.replay_flight_data("test_get_ssm_documents")
        p = self.load_policy(
            {
                "name": "retrieve-ssm-documents",
                "resource": "ssm-document",
                "filters": [
                    {
                        "type": "cross-account",
                        "whitelist": ["xxxxxxxxxxxx"]
                    }
                ]
            },
            session_factory=session_factory,
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["c7n:CrossAccountViolations"][0], "yyyyyyyyyyyy")

    def test_ssm_document_remove_sharing(self):
        session_factory = self.replay_flight_data("test_ssm_document_remove_sharing")
        client = session_factory().client("ssm")
        p = self.load_policy(
            {
                "name": "remove-sharing-ssm-documents",
                "resource": "ssm-document",
                "filters": [
                    {
                        "type": "cross-account",
                        "whitelist": ["xxxxxxxxxxxx"]
                    }
                ],
                "actions": [
                    {
                        "type": "set-sharing",
                        "remove": "matched"
                    }
                ]
            },
            session_factory=session_factory,
        )
        p.run()
        permissions = client.describe_document_permission(
            Name='Test-Document-1',
            PermissionType='Share'
        )
        self.assertEqual(len(permissions.get('AccountIds')), 1)
        self.assertEqual(permissions.get('AccountIds'), ['xxxxxxxxxxxx'])

    def test_ssm_document_add_sharing(self):
        session_factory = self.replay_flight_data("test_ssm_document_add_sharing")
        client = session_factory().client("ssm")
        p = self.load_policy(
            {
                "name": "add-sharing-ssm-documents",
                "resource": "ssm-document",
                "actions": [
                    {
                        "type": "set-sharing",
                        "add": ['yyyyyyyyyyyy']
                    }
                ],
            },
            session_factory=session_factory,
        )
        p.run()
        permissions = client.describe_document_permission(
            Name='Test-Document-1',
            PermissionType='Share'
        )
        self.assertEqual(len(permissions.get('AccountIds')), 2)
        self.assertEqual(permissions.get('AccountIds'), ['xxxxxxxxxxxx', 'yyyyyyyyyyyy'])

    def test_ssm_document_delete(self):
        session_factory = self.replay_flight_data("test_ssm_document_delete")
        client = session_factory().client("ssm")
        p = self.load_policy(
            {
                "name": "delete-ssm-documents",
                "resource": "ssm-document",
                "filters": [
                    {
                        "type": "cross-account",
                        "whitelist": ["xxxxxxxxxxxx"]
                    }
                ],
                "actions": [
                    {
                        "type": "delete",
                        "force": True
                    }
                ]
            },
            session_factory=session_factory,
        )
        p.run()
        try:
            client.get_document(
                Name='Test-Document-1',
            )
        except Exception as e:
            self.assertTrue(e, client.exceptions.InvalidDocument)

    def test_ssm_document_delete_error(self):
        session_factory = self.replay_flight_data("test_ssm_document_delete")
        client = session_factory().client("ssm")
        p = self.load_policy(
            {
                "name": "delete-ssm-documents-error",
                "resource": "ssm-document",
                "filters": [
                    {
                        "type": "cross-account",
                        "whitelist": ["xxxxxxxxxxxx"]
                    }
                ],
                "actions": [
                    {
                        "type": "delete",
                        "force": False
                    }
                ]
            },
            session_factory=session_factory,
        )

        try:
            p.run()
        except Exception as e:
            self.assertTrue(e, client.exceptions.InvalidDocumentOperation)

    def test_ssm_document_tag(self):
        session_factory = self.replay_flight_data("test_ssm_document_tag")
        client = session_factory().client("ssm")
        p = self.load_policy(
            {
                "name": "ssm-document-tag",
                "resource": "ssm-document",
                "filters": [{"Name": "Test-Document-1"}],
                "actions": [
                    {
                        "type": "tag",
                        "key": "TestTag",
                        "value": "c7n"
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory(region="us-east-1").client("ssm")
        tags = client.list_tags_for_resource(ResourceType='Document', ResourceId='Test-Document-1')
        self.assertEqual(tags["TagList"][0]['Key'], 'TestTag')
        self.assertEqual(tags["TagList"][0]['Value'], 'c7n')

        p = self.load_policy(
            {
                "name": "ssm-document-untag",
                "resource": "ssm-document",
                "filters": [{"tag:TestTag": "c7n"}],
                "actions": [{"type": "remove-tag", "tags": ["TestTag"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        tags = client.list_tags_for_resource(ResourceType='Document', ResourceId='Test-Document-1')
        self.assertEqual(len(tags["TagList"]), 0)

    def test_get_data_sync_resources(self):
        session_factory = self.replay_flight_data("test_get_data_sync_resources")
        p = self.load_policy(
            {
                "name": "ssm-get-data-sync-resources",
                "resource": "ssm-data-sync"
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 3)

    def test_data_sync_kms_key_filter(self):
        session_factory = self.replay_flight_data("test_data_sync_kms_filter")
        p = self.load_policy(
            {
                "name": "ssm-get-data-sync-resources",
                "resource": "ssm-data-sync",
                "filters": [
                    {
                        "type": "kms-key",
                        "key": "c7n:AliasName",
                        "value": "data-sync-kms-key",
                    }
                ]
            },
            session_factory=session_factory,
        )
        resource = p.run()
        self.assertEqual(len(resource), 1)
        self.assertEqual(resource[0]["S3Destination"]["BucketName"], "data-sync-destination-bucket")

    def test_data_sync_value_filter(self):
        session_factory = self.replay_flight_data("test_data_sync_value_filter")
        p = self.load_policy(
            {
                "name": "ssm-data-sync-value-filter",
                "resource": "ssm-data-sync",
                'filters': [
                    {
                        'type': 'value',
                        'key': 'S3Destination.BucketName',
                        'value': ['c7n-ssm'],
                        'op': 'in'
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["S3Destination"]["BucketName"], "c7n-ssm")

    def test_data_sync_delete(self):
        session_factory = self.replay_flight_data("test_data_sync_delete")
        p = self.load_policy(
            {
                "name": "ssm-delete-data-sync-resources",
                "resource": "ssm-data-sync",
                'filters': [
                    {
                        'type': 'value',
                        'key': 'S3Destination.BucketName',
                        'value': ['data-sync-destination-bucket'],
                        'op': 'in'
                    }
                ],
                'actions': [
                    {
                        'type': 'delete'
                    }
                ]
            },
            session_factory=session_factory,
        )

        p.run()
        client = session_factory().client('ssm', region_name='us-east-1')
        data_syncs = client.list_resource_data_sync(SyncType='SyncToDestination')
        self.assertEqual(len(data_syncs.get('ResourceDataSyncItems')), 1)

    def test_data_sync_delete_error(self):
        session_factory = self.replay_flight_data("test_data_sync_delete_error")
        p = self.load_policy(
            {
                "name": "ssm-delete-data-sync-resources",
                "resource": "ssm-data-sync",
                'actions': [
                    {
                        'type': 'delete'
                    }
                ]
            },
            session_factory=session_factory,
        )

        data_syncs = p.run()
        self.assertEqual(len(data_syncs), 3)

    def test_ssm_session_manager_terminate(self):
        session_factory = self.replay_flight_data("test_ssm_session_manager_terminate")
        p = self.load_policy({
            'name': 'ssm-session-manager',
            'resource': 'ssm-session-manager',
            'actions': [
                    {
                        'type': 'terminate'
                    }
                ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('ssm', region_name='us-east-1')
        sessions = client.describe_sessions(State="Active")
        self.assertEqual(len(sessions["Sessions"]), 0)


@terraform("ssm_patch_group")
def test_ssm_patch_group_query(test, ssm_patch_group):
    factory = test.replay_flight_data("test_ssm_patch_group_query")

    policy = test.load_policy({
      "name": "test-aws-ssm-patch-group",
      "resource": "aws.ssm-patch-group"
    }, session_factory=factory)

    resources = policy.run()
    assert len(resources) > 0
    assert resources[0]['PatchGroup'] == 'patch-group-name'
