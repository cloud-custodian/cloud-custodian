# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from copy import deepcopy
import jmespath
import pytest
from c7n.query import sources
from c7n_tencentcloud.query import (ResourceTypeInfo, ResourceQuery,
                                    DescribeSource, QueryResourceManager)


def test_resource_type():
    service_data = "Foo"
    version_data = "2022-01-01"

    class Foo(ResourceTypeInfo):
        service = service_data
        version = version_data

    expected = f"<Type info service:{service_data} client:{version_data}>"
    assert repr(Foo) == expected


class ResourceType_1(ResourceTypeInfo):
    id: str = "id"
    endpoint: str = "endpoint_1"
    service: str = "service_1"
    version: str = "version_1"
    enum_spec = ("action_1", "Response.data", None)


class ResourceType_2(ResourceTypeInfo):
    id: str = "id"
    endpoint: str = "endpoint_2"
    service: str = "service_2"
    version: str = "version_2"
    enum_spec = ("action_2", "Response.data[]", {"Limit": 10})


response = {
    "action_1": {
        "Response": {
            "data": [{
                "id": "id_1",
                "type": "cvm"
            }],
            "ResourceTagMappingList": [
                {"Tags": [{
                    "TagKey": "key1",
                    "TagValue": "tag_value"
                }]}
            ]
        }
    },
    "action_2": {
        "Response": {
            "data": [
                {
                    "id": "id_2",
                    "type": "cvm"
                },
                {
                    "id": "id_3",
                    "type": "cvm"
                }
            ],
            "ResourceTagMappingList": [
                {"Tags": [{
                    "TagKey": "key2",
                    "TagValue": "tag_value"
                }]}
            ]
        }
    }
}


# (resource_type, response_data, expected_params, expected_return_value,
# TestQueryMananger:expected_return_valu)
resource_query_test_cases = [
    (
        ResourceType_1,
        response[ResourceType_1.enum_spec[0]],
        {},
        response[ResourceType_1.enum_spec[0]]["Response"]["data"],
        [{"id": "id_1", "type": "cvm", "Tags": [{"Key": "key1", "Value": "tag_value"}]}]
    ),
    (
        ResourceType_2,
        response[ResourceType_2.enum_spec[0]],
        {"Limit": 10},
        response[ResourceType_2.enum_spec[0]]["Response"]["data"],
        [
            {"id": "id_2", "type": "cvm", "Tags": [{"Key": "key2", "Value": "tag_value"}]},
            {"id": "id_3", "type": "cvm", "Tags": [{"Key": "key2", "Value": "tag_value"}]}
        ]
    )
]


@pytest.fixture()
def session():
    class Client:
        def __init__(self) -> None:
            self.test_case = None
            self.check_params_flag = True

        def set_test_case(self, test_case):
            self.test_case = test_case

        def set_check_params_flag(self, flag):
            self.check_params_flag = flag

        def execute_query(self, action, params):
            if self.check_params_flag and params != self.test_case[2]:
                raise Exception(f"wrong params, {params} != {self.test_case[2]}")
            return deepcopy(self.test_case[1])

        def execute_paged_query(self, action, params, jsonpath, paging_def):
            if self.check_params_flag and params != self.test_case[2]:
                raise Exception("wrong params")
            return deepcopy(jmespath.search(jsonpath, self.test_case[1]))

    class Sesion:
        def __init__(self) -> None:
            self._cli = Client()

        def client(self, *args, **kwargs):
            return self._cli

    return Sesion()


@pytest.fixture(params=resource_query_test_cases)
def test_case(request):
    return request.param


def test_resource_query_filter(session, test_case):
    client = session.client()
    client.set_test_case(test_case)

    resource_query = ResourceQuery(session)
    res = resource_query.filter("ap-shanghai", test_case[0], {})
    assert res == test_case[3]


def test_resource_query_paged_filter(session, test_case):
    client = session.client()
    client.set_test_case(test_case)

    resource_query = ResourceQuery(session)
    res = resource_query.paged_filter("ap-shanghai", test_case[0], {})
    assert res == test_case[3]


def source_get(*args):
    return DescribeSource


# (data, expected_query_params)
data_test_cases = [
    ({}, {}),
    ({"query": [{"Key": "Value"}]}, {"Filters": [{"Key": "Value"}]})
]


@pytest.fixture(params=data_test_cases)
def data_test_case(request):
    return request.param


class TestQueryResourceManager:
    def test_get_permissions(self, ctx, monkeypatch):
        monkeypatch.setattr(sources, "get", source_get)
        resource_manager = QueryResourceManager(ctx, {})
        assert resource_manager.get_permissions() == []

    def test_get_resource_query_params(self, ctx, data_test_case, monkeypatch):
        monkeypatch.setattr(sources, "get", source_get)
        resource_manager = QueryResourceManager(ctx, data_test_case[0])
        res = resource_manager.get_resource_query_params()
        assert res == data_test_case[1]

    def test_resources(self, ctx, session, test_case, monkeypatch):
        client = session.client()
        client.set_test_case(test_case)
        client.set_check_params_flag(False)
        monkeypatch.setattr(sources, "get", source_get)
        monkeypatch.setattr(QueryResourceManager, "resource_type", test_case[0])
        resource_manager = QueryResourceManager(ctx, {})
        res = resource_manager.resources()
        assert res == test_case[4]
