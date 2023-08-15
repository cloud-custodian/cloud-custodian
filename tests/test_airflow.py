# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest
from c7n.utils import jmespath_search

class TestApacheAirflow(BaseTest):
    def test_airflow_environment_value_filter(self):
        session_factory = self.replay_flight_data('test_airflow_environment_value_filter')
        p = self.load_policy(
            {
                "name": "airflow-name-filter",
                "resource": "airflow",
                "filters": [
                    {
                        "type": "value",
                        "key": "Name",
                        "op": "eq",
                        "value": "testEnvironment",
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'testEnvironment')
        self.assertEqual(resources[0]['c7n:MatchedFilters'], ['Name'])

    def test_airflow_environment_kms_filter(self):
        session_factory = self.replay_flight_data('test_airflow_environment_kms_filter')
        kms = session_factory().client('kms')
        expression = 'KmsKey'
        p = self.load_policy(
            {
                "name": "airflow-kms-filter",
                "resource": "airflow",
                "filters": [
                    {
                        "type": "kms-key",
                        "key": "c7n:AliasName",
                        "value": "alias/mwaa",
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        aliases = kms.list_aliases(KeyId=(jmespath_search(expression, resources[0])))
        self.assertEqual(aliases['Aliases'][0]['AliasName'], 'alias/mwaa')

    def test_airflow_environment_tag(self):
        session_factory = self.replay_flight_data('test_airflow_environment_tag')
        new_tag = {'env': 'dev'}
        p = self.load_policy(
            {
                'name': 'airflow-tag',
                'resource': 'airflow',
                'filters': [{
                    'tag:env': 'absent'
                }],
                'actions': [{
                    'type': 'tag',
                    'tags': new_tag
                }]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(1, len(resources))
        name = resources[0].get('Name')
        airflow = session_factory().client('mwaa')
        call = airflow.get_environment(Name=name)
        self.assertEqual(new_tag, call['Environment'].get('Tags'))

    def test_airflow_environment_untag(self):
        session_factory = self.replay_flight_data('test_airflow_environment_untag')
        p = self.load_policy(
            {
                'name': 'airflow-untag',
                'resource': 'airflow',
                'filters': [{
                    'tag:env': 'dev'
                }],
                'actions': [{
                    'type': 'remove-tag',
                    'tags': ['env']
                }]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(1, len(resources))
        name = resources[0].get('Name')
        airflow = session_factory().client('mwaa')
        call = airflow.get_environment(Name=name)
        self.assertEqual({}, call['Environment'].get('Tags'))
