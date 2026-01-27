# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class TestFIS(BaseTest):
    def test_fis_delete(self):
        session_factory = self.replay_flight_data('test_fis_delete', region="us-east-2")
        p = self.load_policy(
            {
                "name": "fis-name-filter",
                "resource": "aws.fis-template",
                "filters": [{"id": "EXT3dBw7DdJZ2v8p"}],
                "actions": ["delete"],
            },
            config={'region': 'us-east-2', 'account_id': '619193117841'},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('fis')
        experiments = client.list_experiment_templates().get('experimentTemplates')
        assert experiments == []

    def test_fis_tag(self):
        session_factory = self.replay_flight_data('test_fis_tag', region="us-east-2")
        p = self.load_policy(
            {
                "name": "fis-name-filter",
                "resource": "aws.fis-template",
                "filters": [{'tag:Name': 'Charybdis'}],
                "actions": [
                    {"type": "tag", "key": "Location", "value": "Messina"},
                    {"type": "remove-tag", "tags": ["Name"]},
                ],
            },
            config={'region': 'us-east-2'},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('fis')
        experiment = client.get_experiment_template(id=resources[0]['id']).get(
            'experimentTemplate'
        )
        assert experiment['tags'] == {'Location': 'Messina'}

    def test_fis_mark_match(self):
        session_factory = self.replay_flight_data(
            "test_fis_mark_match"
        )
        p = self.load_policy(
            {
                "name": "test_fis_mark_for_op",
                "resource": "aws.fis-template",
                "filters": [{'tag:Name': 'Shiney'}],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "days": 4,
                        "op": "delete",
                        "tag": "custodian_cleanup",
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        policy = self.load_policy(
            {
                "name": "test_fis_marked_for_op",
                "resource": "aws.fis-template",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "tag": "custodian_cleanup",
                        "op": "delete",
                        "skew": 4,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Tags'][0],
                        {'Key': 'custodian_cleanup',
                         'Value': 'Resource does not meet policy: delete@2022/08/29'})

    def test_fis_experiment(self):
        session_factory = self.replay_flight_data("test_fis_experiment")
        p = self.load_policy(
            {
                "name": "test_fis_experiment",
                "resource": "aws.fis-experiment",
                "filters": [{'tag:foo': 'bar'}],
                "actions": [
                    {
                        "type": "remove-tag",
                        "tags": ["foo"],
                    },
                    {
                        "type": "tag",
                        "key": "is_test",
                        "value": "true"
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        print(resources)
        self.assertEqual(len(resources), 1)
        client = session_factory().client('fis')
        experiments = client.list_experiments().get('experiments')
        self.assertEqual(experiments[0]['tags'], {'is_test': 'true'})
