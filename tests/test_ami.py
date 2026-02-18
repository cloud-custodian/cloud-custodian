# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.exceptions import ClientError, PolicyValidationError
from c7n.resources.ami import ErrorHandler
from c7n.query import DescribeSource
from c7n.utils import jmespath_search
from .common import BaseTest


class TestAMI(BaseTest):

    def test_query(self):
        factory = self.replay_flight_data("test_ami")
        p = self.load_policy(
            {
                "name": "test-ami",
                "resource": "ami",
                "filters": [
                    {"Name": "LambdaCompiler"}, {"type": "image-age", "days": 0.2}
                ],
                "actions": ["deregister"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_ami_remove_launch_permissions(self):
        factory = self.replay_flight_data('test_ami_remove_perms')
        p = self.load_policy({
            'name': 'ami-check',
            'resource': 'aws.ami',
            'filters': ['cross-account'],
            'actions': [{
                'type': 'remove-launch-permissions'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            sorted(resources[0]['c7n:CrossAccountViolations']),
            ['112233445566', '665544332211',
            'arn:aws:organizations:112233445566:organization/o-xyz123abc',
            'arn:aws:organizations:112233445566:ou/o-xyz123abc/ou-a123-xyzab123'])

        client = factory().client('ec2')
        perms = client.describe_image_attribute(
            ImageId=resources[0]['ImageId'],
            Attribute='launchPermission')['LaunchPermissions']
        assert perms == []

    def test_ami_remove_launch_permissions_matched(self):
        factory = self.replay_flight_data('test_ami_remove_perms')
        p = self.load_policy({
            'name': 'ami-check',
            'resource': 'aws.ami',
            'filters': ['cross-account'],
            'actions': [{
                'type': 'remove-launch-permissions',
                'accounts': 'matched'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            sorted(resources[0]['c7n:CrossAccountViolations']),
            ['112233445566', '665544332211',
            'arn:aws:organizations:112233445566:organization/o-xyz123abc',
            'arn:aws:organizations:112233445566:ou/o-xyz123abc/ou-a123-xyzab123'])

        client = factory().client('ec2')
        perms = client.describe_image_attribute(
            ImageId=resources[0]['ImageId'],
            Attribute='launchPermission')['LaunchPermissions']
        assert perms == []

    def test_ami_set_permissions_remove_matched(self):
        factory = self.replay_flight_data('test_ami_set_perms')
        p = self.load_policy({
            'name': 'ami-check',
            'resource': 'aws.ami',
            'filters': ['cross-account'],
            'actions': [{
                'type': 'set-permissions',
                'remove': 'matched',
                'add': ['arn:aws:organizations:112233445566:ou/o-xyz123abc/ou-a123-xyzab234']}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            sorted(resources[0]['c7n:CrossAccountViolations']),
            ['112233445566', '665544332211',
                'all',
                'arn:aws:organizations:112233445566:organization/o-xyz123abc',
                'arn:aws:organizations:112233445566:ou/o-xyz123abc/ou-a123-xyzab123'])

        client = factory().client('ec2')
        perms = client.describe_image_attribute(
            ImageId=resources[0]['ImageId'],
            Attribute='launchPermission')['LaunchPermissions']
        assert perms == [{
            'OrganizationalUnitArn':
                'arn:aws:organizations:112233445566:ou/o-xyz123abc/ou-a123-xyzab234'}]

    def test_ami_set_permissions_remove_public(self):
        factory = self.replay_flight_data('test_ami_set_perms')
        p = self.load_policy({
            'name': 'ami-check',
            'resource': 'aws.ami',
            'filters': ['cross-account'],
            'actions': [{
                'type': 'set-permissions',
                'remove': ['all'],
                'add': ['arn:aws:organizations:112233445566:ou/o-xyz123abc/ou-a123-xyzab234']}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            sorted(resources[0]['c7n:CrossAccountViolations']),
            ['112233445566', '665544332211',
                'all',
                'arn:aws:organizations:112233445566:organization/o-xyz123abc',
                'arn:aws:organizations:112233445566:ou/o-xyz123abc/ou-a123-xyzab123'])

        client = factory().client('ec2')
        perms = client.describe_image_attribute(
            ImageId=resources[0]['ImageId'],
            Attribute='launchPermission')['LaunchPermissions']
        assert perms == [{
            'OrganizationalUnitArn':
                'arn:aws:organizations:112233445566:ou/o-xyz123abc/ou-a123-xyzab234'}]

    def test_ami_set_permissions_reset_all(self):
        factory = self.replay_flight_data('test_ami_remove_perms')
        p = self.load_policy({
            'name': 'ami-check',
            'resource': 'aws.ami',
            'filters': ['cross-account'],
            'actions': [{
                'type': 'set-permissions'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            sorted(resources[0]['c7n:CrossAccountViolations']),
            ['112233445566', '665544332211',
            'arn:aws:organizations:112233445566:organization/o-xyz123abc',
            'arn:aws:organizations:112233445566:ou/o-xyz123abc/ou-a123-xyzab123'])

        client = factory().client('ec2')
        perms = client.describe_image_attribute(
            ImageId=resources[0]['ImageId'],
            Attribute='launchPermission')['LaunchPermissions']
        assert perms == []

    def test_ami_set_deprecation_age(self):
        factory = self.replay_flight_data('test_ami_set_deprecation')
        p = self.load_policy({
            'name': 'ami-check',
            'resource': 'aws.ami',
            'filters': [{
                'type': 'value',
                'key': 'DeprecationTime',
                'value': 'absent'}],
            'actions': [{
                'type': 'set-deprecation',
                'age': 45}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)
        assert 'DeprecationTime' not in resources[0]

        client = factory().client('ec2')
        dtime = client.describe_images(
            ImageIds=[resources[0]['ImageId']])['Images'][0]['DeprecationTime']
        assert dtime == '2020-09-24T13:31:456.000Z'

    def test_ami_set_deprecation_date(self):
        factory = self.replay_flight_data('test_ami_set_deprecation')
        p = self.load_policy({
            'name': 'ami-check',
            'resource': 'aws.ami',
            'filters': [{
                'type': 'value',
                'key': 'DeprecationTime',
                'value': 'absent'}],
            'actions': [{
                'type': 'set-deprecation',
                'date': '2020-09-24T13:31'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)
        assert 'DeprecationTime' not in resources[0]

        client = factory().client('ec2')
        dtime = client.describe_images(
            ImageIds=[resources[0]['ImageId']])['Images'][0]['DeprecationTime']
        assert dtime == '2020-09-24T13:31:456.000Z'

    def test_ami_set_deprecation_disable(self):
        factory = self.replay_flight_data('test_ami_set_deprecation')
        p = self.load_policy({
            'name': 'ami-check',
            'resource': 'aws.ami',
            'filters': [{
                'type': 'value',
                'key': 'DeprecationTime',
                'value': 'absent'}],
            'actions': [{
                'type': 'set-deprecation'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)
        assert 'DeprecationTime' not in resources[0]

    def test_ami_set_deprecation_validation(self):
        with self.assertRaises(PolicyValidationError) as e:
            self.load_policy({
                'name': 'ami-check',
                'resource': 'aws.ami',
                'filters': [{
                    'type': 'value',
                    'key': 'DeprecationTime',
                    'value': 'absent'}],
                'actions': [{
                    'type': 'set-deprecation',
                    'date': "notright"}]})
        self.assertIn(
            "has invalid date format", str(e.exception))

        with self.assertRaises(PolicyValidationError) as e:
            self.load_policy({
                'name': 'ami-check',
                'resource': 'aws.ami',
                'filters': [{
                    'type': 'value',
                    'key': 'DeprecationTime',
                    'value': 'absent'}],
                'actions': [{
                    'type': 'set-deprecation',
                    'days': -327678902}]})
        self.assertIn(
            "has invalid time interval", str(e.exception))

    def test_ami_sse(self):
        factory = self.replay_flight_data('test_ami_sse')
        p = self.load_policy({
            'name': 'ubuntu-bionic',
            'resource': 'aws.ami',
            'query': [
                {'Owners': ["123456789123"]},
                {'Filters': [
                    {'Name': 'name',
                     'Values': ["ubuntu/images/hvm-ssd/ubuntu-bionic*"]}]}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(resources[0]['OwnerId'], '123456789123')

    def test_err_ami(self):
        factory = self.replay_flight_data("test_ami_not_found_err")
        ami_id = 'ami-123f000eee1f9f654'
        good_ami_id = 'ami-041151726c89bed87'
        error_response = {"Error": {
            "Message": "The image id '[%s]' does not exist" % (ami_id),
            "Code": "InvalidAMIID.NotFound"}}

        responses = [ClientError(error_response, "DescribeSnapshots")]

        def base_get_resources(self, ids, cache=True):
            if responses:
                raise responses.pop()
            return factory().client('ec2').describe_images(ImageIds=ids).get('Images')

        self.patch(DescribeSource, 'get_resources', base_get_resources)

        p = self.load_policy(
            {'name': 'bad-ami', 'resource': 'ami'},
            session_factory=factory)
        resources = p.resource_manager.get_resources([ami_id, good_ami_id])
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ImageId'], good_ami_id)

    def test_err_get_ami_invalid(self):
        operation_name = "DescribeSnapshots"
        error_response = {
            "Error": {
                "Message": 'Invalid id: "ami123f000eee1f9f654"',
                "Code": "InvalidAMIID.Malformed",
            }
        }
        e = ClientError(error_response, operation_name)
        ami = ErrorHandler.extract_bad_ami(e)
        self.assertEqual(ami, ["ami123f000eee1f9f654"])

        operation_name = "DescribeSnapshots"
        error_response = {
            "Error": {
                "Message": 'Invalid id: "ami-1234567890abcdef0"',
                "Code": "InvalidAMIID.Malformed",
            }
        }
        e = ClientError(error_response, operation_name)
        ami = ErrorHandler.extract_bad_ami(e)
        self.assertEqual(ami, ["ami-1234567890abcdef0"])

    def test_err_get_ami_notfound(self):
        operation_name = "DescribeSnapshots"
        error_response = {
            "Error": {
                "Message": "The image id '[ami-ffffffff]' does not exist",
                "Code": "InvalidAMIID.NotFound"
            }
        }
        e = ClientError(error_response, operation_name)
        snap = ErrorHandler.extract_bad_ami(e)
        self.assertEqual(snap, ["ami-ffffffff"])

        operation_name = "DescribeSnapshots"
        error_response = {
            "Error": {
                "Message": "The image id '[ami-11111111, ami-ffffffff]' does not exist",
                "Code": "InvalidAMIID.NotFound"
            }
        }
        e = ClientError(error_response, operation_name)
        snap = ErrorHandler.extract_bad_ami(e)
        self.assertEqual(snap, ["ami-11111111", "ami-ffffffff"])

    def test_deregister_delete_snaps(self):
        factory = self.replay_flight_data('test_ami_deregister_delete_snap')
        p = self.load_policy({
            'name': 'deregister-snap',
            'resource': 'ami',
            'actions': [{
                'type': 'deregister',
                'delete-snapshots': True}]},
            session_factory=factory, config={'account_id': '644160558196'})
        resources = p.run()
        self.assertEqual(len(resources), 2)
        client = factory().client('ec2')
        snap_ids = jmespath_search(
            'BlockDeviceMappings[].Ebs.SnapshotId', resources[0])
        self.assertRaises(
            ClientError, client.describe_snapshots, SnapshotIds=snap_ids, OwnerIds=['self'])

    def test_unused_ami_with_asg_launch_templates(self):
        factory = self.replay_flight_data('test_unused_ami_launch_template')
        p = self.load_policy(
            {"name": "test-unused-ami", "resource": "ami", "filters": ["unused"]},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['ImageId'], 'ami-0515ff4f8f9dbeb31')

    def test_ami_with_last_launched_time(self):
        factory = self.replay_flight_data('test_ami_with_last_launched_time')
        p = self.load_policy(
            {
                "name": "test-ami-last-launched-time",
                "resource": "ami",
                "filters": [{"type": "image-attribute",
                             "attribute": "lastLaunchedTime",
                             "key": "Value",
                             "op": "gte",
                             "value_type": "age",
                             "value": 1}],
            },
            {"region": "ap-southeast-2"},
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['c7n:attribute-lastLaunchedTime']
                         ['Value'], '2022-10-20T07:07:19Z')

    def test_ami_with_no_last_launched_time(self):
        factory = self.replay_flight_data('test_ami_with_no_last_launched_time')
        p = self.load_policy(
            {
                "name": "test-ami-last-launched-time",
                "resource": "ami",
                "filters": [{"type": "image-attribute",
                             "attribute": "lastLaunchedTime",
                             "key": "Value",
                             "op": "gte",
                             "value_type": "age",
                             "value": 1}],
            },
            {"region": "ap-southeast-2"},
            session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_cancel_launch_permissions_true(self):
        factory = self.replay_flight_data("test_cancel_launch_permissions")
        p = self.load_policy(
            {
                "name": "test-cancel-launch-permissions",
                "resource": "ami",
                "actions": [{"type": "cancel-launch-permission", }]},
                session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_cancel_launch_permissions_false(self):
        factory = self.replay_flight_data("test_cancel_launch_permissions")
        p = self.load_policy(
            {
                "name": "test-cancel-launch-permission",
                "resource": "ami",
                "actions": [{"type": "cancel-launch-permission", "dryrun": False}]},
                session_factory=factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_unused_ami_true(self):
        factory = self.replay_flight_data("test_unused_ami_true")
        p = self.load_policy(
            {"name": "test-unused-ami", "resource": "ami", "filters": ["unused"]},
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_unused_ami_false(self):
        factory = self.replay_flight_data("test_unused_ami_false")
        p = self.load_policy(
            {
                "name": "test-unused-ami",
                "resource": "ami",
                "filters": [{"type": "unused", "value": False}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_ami_cross_accounts(self):
        session_factory = self.replay_flight_data("test_ami_cross_accounts")
        p = self.load_policy(
            {
                "name": "cross-account-ami",
                "resource": "ami",
                "filters": [{"type": "cross-account"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_ami_image_ancestry(self):
        session_factory = self.replay_flight_data("test_ami_image_ancestry")
        p = self.load_policy(
            {
                "name": "ami-ancestry",
                "resource": "ami",
                "filters": [
                    {"type": "image-ancestry", "approved_owners": ["amazon"]}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertIn('c7n:image-ancestry', resources[0])

    def test_ami_image_ancestry_self_approved(self):
        session_factory = self.replay_flight_data('test_ec2_image_ancestry')
        p = self.load_policy(
            {
                'name': 'ami-self-approved',
                'resource': 'ami',
                'filters': [
                    {
                        'type': 'image-ancestry',
                        'approved_owners': ['amazon'],
                        'max_depth': 1
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertGreaterEqual(len(resources), 1)

    def test_ami_image_ancestry_parent_approved(self):
        session_factory = self.replay_flight_data('test_ec2_image_ancestry')
        p = self.load_policy(
            {
                'name': 'ami-parent-approved',
                'resource': 'ami',
                'filters': [
                    {
                        'type': 'image-ancestry',
                        'approved_owners': ['123456789012'],
                        'max_depth': 1
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_ami_image_ancestry_depth_traversal(self):
        session_factory = self.replay_flight_data('test_ec2_image_ancestry')
        p = self.load_policy(
            {
                'name': 'ami-grandparent-approved',
                'resource': 'ami',
                'filters': [
                    {
                        'type': 'image-ancestry',
                        'approved_owners': ['amazon'],
                        'max_depth': 2
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertGreaterEqual(len(resources), 1)

    def test_ami_image_ancestry_unapproved(self):
        session_factory = self.replay_flight_data('test_ec2_image_ancestry')
        p = self.load_policy(
            {
                'name': 'ami-unapproved-ancestry',
                'resource': 'ami',
                'filters': [
                    {
                        'type': 'image-ancestry',
                        'approved_owners': ['000000000000'],
                        'max_depth': 2
                    }
                ]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_ami_set_permissions_remove_matched_no_add(self):
        factory = self.replay_flight_data('test_ami_set_permissions_remove_matched_no_add')
        p = self.load_policy({
            'name': 'ami-check',
            'resource': 'aws.ami',
            'filters': [{'type': 'cross-account'},
            {'type': 'value',
            'key': 'Name',
            'value': 'test-ami'}],
            'actions': [{
                'type': 'set-permissions',
                'remove': 'matched'
            }]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['c7n:CrossAccountViolations'], ['898786471159'])
        client = factory().client('ec2')
        perms = client.describe_image_attribute(
            ImageId=resources[0]['ImageId'],
            Attribute='launchPermission')['LaunchPermissions']
        assert perms == []
