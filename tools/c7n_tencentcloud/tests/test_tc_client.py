# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import os
import socket

from datetime import datetime
from unittest.mock import patch

import pytest

from c7n.utils import jmespath_search
from c7n.exceptions import PolicyExecutionError

from c7n_tencentcloud.utils import PageMethod
from c7n_tencentcloud.client import Session, retry_exception, retry_result

from retrying import RetryError
from requests.exceptions import ConnectionError
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

    def test_retry_exception_function(self):
        """Test retry_exception helper function"""
        assert retry_exception(socket.error())
        assert retry_exception(ConnectionError())
        assert not retry_exception(ValueError())
        assert not retry_exception(Exception())

    def test_retry_result_function(self):
        """Test retry_result helper function"""
        # Test with RequestLimitExceeded error
        resp_limit = {
            "Response": {
                "Error": {
                    "Code": "RequestLimitExceeded"
                }
            }
        }
        assert retry_result(resp_limit)

        # Test with RequestLimitExceeded in error code
        resp_limit_partial = {
            "Response": {
                "Error": {
                    "Code": "SomeRequestLimitExceededError"
                }
            }
        }
        assert retry_result(resp_limit_partial)

        # Test without error
        resp_ok = {
            "Response": {
                "Data": "ok"
            }
        }
        assert not retry_result(resp_ok)

        # Test with different error
        resp_other = {
            "Response": {
                "Error": {
                    "Code": "InvalidParameter"
                }
            }
        }
        assert not retry_result(resp_other)

    def test_session_properties(self):
        """Test Session property accessors"""
        session = Session()
        # Access properties to ensure they're covered
        assert session.secret_id is not None
        assert session.secret_key is not None
        # token should be None when no TOKEN env var is set
        token = session.token
        assert token is None or isinstance(token, str)

    def test_paging_page_method(self, simple_client, monkeypatch):
        """Test Page-based pagination"""
        call_count = 0

        def mock_execute_query(action, params):
            nonlocal call_count
            call_count += 1
            page = params.get("Page", 1)
            if page == 1:
                return {"Response": {"Items": ["item1", "item2"]}}
            elif page == 2:
                return {"Response": {"Items": ["item3"]}}
            else:
                return {"Response": {"Items": []}}

        monkeypatch.setattr(simple_client, "execute_query", mock_execute_query)

        paging_def = {
            "method": PageMethod.Page,
            "limit": {"key": "Limit", "value": 2}
        }
        results = simple_client.execute_paged_query(
            "TestAction", {}, "Response.Items", paging_def
        )
        assert len(results) == 3
        assert results == ["item1", "item2", "item3"]

    def test_paging_pagination_token_no_path(self, simple_client):
        """Test PaginationToken method without token path raises error"""
        paging_def = {
            "method": PageMethod.PaginationToken,
            "limit": {"key": "MaxResults", "value": 50}
        }
        with pytest.raises(PolicyExecutionError, match="pagination_token but not set token path"):
            simple_client.execute_paged_query("TestAction", {}, "Response.Items", paging_def)

    def test_paging_unsupported_method(self, simple_client):
        """Test unsupported paging method raises error"""
        class UnsupportedMethod:
            name = "Unsupported"

        paging_def = {
            "method": UnsupportedMethod(),
            "limit": {"key": "Limit", "value": 10}
        }
        with pytest.raises(PolicyExecutionError, match="unsupported paging method"):
            simple_client.execute_paged_query("TestAction", {}, "Response.Items", paging_def)

    def test_paging_too_many_requests(self, simple_client, monkeypatch):
        """Test that too many requests raises error"""
        def mock_execute_query(action, params):
            return {"Response": {"Items": ["item"] * 20}}

        monkeypatch.setattr(simple_client, "execute_query", mock_execute_query)
        # Set a low MAX_REQUEST_TIMES for testing
        original_max = simple_client.MAX_REQUEST_TIMES
        simple_client.MAX_REQUEST_TIMES = 5

        paging_def = {
            "method": PageMethod.Offset,
            "limit": {"key": "Limit", "value": 10}
        }

        with pytest.raises(PolicyExecutionError, match="too many resources"):
            simple_client.execute_paged_query("TestAction", {}, "Response.Items", paging_def)

        simple_client.MAX_REQUEST_TIMES = original_max

    def test_paging_too_many_data(self, simple_client, monkeypatch):
        """Test that too much data raises error"""
        def mock_execute_query(action, params):
            return {"Response": {"Items": ["item"] * 1000}}

        monkeypatch.setattr(simple_client, "execute_query", mock_execute_query)
        # Set a low MAX_RESPONSE_DATA_COUNT for testing
        original_max = simple_client.MAX_RESPONSE_DATA_COUNT
        simple_client.MAX_RESPONSE_DATA_COUNT = 2000

        paging_def = {
            "method": PageMethod.Offset,
            "limit": {"key": "Limit", "value": 1000}
        }

        with pytest.raises(PolicyExecutionError, match="too many resources"):
            simple_client.execute_paged_query("TestAction", {}, "Response.Items", paging_def)

        simple_client.MAX_RESPONSE_DATA_COUNT = original_max

    def test_paging_offset_string_limit(self, simple_client, monkeypatch):
        """Test Offset pagination with string limit value"""
        call_count = 0

        def mock_execute_query(action, params):
            nonlocal call_count
            call_count += 1
            # Verify Offset is converted to string
            if call_count > 1:
                assert isinstance(params["Offset"], str)
            offset = int(params.get("Offset", 0))
            if offset == 0:
                return {"Response": {"Items": ["item1", "item2"]}}
            elif offset == 2:
                return {"Response": {"Items": ["item3", "item4"]}}
            else:
                return {"Response": {"Items": ["item5"]}}

        monkeypatch.setattr(simple_client, "execute_query", mock_execute_query)

        paging_def = {
            "method": PageMethod.Offset,
            "limit": {"key": "Limit", "value": "2"}  # String value
        }
        results = simple_client.execute_paged_query(
            "TestAction", {}, "Response.Items", paging_def
        )
        assert len(results) == 5
        assert call_count == 3

    def test_paging_offset_continuation(self, simple_client, monkeypatch):
        """Test Offset pagination with multiple pages"""
        pages = [
            ["item1", "item2", "item3"],
            ["item4", "item5", "item6"],
            ["item7", "item8"]
        ]
        call_count = 0

        def mock_execute_query(action, params):
            nonlocal call_count
            offset = params.get("Offset", 0)
            page_idx = offset // 3
            call_count += 1
            if page_idx < len(pages):
                return {"Response": {"Items": pages[page_idx]}}
            return {"Response": {"Items": []}}

        monkeypatch.setattr(simple_client, "execute_query", mock_execute_query)

        paging_def = {
            "method": PageMethod.Offset,
            "limit": {"key": "Limit", "value": 3}
        }
        results = simple_client.execute_paged_query(
            "TestAction", {}, "Response.Items", paging_def
        )
        assert len(results) == 8
        assert call_count == 3

    def test_paging_empty_first_page(self, simple_client, monkeypatch):
        """Test pagination with empty first page"""
        def mock_execute_query(action, params):
            return {"Response": {"Items": []}}

        monkeypatch.setattr(simple_client, "execute_query", mock_execute_query)

        paging_def = {
            "method": PageMethod.Offset,
            "limit": {"key": "Limit", "value": 10}
        }
        results = simple_client.execute_paged_query(
            "TestAction", {}, "Response.Items", paging_def
        )
        assert len(results) == 0

    def test_paging_pagination_token_continuation(self, simple_client, monkeypatch):
        """Test PaginationToken-based pagination with continuation"""
        call_count = 0

        def mock_execute_query(action, params):
            nonlocal call_count
            call_count += 1
            token = params.get("PaginationToken", "")
            if token == "":
                return {
                    "Response": {
                        "Items": ["item1", "item2"],
                        "PaginationToken": "token123"
                    }
                }
            elif token == "token123":
                return {
                    "Response": {
                        "Items": ["item3", "item4"],
                        "PaginationToken": ""  # Empty token means no more data
                    }
                }
            else:
                return {"Response": {"Items": [], "PaginationToken": ""}}

        monkeypatch.setattr(simple_client, "execute_query", mock_execute_query)

        paging_def = {
            "method": PageMethod.PaginationToken,
            "pagination_token_path": "Response.PaginationToken",
            "limit": {"key": "MaxResults", "value": 2}
        }
        results = simple_client.execute_paged_query(
            "TestAction", {}, "Response.Items", paging_def
        )
        assert len(results) == 4
        assert call_count == 2

    def test_session_profile_name_success(self, tmp_path, monkeypatch):
        """Test Session with valid profile_name"""
        # Create a temporary credentials file
        credentials_dir = tmp_path / ".tencentcloud"
        credentials_dir.mkdir()
        credentials_file = credentials_dir / "credentials"
        credentials_file.write_text("""[test_profile]
secret_id = test_secret_id_123
secret_key = test_secret_key_456
""")

        # Mock expanduser to return our temp directory
        monkeypatch.setattr(os.path, "expanduser", lambda x: str(credentials_file))

        session = Session(profile_name="test_profile")
        assert session._cred.secret_id == "test_secret_id_123"
        assert session._cred.secret_key == "test_secret_key_456"

    def test_session_profile_name_not_found(self, tmp_path, monkeypatch):
        """Test Session with non-existent profile_name"""
        credentials_dir = tmp_path / ".tencentcloud"
        credentials_dir.mkdir()
        credentials_file = credentials_dir / "credentials"
        credentials_file.write_text("""[other_profile]
secret_id = test_id
secret_key = test_key
""")

        monkeypatch.setattr(os.path, "expanduser", lambda x: str(credentials_file))

        with pytest.raises(TencentCloudSDKException, match="Profile 'missing_profile' not found"):
            Session(profile_name="missing_profile")

    def test_session_profile_missing_credentials(self, tmp_path, monkeypatch):
        """Test Session with profile missing secret_id or secret_key"""
        credentials_dir = tmp_path / ".tencentcloud"
        credentials_dir.mkdir()
        credentials_file = credentials_dir / "credentials"
        credentials_file.write_text("""[incomplete_profile]
secret_id = test_id
""")

        monkeypatch.setattr(os.path, "expanduser", lambda x: str(credentials_file))

        with pytest.raises(TencentCloudSDKException, match="missing secret_id or secret_key"):
            Session(profile_name="incomplete_profile")

    def test_session_profile_file_not_found(self, tmp_path, monkeypatch):
        """Test Session with non-existent credentials file"""
        credentials_file = tmp_path / ".tencentcloud" / "credentials"

        monkeypatch.setattr(os.path, "expanduser", lambda x: str(credentials_file))

        with pytest.raises(TencentCloudSDKException, match="Credentials file not found"):
            Session(profile_name="any_profile")

    def test_session_profile_parse_error(self, tmp_path, monkeypatch):
        """Test Session with invalid credentials file format"""
        credentials_dir = tmp_path / ".tencentcloud"
        credentials_dir.mkdir()
        credentials_file = credentials_dir / "credentials"
        # Write invalid content
        credentials_file.write_text("this is not valid ini format {[}")

        monkeypatch.setattr(os.path, "expanduser", lambda x: str(credentials_file))

        with pytest.raises(TencentCloudSDKException, match="Failed to load profile"):
            Session(profile_name="test_profile")
