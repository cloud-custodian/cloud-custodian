# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from . import tools_tags as tools
from .azure_common import BaseTest, arm_template
from c7n_azure.session import Session


class FunctionalFiltersTagsTest(BaseTest):

    rg_name = 'test_vm'
    vm_name = 'cctestvm'
    DAYS = 10

    initial_tags = {}

    @classmethod
    def setUpClass(cls, *args, **kwargs):
        super(FunctionalFiltersTagsTest, cls).setUpClass(*args, **kwargs)
        cls.client = Session().client('azure.mgmt.compute.ComputeManagementClient')

        try:
            cls.initial_tags = tools.get_tags(cls.client, cls.rg_name, cls.vm_name)

            # Using some date in the past for marked-for-op to avoid patching utc_now
            tools.set_tags(cls.client, cls.rg_name, cls.vm_name,
                           {'test_filters_tag': 'test_value',
                            'custodian_status': 'TTL: delete@2018-01-01'})
        except Exception:
            # Can fail without real auth
            pass

    @classmethod
    def tearDownClass(cls, *args, **kwargs):
        super(FunctionalFiltersTagsTest, cls).tearDownClass(*args, **kwargs)
        try:
            tools.set_tags(cls.client, cls.rg_name, cls.vm_name, cls.initial_tags)
        except Exception:
            # Can fail without real auth
            pass

    @arm_template('vm.json')
    def test_tag(self):
        resources = self._run_policy([{'tag:test_filters_tag': 'test_value'}])
        self.assertEqual(len(resources), 1)

    @arm_template('vm.json')
    def test_marked_for_op(self):
        resources = self._run_policy([{'type': 'marked-for-op', 'op': 'delete'}])
        self.assertEqual(len(resources), 1)

    def _run_policy(self, filters):
        return self.load_policy({
            'name': 'test-tag',
            'resource': 'azure.vm',
            'filters': [{
                'type': 'value',
                'key': 'name',
                'op': 'eq',
                'value_type': 'normalize',
                'value': self.vm_name
            }] + filters
        }).run()
