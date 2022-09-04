# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import pytest
from c7n.config import Config
from c7n.ctx import ExecutionContext
from c7n_tencentcloud.client import Session


@pytest.fixture
def mock_env_aksk(monkeypatch):
    monkeypatch.setenv("TENCENTCLOUD_SECRET_ID", "xxx")
    monkeypatch.setenv("TENCENTCLOUD_SECRET_KEY", "yyy")


@pytest.fixture
def session(mock_env_aksk):
    return Session()


@pytest.fixture
def options():
    return Config.empty(**{
        "region": "ap-singapore"  # just for init, ignore the value
    })


@pytest.fixture
def ctx(session, options):
    return ExecutionContext(session, {}, options)
