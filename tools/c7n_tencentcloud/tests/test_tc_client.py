# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import os
import socket

from datetime import datetime
from unittest.mock import patch

import pytest

from c7n.utils import jmespath_search

from c7n_tencentcloud.utils import PageMethod
from c7n_tencentcloud.client import Session

from retrying import RetryError
from tencentcloud.common.abstract_client import AbstractClient
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException


class TestClient:
    @pytest.fixture
    def simple_client(self, session):
        return session.client("region.tencentcloudapi.com", "region", "2022-06-27", "ap-shanghai")

    @pytest.mark.vcr
    def test_query_simple(self, simple_client):
        # cli = session.client("region.tencentcloudapi.com", "region", "2022-06-27", "ap-shanghai")
        action = "DescribeProducts"
        jsonpath = "Response.Products[]"
        resp = simple_client.execute_query(action, {})
        data = jmespath_search(jsonpath, resp)
        # TODO assert some value
        assert data

    @pytest.fixture
    def gen_error_reponse(self):
        def _make_response(err_code):
            return {
                "Response": {
                    "Error": {
                        "Code": err_code
                    }
                }
            }
        return _make_response

    def test_retry_error(self, simple_client, gen_error_reponse, monkeypatch):
        call_counter = 0

        def mock_call_json(*args, **kwargs):
            nonlocal call_counter
            call_counter += 1
            if call_counter == 3:
                return gen_error_reponse("Invalid")
            return gen_error_reponse("RequestLimitExceeded")

        monkeypatch.setattr(AbstractClient, "call_json", mock_call_json)
        simple_client.execute_query("test", {})
        assert call_counter == 3

    def test_retry_exception(self, simple_client, monkeypatch):
        call_counter = 0

        def mock_call_json(*args, **kwargs):
            nonlocal call_counter
            call_counter += 1
            if call_counter == 3:
                raise TencentCloudSDKException()
            raise socket.error()
        monkeypatch.setattr(AbstractClient, "call_json", mock_call_json)
        with pytest.raises(TencentCloudSDKException):
            simple_client.execute_query("test", {})

        assert call_counter == 3

    def test_non_retry_exception(self, simple_client, monkeypatch):
        call_counter = 0

        def mock_call_json(*args, **kwargs):
            nonlocal call_counter
            call_counter += 1
            raise TencentCloudSDKException()

        monkeypatch.setattr(AbstractClient, "call_json", mock_call_json)
        with pytest.raises(TencentCloudSDKException):
            simple_client.execute_query("test", {})

        assert call_counter == 1

    def test_over_retry_times(self, simple_client, gen_error_reponse, monkeypatch):
        call_counter = 0
        call_timer = None
        call_at = [0]

        def mock_call_json(*args, **kwargs):
            nonlocal call_counter
            nonlocal call_timer
            nonlocal call_at
            if call_counter == 0:
                call_timer = datetime.now().timestamp()
            else:
                call_at.append(datetime.now().timestamp() - call_timer)
            call_counter += 1
            return gen_error_reponse("RequestLimitExceeded")

        monkeypatch.setattr(AbstractClient, "call_json", mock_call_json)
        with pytest.raises(RetryError):
            simple_client.execute_query("test", {})

        assert call_counter == 5

    @pytest.mark.vcr
    def test_paging_offset(self, client_cvm):
        jsonpath = "Response.InstanceSet[]"
        paging_def = {
            "method": PageMethod.Offset,
            "limit": {
                "key": "Limit",
                "value": 3
            }
        }
        params = {}
        res = client_cvm.execute_paged_query("DescribeInstances", params, jsonpath, paging_def)
        assert len(res) == 6

    @pytest.mark.vcr
    def test_paging_token(self, client_tag):
        jsonpath = "Response.Tags"
        paging_def = {
            "method": PageMethod.PaginationToken,
            "pagination_token_path": "Response.PaginationToken",
            "limit": {
                "key": "MaxResults",
                "value": 50
            }
        }
        params = {
            "TagKeys": ["tke-lb-serviceuuid"]
        }
        res = client_tag.execute_paged_query("GetTagValues", params, jsonpath, paging_def)
        assert len(res) == 233

    @patch.dict(
        os.environ,
        {
            "TENCENTCLOUD_TOKEN": "foo",
            "TENCENTCLOUD_SECRET_KEY": "bar",
            "TENCENTCLOUD_SECRET_ID": "baz",
        }, clear=True
    )
    def test_tc_client_token(self):
        session = Session()
        assert session._cred.token == 'foo'
        assert session._cred.secret_key == 'bar'
        assert session._cred.secret_id == 'baz'

    @patch.dict(
        os.environ,
        {
            "TENCENTCLOUD_TOKEN": "foo",
            "TENCENTCLOUD_SECRET_ID": "baz",
        }, clear=True
    )
    def test_tc_client_token_missing_key(self):
        found = False
        try:
            Session()
        except TencentCloudSDKException:
            found = True
        assert found
