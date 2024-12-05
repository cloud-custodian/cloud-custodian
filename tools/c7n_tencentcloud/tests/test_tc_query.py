# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import pytest
from c7n_tencentcloud.query import ResourceTypeInfo, ResourceQuery, QueryResourceManager
from c7n_tencentcloud.utils import PageMethod


class RegionInfo(ResourceTypeInfo):
    """RegionInfo"""
    id = "InstanceId"
    endpoint = "cvm.tencentcloudapi.com"
    service = "cvm"
    version = "2017-03-12"
    enum_spec = ("DescribeRegions", "Response.RegionSet[]", {})
    metrics_instance_id_name = "InstanceId"
    resource_prefix = "instance"
    taggable = True


class CVMInfo(ResourceTypeInfo):
    """CVMInfo"""
    id = "InstanceId"
    endpoint = "cvm.tencentcloudapi.com"
    service = "cvm"
    version = "2017-03-12"
    enum_spec = ("DescribeInstances", "Response.InstanceSet[]", {})
    metrics_instance_id_name = "InstanceId"
    paging_def = {"method": PageMethod.Offset, "limit": {"key": "Limit", "value": 20}}
    resource_prefix = "instance"
    taggable = True


class CVMInfoNoPagination(ResourceTypeInfo):
    """CVMInfoNoPagination"""
    id = "InstanceId"
    endpoint = "cvm.tencentcloudapi.com"
    service = "cvm"
    version = "2017-03-12"
    enum_spec = ("DescribeInstances", "Response.InstanceSet[]", {})
    metrics_instance_id_name = "InstanceId"
    resource_prefix = "instance"
    taggable = True


def test_meta_str():
    assert str(RegionInfo) == "<Type info service:cvm client:2017-03-12>"
    assert str(CVMInfo) == "<Type info service:cvm client:2017-03-12>"


class TestResourcetQuery:
    @pytest.mark.vcr
    def test_filter(self, session):
        resource_query = ResourceQuery(session)
        res = resource_query.filter("ap-singapore", RegionInfo, {})
        assert len(res) == 20

    @pytest.mark.vcr
    def test_paged_filter(self, session):
        resource_query = ResourceQuery(session)
        res = resource_query.paged_filter("ap-singapore", CVMInfo, {})
        assert len(res) == 6


# (data, expected_query_params)
data_test_cases = [
    ({}, {}),
    ({"query": [{"Filters": [{"Key": "Value"}]}]}, {"Filters": [{"Key": "Value"}]})
]


@pytest.fixture(params=data_test_cases)
def data_test_case(request):
    return request.param


class TestQueryResourceManager:
    def test_get_permissions(self, ctx):
        resource_manager = QueryResourceManager(ctx, {})
        assert resource_manager.get_permissions() == []

    def test_get_resource_query_params(self, ctx, data_test_case):
        resource_manager = QueryResourceManager(ctx, data_test_case[0])
        res = resource_manager.get_resource_query_params()
        assert res == data_test_case[1]

    @pytest.mark.vcr
    def test_resources(self, ctx, monkeypatch):
        monkeypatch.setattr(QueryResourceManager, "resource_type", CVMInfo)
        resource_manager = QueryResourceManager(ctx, {})
        res = resource_manager.resources()
        assert len(res) == 6

    @pytest.mark.vcr
    def test_resources_no_pagination(self, ctx, monkeypatch):
        monkeypatch.setattr(QueryResourceManager, "resource_type", CVMInfoNoPagination)
        resource_manager = QueryResourceManager(ctx, {})
        res = resource_manager.resources()
        assert len(res) == 6
