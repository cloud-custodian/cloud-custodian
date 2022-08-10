# Copyright 2020 Cloud Custodian Authors
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time
from botocore.exceptions import ClientError
from .common import BaseTest


class TestQLDB(BaseTest):

    def test_qldb_describe(self):
        factory = self.replay_flight_data('test_qldb_describe')
        p = self.load_policy({
            'name': 'qldb', 'resource': 'aws.qldb'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertEqual({r['Name'] for r in resources}, {'devledger', 'devx'})
        self.assertEqual(resources[0]['Tags'], [{'Key': 'Env', 'Value': 'Dev'}])

    def test_qldb_force_delete(self):
        factory = self.replay_flight_data('test_qldb_force_delete')
        p = self.load_policy({
            'name': 'qldb',
            'resource': 'aws.qldb',
            'actions': [{'type': 'delete', 'force': True}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'devledger')
        if self.recording:
            time.sleep(10)
        client = factory().client('qldb')
        self.assertRaises(
            ClientError, client.describe_ledger, Name='devledger')

    def test_qldb_delete(self):
        factory = self.replay_flight_data('test_qldb_delete')
        output = self.capture_logging('custodian.actions')
        p = self.load_policy({
            'name': 'qldb', 'resource': 'aws.qldb', 'actions': ['delete']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)
        self.assertIn('qldb delete found 1 delete-protected', output.getvalue())
        if self.recording:
            time.sleep(10)
        client = factory().client('qldb')
        self.assertRaises(
            ClientError, client.describe_ledger, Name='devx')
