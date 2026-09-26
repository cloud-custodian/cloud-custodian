# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.resources import load_resources


def test_resource_map_entries_import():
    # every openstack resource map entry must name a class that exists
    assert load_resources(['openstack.*']) == []
