# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import pytest
from c7n.config import Config
from c7n_tencentcloud.client import Session
from c7n_tencentcloud.provider import TencentCloud, DEFAULT_REGION
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException


@pytest.fixture
def tc_provider():
    return TencentCloud()


def test_get_session_factory(tc_provider, mock_env_aksk):
    session = tc_provider.get_session_factory(None)
    assert isinstance(session, Session)

    endpoint = "cvm.tencentcloudapi.com"
    service = "cvm"
    version = "2017-03-12"
    region = "ap-shanghai"
    cli = session.client(endpoint, service, version, region)

    with pytest.raises(TencentCloudSDKException):
        cli.execute_query("DescribeInstances", {})


test_cases = [
    ([], DEFAULT_REGION),
    (["ap-shanghai"], "ap-shanghai"),
    (["ap-shanghai", "others"], "ap-shanghai")
]


@pytest.fixture(params=test_cases)
def option_case(request):
    return request.param


def test_provider_initialize(tc_provider, option_case):
    config = Config.empty(**{
        "regions": option_case[0]
    })
    tc_provider.initialize(config)
    assert config.region == option_case[1]
