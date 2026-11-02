# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from collections import Counter

import c7n.policy

from c7n.exceptions import PolicyValidationError

from ..azure_common import BaseTest, arm_template


class CognitiveServiceLocationUsageTest(BaseTest):

    def load_usage_policy(self, **data: object) -> c7n.policy.Policy:
        with self.sign_out_patch():
            return self.load_policy(
                {
                    'name': 'test-cognitiveservice-location-usage',
                    'resource': 'azure.cognitiveservice-location-usage',
                    **data,
                },
                validate=True,
            )

    def test_arm_actions_are_not_available(self) -> None:
        self.load_usage_policy()
        for action in ('delete', 'tag', 'lock'):
            with self.subTest(action=action), self.assertRaises(PolicyValidationError):
                self.load_usage_policy(actions=[{'type': action}])

    @arm_template('cognitive-service-location-usage.json')
    def test_location_usage_rows(self) -> None:
        policy = self.load_policy(
            {
                'name': 'cognitiveservice-location-usage',
                'resource': 'azure.cognitiveservice-location-usage',
            },
        )
        rows = policy.run()

        self.assertEqual(len({row['id'] for row in rows}), len(rows))
        names = Counter(
            (row.get('scopeType'), row['name']['value']) for row in rows
        )
        # Shared quota is listed once, regional quota once per location.
        self.assertEqual(names[('Global', 'OpenAI.GlobalStandard.gpt-5.4-nano')], 1)
        self.assertEqual(names[('DataZone', 'OpenAI.DataZoneProvisionedManaged')], 1)
        self.assertEqual(names[('Classic', 'OpenAI.ProvisionedManaged')], 2)
        self.assertEqual(names[(None, 'AccountCount')], 2)
        self.assertEqual(
            {row['c7n:location'] for row in rows if row['name']['value'] == 'AccountCount'},
            {'eastus', 'eastus2'},
        )

        global_row = next(
            row for row in rows
            if row['name']['value'] == 'OpenAI.GlobalStandard.gpt-5.4-nano'
        )
        self.assertEqual(global_row['scopeId'], 'global')
        self.assertEqual(global_row['c7n:location'], 'eastus')
        self.assertEqual(global_row['currentValue'], 1)
        self.assertGreater(global_row['limit'], 0)
