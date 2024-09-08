# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from pytest_terraform import terraform
import pytest

aws_region = 'us-east-1'

test_data = [
    ('app-elb', ['aws_lb.nlb_unallowed.arn', 'aws_lb.alb_unallowed.arn']),
    # ...
]

@pytest.mark.parametrize('elb_type, expected', test_data)
@terraform('elb_ingress')
def test_elbv2_ingress(test, elb_ingress, elb_type, expected):
    session_factory = test.replay_flight_data(
        'elb_ingress',
        region=aws_region,
    )

    p = test.load_policy(
        {
            'name': 'foo',
            'resource': elb_type,
            'filters': [
                {
                    'type': 'ingress',
                    'Cidr': '0.0.0.0/0',
                }
            ],
        },
        session_factory=session_factory,
        config={
            'region': aws_region
        },
    )

    resources = p.run()

    arns = [i['LoadBalancerArn'] for i in resources]

    _expected_arns = [elb_ingress[e] for e in expected]

    assert len(resources) == len(_expected_arns)
    assert _expected_arns == arns
