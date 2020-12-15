# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time
from botocore.exceptions import ClientError
import pytest
from pytest_terraform import terraform


@terraform('s3_access_point', teardown=terraform.TEARDOWN_IGNORE)
def test_s3_access_point(test, s3_access_point):
    factory = test.record_flight_data('s3_access_point_query')
    client = factory().client('s3control')
    p = test.load_policy({
        'name': 'ap',
        'resource': 'aws.s3-access-point',
        'filters': ['cross-account'],
        'actions': ['delete']},
        session_factory=factory)

    resources = p.run()
    assert len(resources) == 1
    assert resources[0]['Name'].startswith('example-')

    if test.recording:
        time.sleep(2)

    with pytest.raises(ClientError) as ecm:
        client.get_access_point(
            AccountId=p.options['account_id'],
            Name=resources[0]['Name'])
