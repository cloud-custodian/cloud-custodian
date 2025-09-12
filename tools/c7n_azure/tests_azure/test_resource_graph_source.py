# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
from datetime import timedelta

from tests_azure.azure_common import BaseTest, arm_template
from dateutil.parser import parse

from c7n.exceptions import PolicyValidationError


class ResourceGraphSource(BaseTest):

    def test_resource_graph_validate(self):
        p = self.load_policy({
            'name': 'test-azure-storage-arm-source',
            'resource': 'azure.storage',
            'source': 'resource-graph',
        }, validate=True)
        self.assertTrue(p)

    def test_resource_graph_validate_unsupported_resources(self):
        with self.assertRaises(PolicyValidationError):
            p = self.load_policy({
                'name': 'test-azure-storage-arm-source',
                'resource': 'azure.keyvault-certificate',
                'source': 'resource-graph',
            })
            self.assertTrue(p)

    @arm_template('storage.json')
    def test_resource_graph_and_arm_sources_storage_are_equivalent(self):
        p1 = self.load_policy({
            'name': 'test-azure-storage-arm-source',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctstorage*'}]
        })

        resources_arm = json.loads(json.dumps(p1.run()[0]))

        p2 = self.load_policy({
            'name': 'test-azure-storage-arm-source',
            'resource': 'azure.storage',
            'source': 'resource-graph',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctstorage*'}]
        })

        resources_resource_graph = json.loads(json.dumps(p2.run()[0]))

        self.assertTrue(resource_cmp(resources_arm,
                                     resources_resource_graph,
                                     ignore_properties=['keyCreationTime']))

    @arm_template('vm.json')
    def test_resource_graph_and_arm_sources_vm_are_equivalent(self):
        p1 = self.load_policy({
            'name': 'test-azure-vm-arm-source',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestvm*'}]
        })

        resources_arm = json.loads(json.dumps(p1.run()[0]))

        p2 = self.load_policy({
            'name': 'test-azure-vm-arm-source',
            'resource': 'azure.vm',
            'source': 'resource-graph',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctestvm*'}]
        })

        resources_resource_graph = json.loads(json.dumps(p2.run()[0]))

        # ARM returns the vm child extension resources that is not return with the resource graph
        self.assertTrue(
            resource_cmp(resources_arm, resources_resource_graph, ignore_properties=['resources']))


def resource_cmp(res1, res2, ignore_properties=[]):
    """
    Recursively compare for equality the resources return by ARM to the Resource Graph.
    Resource Graph has more properties than the default ARM call.
    :param ignore_properties: list of properties we can skip comparing
    :param res1: dictionary that represents the ARM resource
    :param res2: dictionary that represents the Resource Graph resource
    :return: True if every property for ARM is returned in the Resource Graph, else False
    """
    if not isinstance(res1, type(res2)):
        return False

    if isinstance(res1, dict):
        for prop in res1:
            if prop not in ignore_properties and \
                    (prop not in res2 or not resource_cmp(
                        res1[prop], res2[prop], ignore_properties)):
                return False

    elif isinstance(res1, list):
        if len(res1) != len(res2):
            return False

        for item1, item2 in zip(res1, res2):
            if not resource_cmp(item1, item2, ignore_properties):
                return False

    elif isinstance(res1, str):
        res1 = res1.lower()
        res2 = res2.lower()

        if res1 != res2:
            return datetime_str_equals(res1, res2)

    elif res1 != res2:
        return False

    return True


def datetime_str_equals(s1, s2, delta=timedelta(seconds=1)):
    """
    Resource Graph response truncates the microseconds of the datetime
    Example:
        ARM             {'creationTime' : '2019-10-08t00:29:01.673944z'}
        Resource Graph  {'creationTime' : '2019-10-08t00:29:01.6730000z'}
    """
    try:
        d1 = parse(s1)
        d2 = parse(s2)
        if d1 - d2 >= delta:
            return False
    except ValueError:
        return False

    return True
