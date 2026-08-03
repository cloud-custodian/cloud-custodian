# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class S3FilesFileSystemTest(BaseTest):

    def test_s3files_file_system_query(self):
        session_factory = self.replay_flight_data('test_s3files_file_system_query')
        p = self.load_policy(
            {'name': 's3files-fs-query',
             'resource': 'aws.s3files-file-system'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        fs = resources[0]
        self.assertEqual(fs['Tags'], [{'Key': 'Env', 'Value': 'test'}])
        self.assertTrue(fs['bucket'])
        self.assertTrue(fs['fileSystemArn'].startswith('arn:aws:s3files:'))

    def test_s3files_cross_account(self):
        session_factory = self.replay_flight_data('test_s3files_cross_account')
        p = self.load_policy(
            {'name': 's3files-cross-account',
             'resource': 'aws.s3files-file-system',
             'filters': [{'type': 'cross-account'}]},
            session_factory=session_factory)
        resources = p.run()
        # wildcard principal statement in the file system policy
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]['c7n:Policy'])

    def test_s3files_has_statement(self):
        session_factory = self.replay_flight_data('test_s3files_has_statement')
        p = self.load_policy(
            {'name': 's3files-has-statement',
             'resource': 'aws.s3files-file-system',
             'filters': [
                 {'type': 'has-statement',
                  'statements': [
                      {'Effect': 'Allow',
                       'Action': 's3files:ClientMount'}]}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_s3files_no_policy(self):
        session_factory = self.replay_flight_data('test_s3files_no_policy')
        p = self.load_policy(
            {'name': 's3files-no-policy',
             'resource': 'aws.s3files-file-system',
             'filters': [{'type': 'cross-account'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_s3files_access_point_account(self):
        session_factory = self.replay_flight_data(
            'test_s3files_access_point_account')
        p = self.load_policy(
            {'name': 's3files-foreign-ap',
             'resource': 'aws.s3files-file-system',
             'filters': [{'type': 'access-point-account'}]},
            session_factory=session_factory)
        resources = p.run()
        # the policy has one same-account AccessPointArn condition and
        # one wildcard-account condition; only the latter is foreign
        self.assertEqual(len(resources), 1)
        foreign = resources[0]['c7n:ForeignAccessPoints']
        self.assertEqual(len(foreign), 1)
        self.assertIn(':*:', foreign[0])

    def test_s3files_file_system_tag(self):
        session_factory = self.replay_flight_data('test_s3files_file_system_tag')
        p = self.load_policy(
            {'name': 's3files-tag',
             'resource': 'aws.s3files-file-system',
             'filters': [{'tag:Owner': 'absent'}],
             'actions': [
                 {'type': 'tag', 'key': 'Owner', 'value': 'c7n-test'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('s3files')
        tags = client.list_tags_for_resource(
            resourceId=resources[0]['fileSystemId'])['tags']
        self.assertIn(
            {'key': 'Owner', 'value': 'c7n-test'}, tags)


class S3FilesMountTargetTest(BaseTest):

    def test_s3files_mount_target_query(self):
        session_factory = self.replay_flight_data('test_s3files_mount_target_query')
        p = self.load_policy(
            {'name': 's3files-mt-query',
             'resource': 'aws.s3files-mount-target'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        mt = resources[0]
        self.assertTrue(mt['subnetId'])
        self.assertTrue(mt['securityGroups'])

    def test_s3files_mount_target_subnet(self):
        session_factory = self.replay_flight_data('test_s3files_mount_target_subnet')
        p = self.load_policy(
            {'name': 's3files-mt-subnet',
             'resource': 'aws.s3files-mount-target',
             'filters': [
                 {'type': 'subnet',
                  'key': 'State',
                  'value': 'available'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_s3files_mount_target_security_group(self):
        session_factory = self.replay_flight_data(
            'test_s3files_mount_target_security_group')
        p = self.load_policy(
            {'name': 's3files-mt-sg',
             'resource': 'aws.s3files-mount-target',
             'filters': [
                 {'type': 'security-group',
                  'key': 'GroupName',
                  'value': 'default'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)


class S3FilesAccessPointTest(BaseTest):

    def test_s3files_access_point_query(self):
        session_factory = self.replay_flight_data('test_s3files_access_point_query')
        p = self.load_policy(
            {'name': 's3files-ap-query',
             'resource': 'aws.s3files-access-point'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        ap = resources[0]
        self.assertTrue(ap['accessPointArn'].startswith('arn:aws:s3files:'))
        self.assertIn('rootDirectory', ap)
        self.assertIn('c7n:parent-id', ap)
