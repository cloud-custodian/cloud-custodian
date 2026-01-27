# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest
from tc_common import BaseTest


class TestMySQL(BaseTest):

    @pytest.mark.vcr
    def test_mysql_engine_value(self):
        policy = self.load_policy(
            {
                "name": "test_mysql_engine_value",
                "resource": "tencentcloud.mysql",
                "filters": [
                    {
                        "type": "value",
                        "key": "EngineType",
                        "value": ["InnoDB", "RocksDB"],
                        "op": "in"
                    }, {
                        "type": "value",
                        "key": "EngineVersion",
                        "op": "in",
                        "value": [
                            "5.5",
                            "5.6",
                            "5.7",
                            "8.0"
                        ]
                    }
                ]
            }
        )
        resources = policy.run()
        engine_set = {resource['EngineType'] for resource in resources}
        assert len(resources) == 2 and len(engine_set) == 2

    @pytest.mark.vcr
    def test_mysql_encryption_not_enabled_filter(self):
        policy = self.load_policy(
            {
                "name": "test_mysql_encryption_not_enabled_filter",
                "resource": "tencentcloud.mysql",
                "query": [{"InstanceIds": ["cdb-lbxusyi7"]}],
                "filters": [
                    {
                        "type": "encryption",
                        "value": False
                    }]
            })
        resources = policy.run()
        assert len(resources) == 1

    @pytest.mark.vcr
    def test_mysql_create_time(self):
        policy = self.load_policy(
            {
                "name": "test_mysql_create_time",
                "resource": "tencentcloud.mysql",
                "query": [{"InstanceIds": ["cdb-lbxusyi7"]}],
                "filters": [
                    {
                        "type": "value",
                        "key": "CreateTime",
                        "value": 1,
                        "value_type": "age",
                        "op": "gte"
                    }]
            })
        resources = policy.run()
        assert len(resources) == 1

    @pytest.mark.vcr
    def test_metrics_filter(self):
        policy = self.load_policy(
            {
                "name": "test_metrics_filter",
                "resource": "tencentcloud.mysql",
                "filters": [
                    {
                        "type": "value",
                        "key": "CreateTime",
                        "value": 1,
                        "value_type": "age",
                        "op": "gte"
                    },
                    {
                        "type": "metrics",
                        "name": "MaxConnections",
                        "statistics": "Sum",
                        "missing-value": 0,
                        "period": 3600,
                        "days": 3,
                        "value": 0,
                        "op": "equal"
                    }]
            },
            region="ap-guangzhou")
        resources = policy.run()
        assert len(resources) == 1
        assert resources[0]["InstanceId"] == 'cdb-o6tjxap7'
