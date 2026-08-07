# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class S3TableBucketTest(BaseTest):

    def test_s3_table_bucket_query(self):
        session_factory = self.replay_flight_data('test_s3_table_bucket_query')
        p = self.load_policy(
            {'name': 's3-table-bucket-query',
             'resource': 'aws.s3-table-bucket'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 3)
        tagged = {r['name']: r['Tags'] for r in resources}
        self.assertEqual(
            tagged['c7n-test-tb-compliant'],
            [{'Key': 'Env', 'Value': 'test'}])

    def test_s3_table_bucket_cross_account_org(self):
        session_factory = self.replay_flight_data(
            'test_s3_table_bucket_cross_account_org')
        p = self.load_policy(
            {'name': 's3-table-bucket-cross-account',
             'resource': 'aws.s3-table-bucket',
             'filters': [
                 {'type': 'cross-account',
                  'whitelist_orgids': ['o-c7ntest4321']}]},
            session_factory=session_factory)
        resources = p.run()
        # the whitelisted-org bucket passes, the no-policy bucket is
        # skipped, only the foreign-org bucket is flagged
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'c7n-test-tb-open')
        self.assertTrue(resources[0]['c7n:Policy'])

    def test_s3_table_bucket_has_statement(self):
        session_factory = self.replay_flight_data(
            'test_s3_table_bucket_has_statement')
        p = self.load_policy(
            {'name': 's3-table-bucket-has-statement',
             'resource': 'aws.s3-table-bucket',
             'filters': [
                 {'type': 'has-statement',
                  'statements': [
                      {'Effect': 'Allow',
                       'Condition': {
                           'StringEquals': {
                               'aws:PrincipalOrgID': 'o-c7ntest4321'}}}]}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'c7n-test-tb-compliant')

    def test_s3_table_bucket_add_tag(self):
        session_factory = self.replay_flight_data('test_s3_table_bucket_add_tag')
        p = self.load_policy(
            {'name': 's3-table-bucket-tag',
             'resource': 'aws.s3-table-bucket',
             'filters': [{'tag:Env': 'absent'}],
             'actions': [
                 {'type': 'tag', 'key': 'Env', 'value': 'test'}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)
        client = session_factory().client('s3tables')
        tags = client.list_tags_for_resource(
            resourceArn=resources[0]['arn'])['tags']
        self.assertEqual(tags.get('Env'), 'test')

    def test_s3_table_bucket_remove_tag(self):
        session_factory = self.replay_flight_data(
            'test_s3_table_bucket_remove_tag')
        p = self.load_policy(
            {'name': 's3-table-bucket-remove-tag',
             'resource': 'aws.s3-table-bucket',
             'filters': [{'tag:Env': 'present'}],
             'actions': [{'type': 'remove-tag', 'tags': ['Env']}]},
            session_factory=session_factory)
        resources = p.run()
        self.assertTrue(resources)
        client = session_factory().client('s3tables')
        tags = client.list_tags_for_resource(
            resourceArn=resources[0]['arn'])['tags']
        self.assertNotIn('Env', tags)


class S3TableTest(BaseTest):

    def test_s3_table_query(self):
        session_factory = self.replay_flight_data('test_s3_table_query')
        p = self.load_policy(
            {'name': 's3-table-query',
             'resource': 'aws.s3-table'},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)
        for r in resources:
            self.assertTrue(r['c7n:parent-id'].startswith('arn:aws:s3tables:'))

    def test_s3_table_cross_account(self):
        session_factory = self.replay_flight_data('test_s3_table_cross_account')
        p = self.load_policy(
            {'name': 's3-table-cross-account',
             'resource': 'aws.s3-table',
             'filters': [{'type': 'cross-account'}]},
            session_factory=session_factory)
        resources = p.run()
        # only the foreign-org table policy is flagged; the
        # policy-less table is skipped
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['name'], 'c7n_table_open')
