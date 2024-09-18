# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from deploy_chart import Deployment


def test_write_values_to_file():
    data = {"abc": 1}
    expected = "abc: 1\n"
    path = Deployment.write_values_to_file(data)
    with open(path, "r") as f:
        assert f.read() == expected
