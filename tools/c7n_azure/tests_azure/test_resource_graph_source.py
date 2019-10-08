# Copyright 2019 Microsoft Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from datetime import timedelta

from tests_azure.azure_common import BaseTest, arm_template
from dateutil.parser import parse


class ResourceGraphSource(BaseTest):

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

        resources_arm = p1.run()[0]

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
        }, validate=True)

        resources_resource_graph = p2.run()[0]

        self.assertTrue(resource_cmp(resources_arm, resources_resource_graph))

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

        resources_arm = p1.run()[0]

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
        }, validate=True)

        resources_resource_graph = p2.run()[0]

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
    if type(res1) != type(res2):
        return False

    if type(res1) == dict:
        for prop in res1:
            if prop not in ignore_properties and \
                    (prop not in res2 or not resource_cmp(res1[prop], res2[prop])):
                return False

    elif type(res1) == list:
        if len(res1) != len(res2):
            return False

        for item1, item2 in zip(res1, res2):
            if not resource_cmp(item1, item2):
                return False

    elif type(res1) == str:
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
