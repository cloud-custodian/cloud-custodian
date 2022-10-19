# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest
from tc_common import BaseTest


class TestCdb(BaseTest):

    @pytest.mark.vcr
    def test_cdb_engine_value(self):
        policy = self.load_policy(
            {
                "name": "test_cdb_engine_value",
                "resource": "tencentcloud.cdb",
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
    def test_cdb_encryption_not_enabled_filter(self):
        policy = self.load_policy(
            {
                "name": "test_cdb_encryption_not_enabled_filter",
                "resource": "tencentcloud.cdb",
                "query": [{"InstanceIds": ["cdb-lbxusyi7"]}],
                "filters": [
                    {
                        "type": "value",
                        "key": "Encryption",
                        "value": "NO",
                    }]
            })
        resources = policy.run()
        assert len(resources) == 1

    @pytest.mark.vcr
    def test_cdb_create_time(self):
        policy = self.load_policy(
            {
                "name": "test_cdb_create_time",
                "resource": "tencentcloud.cdb",
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
