# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json
import pytest

from c7n.data import CustodianProvider
from c7n.exceptions import PolicyExecutionError, PolicyValidationError
from .common import data_path


def test_data_policy(test):
    p = test.load_policy(
        {
            "name": "data-stuff",
            "resource": "c7n.data",
            "source": "static",
            "filters": [{"name": "bob"}],
            "query": [{"records": [{"name": "bob"}, {"name": "alice"}]}],
        }
    )
    resources = p.run()
    assert resources == [{"name": "bob", "c7n:MatchedFilters": ["name"]}]


def test_load_map_fails(test):
    p = test.load_policy(
        {
            "name": "data-nuff",
            "resource": "c7n.data",
            "source": "disk",
            "query": [{"path": data_path("config", "app-elb.json")}],
        }
    )

    with pytest.raises(PolicyExecutionError, match="in non list format"):
        p.run()


def test_load_map_expression_fails(test):
    p = test.load_policy(
        {
            "name": "data-nuff",
            "resource": "c7n.data",
            "source": "disk",
            "query": [{"path": data_path("config", "app-elb.json"), "key": "tags"}],
        }
    )

    with pytest.raises(PolicyExecutionError, match="in non list format"):
        p.run()


def test_load_array_expression(test):
    p = test.load_policy(
        {
            "name": "data-nuff",
            "resource": "c7n.data",
            "source": "disk",
            "query": [{"path": data_path("iam-actions.json"), "key": "account"}],
        }
    )
    assert p.run() == [
        'CloseAccount',
        'DeleteAlternateContact',
        'DisableRegion',
        'EnableRegion',
        'GetAccountInformation',
        'GetAlternateContact',
        'GetChallengeQuestions',
        'GetContactInformation',
        'GetRegionOptStatus',
        'ListRegions',
        'PutAlternateContact',
        'PutChallengeQuestions',
        'PutContactInformation',
    ]


def test_disk_bad_path(tmpdir, test):
    with pytest.raises(PolicyValidationError, match="invalid disk path"):
        test.load_policy(
            {
                "name": "stuff",
                "resource": "c7n.data",
                "source": "disk",
                "query": [{"path": str(tmpdir / "xyz")}],
            }
        )


def test_dir_missing_glob(tmpdir, test):
    with pytest.raises(PolicyValidationError, match="glob pattern required"):
        test.load_policy(
            {
                "name": "stuff",
                "resource": "c7n.data",
                "source": "disk",
                "query": [{"path": str(tmpdir)}],
            }
        )


def test_invalid_static_record(test):
    with pytest.raises(PolicyValidationError, match="invalid static data source `records`"):
        test.load_policy(
            {
                "name": "smack",
                "resource": "c7n.data",
                "source": "static",
                "query": [{"records": "abc"}],
            }
        )


def test_bad_source(test):
    with pytest.raises(PolicyValidationError, match="invalid source dask"):
        test.load_policy(
            {"name": "snack", "resource": "c7n.data", "source": "dask"}, validate=False
        )


def test_provider_initialize(test):
    assert CustodianProvider().initialize({}) is None


def test_provider_initialize_policies(test):
    x = []
    assert CustodianProvider().initialize_policies(x, {}) is x


def test_empty_get_records(test):
    p = test.load_policy(
        {
            "name": "snack",
            "resource": "c7n.data",
            "query": [{"records": ["a", "b"]}],
            "source": "static",
        }
    )
    assert p.resource_manager.get_resources([1, 2]) == []


def test_load_dir_rglob(tmpdir, test):
    (tmpdir.mkdir("xyz") / "foo.json").write(json.dumps(["a", "b", "c"]))
    (tmpdir.mkdir("abc") / "bar.json").write(json.dumps(["d", "e", "f"]))
    p = test.load_policy(
        {
            "name": "stuff",
            "resource": "c7n.data",
            "source": "disk",
            "query": [{"path": str(tmpdir), "glob": "**/*.json"}],
        }
    )
    assert sorted(p.run()) == ["a", "b", "c", "d", "e", "f"]
