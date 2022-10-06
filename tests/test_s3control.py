# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time
from botocore.exceptions import ClientError
import pytest
from pytest_terraform import terraform


@terraform('s3_access_point', teardown=terraform.TEARDOWN_IGNORE)
def test_s3_access_point(test, s3_access_point):
    factory = test.replay_flight_data('s3_access_point_query')
    client = factory().client('s3control')
    sts_client = factory().client('sts')
    account_id = sts_client.get_caller_identity()['Account']
    p = test.load_policy(
        {
            'name': 'ap',
            'resource': 'aws.s3-access-point',
            'filters': ['cross-account'],
            'actions': ['delete'],
        },
        session_factory=factory,
        config={'account_id': account_id}
    )

    resources = p.run()
    assert len(resources) == 1
    assert resources[0]['Name'].startswith('c7n-ap-')

    if test.recording:
        time.sleep(2)

    with pytest.raises(ClientError):
        client.get_access_point(
            AccountId=p.options['account_id'], Name=resources[0]['Name']
        )
