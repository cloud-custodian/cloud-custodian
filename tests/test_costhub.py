# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


def test_cost_hub_ebs(test):
    factory = test.replay_flight_data('cost_opt_hub_ebs')
    p = test.load_policy(
        {
            'name': 'cost-opt-ec2',
            'resource': 'aws.ebs',
            'filters': [
                {
                    'type': 'cost-optimization',
                    'efforts': ['VeryLow', 'Low', 'Medium'],
                    'attrs': [
                        {
                            'type': 'value',
                            'key': 'estimatedSavingsPercentage',
                            'value': 15,
                            'op': 'gte',
                        },
                    ],
                }
            ],
        },
        session_factory=factory,
        config={'account_id': '644160558196'}
    )

    resources = p.run()
    assert len(resources) == 1
    assert resources[0]['c7n:cost_optimize']
