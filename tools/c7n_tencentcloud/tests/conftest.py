# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import pytest
import json
import os

from c7n.config import Config
from c7n.ctx import ExecutionContext
from c7n_tencentcloud.client import Session


@pytest.fixture(autouse=True)
def credential_env_vars(monkeypatch):
    monkeypatch.setenv("TENCENTCLOUD_SECRET_ID",
                       os.environ.get('TENCENTCLOUD_SECRET_ID', "xyz"))
    monkeypatch.setenv("TENCENTCLOUD_SECRET_KEY",
                       os.environ.get('TENCENTCLOUD_SECRET_KEY', "abc123"))
    monkeypatch.setenv("TENCENTCLOUD_REGION",
                       os.environ.get('TENCENTCLOUD_REGION', "na-ashburn"))


@pytest.fixture(scope="package")
def vcr_config():
    return {
        "filter_headers": ["authorization", "X-TC-Timestamp", "X-TC-RequestClient",
                           "X-TC-Language"],
        "filter_query_parameters": ["max-keys"],
        "before_record_response": scrub_string(["IntranetUrl", "InternetUrl", "Url"]),
    }


def scrub_string(keys, replacement=''):
    def before_record_response(response):
        response_value = response['body']['string']
        try:
            res = json.loads(response_value)
            if "Response" in res and "Items" in res["Response"]:
                for i in res["Response"]["Items"]:
                    for key in keys:
                        if key in i:
                            i[key] = replacement
                response['body']['string'] = str.encode(json.dumps(res))
            return response
        except ValueError:
            return response

    return before_record_response


@pytest.fixture
def session():
    return Session()


@pytest.fixture
def client_cvm(session):
    return session.client("cvm.tencentcloudapi.com", "cvm", "2017-03-12", "ap-singapore")


@pytest.fixture
def client_tag(session):
    return session.client("tag.tencentcloudapi.com", "tag", "2018-08-13", "ap-singapore")


@pytest.fixture
def options():
    return Config.empty(**{
        "region": "ap-singapore",  # just for init, ignore the value
        "account_id": "100000750436",
        "output_dir": "null://",
        "log_group": "null://",
        "cache": False,
    })


@pytest.fixture
def ctx(session, options):
    return ExecutionContext(lambda: session, {}, options)
