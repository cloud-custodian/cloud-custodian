# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from pytest_terraform import terraform
import pytest

aws_region = 'us-east-1'

test_data = [
    (True,  ['aws_lb.alb_waf_v2_ip_whitelisting_allowed_addresses_only.arn']),
    (False, [
        'aws_lb.alb_waf_v2_ip_whitelisting_unallowed_addresses.arn',
        'aws_lb.alb_waf_v2_assoc_missing.arn',
    ]),
]

@pytest.mark.parametrize('enabled, expected', test_data)
@terraform('wafv2_ip_whitelist')
def test_wafv2_ip_whitelist(test, wafv2_ip_whitelist, enabled, expected):
    session_factory = test.replay_flight_data(
        'wafv2_ip_whitelist',
        region=aws_region,
    )

    p = test.load_policy(
        {
            'name': 'foo',
            'resource': 'app-elb',
            'filters': [
                {
                    'type': 'wafv2-ip-whitelisting',
                    'enabled': enabled,
                    'whitelist': ['192.168.0.0/24'],
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

    _expected_arns = [wafv2_ip_whitelist[e] for e in expected]

    assert len(resources) == len(_expected_arns)
    assert _expected_arns == arns
