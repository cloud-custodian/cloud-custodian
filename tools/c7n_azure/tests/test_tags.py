# Copyright 2015-2018 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

import datetime
import logging
import re

from azure_common import BaseTest, arm_template
from c7n_azure.actions import AutoTagUser
from c7n_azure.session import Session
from mock import patch

from c7n.exceptions import PolicyValidationError
from c7n.filters import FilterValidationError


class TagsTest(BaseTest):
    # regex for identifying valid email addresses
    EMAIL_REGEX = r"[^@]+@[^@]+\.[^@]+"

    logger = logging.getLogger()

    vm_name = 'cctestvm'
    rg_name = 'test_vm'

    client = Session().client('azure.mgmt.compute.ComputeManagementClient')

    def setUp(self):
        super(TagsTest, self).setUp()
        self.before_tags = self.get_tags(self.rg_name, self.vm_name)

    def tearDown(self):
        self.after_tags = self.get_tags(self.rg_name, self.vm_name)
        tags_to_remove = [k for k in self.after_tags.keys() if k not in self.before_tags.keys()]

        if tags_to_remove:
            if (self.after_tags != self.before_tags):
                p = self.load_policy({
                    'name': 'test-azure-tag',
                    'resource': 'azure.vm',
                    'filters': [
                        {'type': 'value',
                         'key': 'name',
                         'op': 'eq',
                         'value_type': 'normalize',
                         'value': 'cctestvm'}
                    ],
                    'actions': [
                        {'type': 'untag',
                         'tags':
                             tags_to_remove}
                    ],
                })
                p.run()
                self.after_tags = self.get_tags(self.rg_name, self.vm_name)

        super(TagsTest, self).tearDown()

    def get_tags(self, rg_name=rg_name, vm_name=vm_name):
        vm = self.client.virtual_machines.get(rg_name, vm_name)
        return vm.tags

    def get_vm_resource_id(self, rg_name=rg_name, vm_name=vm_name):
        vm = self.client.virtual_machines.get(rg_name, vm_name)
        return vm.id

    def dict_diff(self, a, b):
        return set(a.items()) ^ set(b.items())

    def test_tag_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-tag',
                'resource': 'azure.resourcegroup',
                'actions': [
                    {'type': 'tag',
                     'tag': 'test',
                     'value': 'schema'},
                    {'type': 'tag-trim',
                     'space': 5},
                    {'type': 'mark-for-op',
                     'op': 'delete',
                     'days': 10},
                    {'type': 'auto-tag-user',
                     'tag': 'user'},
                    {'type': 'untag',
                     'tags': ['test']}

                ]
            }, validate=True)
            self.assertTrue(p)

    @arm_template('vm.json')
    def test_add_or_update_single_tag(self):
        """Verifies we can add a new tag to a VM and not modify
        an existing tag on that resource
        """

        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'}
            ],
            'actions': [
                {'type': 'tag',
                 'tag': 'tag1',
                 'value': 'value1'}
            ],
        })
        p.run()

        after_tags = self.get_tags(self.rg_name, self.vm_name)
        self.assertEqual(self.dict_diff(self.before_tags, after_tags), {('tag1', 'value1')})

    @arm_template('vm.json')
    def test_add_or_update_tags(self):
        """Adds tags to an empty resource group, then updates one
        tag and adds a new tag
        """
        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'}
            ],
            'actions': [
                {'type': 'tag',
                 'tags': {'pre-existing-1': 'unmodified', 'pre-existing-2': 'unmodified'}},
            ],
        })
        p.run()

        # verify initial tag set
        after_tags = self.get_tags(self.rg_name, self.vm_name)
        self.assertEqual(self.dict_diff(self.before_tags, after_tags),
                         {('pre-existing-1', 'unmodified'), ('pre-existing-2', 'unmodified')})

        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'}
            ],
            'actions': [
                {'type': 'tag',
                 'tags': {'tag1': 'value1', 'pre-existing-1': 'modified'}}
            ],
        })
        p.run()

        # verify modified tags
        after_tags = self.get_tags(self.rg_name, self.vm_name)
        self.assertEqual(self.dict_diff(self.before_tags, after_tags),
                         {('tag1', 'value1'),
                          ('pre-existing-1', 'modified'),
                          ('pre-existing-2', 'unmodified')})

    def test_cant_have_both_tag_and_tags(self):
        with self.assertRaises(FilterValidationError):
            p = self.load_policy({
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'actions': [
                    {'type': 'tag',
                     'tags': {'tag2': 'value2'},
                     'tag': 'tag1',
                     'value': 'value1'}
                ],
            })
            p.run()

    def test_must_specify_tags_or_tag_and_value(self):
        with self.assertRaises(FilterValidationError):
            p = self.load_policy({
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'actions': [
                    {'type': 'tag'}
                ],
            })
            p.run()

    def test_must_specify_non_empty_tags(self):
        with self.assertRaises(FilterValidationError):
            p = self.load_policy({
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'actions': [
                    {'type': 'tag',
                     'tags': {}}
                ],
            })
            p.run()

    def test_must_specify_both_tag_and_value(self):
        with self.assertRaises(FilterValidationError):
            # Missing value
            p = self.load_policy({
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'actions': [
                    {'type': 'tag',
                     'tag': 'myTag'}
                ],
            })
            p.run()

            # Missing tag
            p = self.load_policy({
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'actions': [
                    {'type': 'tag',
                     'value': 'myValue'}
                ],
            })
            p.run()

    @arm_template('vm.json')
    def test_remove_single_tag(self):
        """Verifies we can delete a tag to a VM and not modify
        an existing tag on that resource
        """
        p = self.load_policy({
            'name': 'test-azure-remove-single-tag',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'}
            ],
            'actions': [
                {'type': 'tag',
                 'tag': 'tag1',
                 'value': 'to-delete'}
            ],
        })
        p.run()

        # verify the initial tag set
        after_tags = self.get_tags(self.rg_name, self.vm_name)
        self.assertTrue(after_tags.get('tag1') == 'to-delete')

        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'}
            ],
            'actions': [
                {'type': 'untag',
                 'tags': ['tag1']}
            ],
        })
        p.run()

        # verify that the a tag is deleted without modifying existing tags
        after_tags = self.get_tags(self.rg_name, self.vm_name)
        self.assertEqual(self.before_tags, after_tags)

    @arm_template('vm.json')
    def test_remove_tags(self):
        """Verifies we can delete multiple tags from a resource
        group without modifying existing tags.
        """
        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'}
            ],
            'actions': [
                {'type': 'tag',
                 'tags': {'pre-existing-1': 'to-keep', 'pre-existing-2': 'to-keep',
                          'added-1': 'to-delete', 'added-2': 'to-delete'}},
            ],
        })
        p.run()

        # verify initial tag set
        after_tags = self.get_tags(self.rg_name, self.vm_name)
        self.assertTrue('pre-existing-1' in after_tags)
        self.assertTrue('pre-existing-2' in after_tags)
        self.assertTrue('added-1' in after_tags)
        self.assertTrue('added-2' in after_tags)

        p = self.load_policy({
            'name': 'test-azure-remove-tag',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'}
            ],
            'actions': [
                {'type': 'untag',
                 'tags': ['added-1', 'added-2']}
            ],
        })
        p.run()

        # verify tags removed and pre-existing tags not removed
        after_tags = self.get_tags(self.rg_name, self.vm_name)
        self.assertTrue('pre-existing-1' in after_tags)
        self.assertTrue('pre-existing-2' in after_tags)
        self.assertTrue('added-1' not in after_tags)
        self.assertTrue('added-2' not in after_tags)

    @arm_template('vm.json')
    def test_removal_does_not_raise_on_nonexistent_tag(self):
        """Verifies attempting to delete a tag that is
        not on the resource does not throw an error
        """

        self.assertTrue('tag-does-not-exist' not in self.before_tags)

        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'}
            ],
            'actions': [
                {'type': 'untag',
                 'tags': ['tag-does-not-exist']},
            ],
        })

        raised = False
        try:
            p.run()
        except KeyError:
            raised = True

        # verify no exception raised and no changes to tags on resource
        after_tags = self.get_tags(self.rg_name, self.vm_name)
        self.assertFalse(raised)
        self.assertEqual(self.before_tags, after_tags)

    def test_must_specify_tags_to_remove(self):
        with self.assertRaises(FilterValidationError):
            p = self.load_policy({
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'actions': [
                    {'type': 'untag'}
                ],
            })
            p.run()

    @arm_template('vm.json')
    def test_auto_tag_add_creator_tag(self):
        """Adds CreatorEmail to a resource group."""
        with patch('c7n_azure.actions.utcnow') as utc_patch:
            utc_patch.return_value = self.get_test_date()

            p = self.load_policy({
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'filters': [
                    {'type': 'value',
                     'key': 'name',
                     'op': 'eq',
                     'value_type': 'normalize',
                     'value': 'cctestvm'}
                ],
                'actions': [
                    {'type': 'auto-tag-user',
                     'tag': 'CreatorEmail',
                     'days': 10,
                     'update': True},
                ],
            })
            p.run()

            after_tags = self.get_tags(self.rg_name, self.vm_name)
            self.assertTrue(re.match(self.EMAIL_REGEX, after_tags.get('CreatorEmail')))

    @arm_template('vm.json')
    def test_auto_tag_update_false_noop_for_existing_tag(self):
        """Adds CreatorEmail to a resource group"""
        with patch('c7n_azure.actions.utcnow') as utc_patch:
            utc_patch.return_value = self.get_test_date()

            # setup by adding an existing CreatorEmail tag
            p = self.load_policy({
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'filters': [
                    {'type': 'value',
                     'key': 'name',
                     'op': 'eq',
                     'value_type': 'normalize',
                     'value': 'cctestvm'}
                ],
                'actions': [
                    {'type': 'tag',
                     'tag': 'CreatorEmail',
                     'value': 'do-not-modify'},
                ],
            })
            p.run()

            p = self.load_policy({
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'filters': [
                    {'type': 'value',
                     'key': 'name',
                     'op': 'eq',
                     'value_type': 'normalize',
                     'value': 'cctestvm'}
                ],
                'actions': [
                    {'type': 'auto-tag-user',
                     'tag': 'CreatorEmail',
                     'update': False,
                     'days': 10}
                ],
            })
            p.run()

            after_tags = self.get_tags(self.rg_name, self.vm_name)
            self.assertEqual(after_tags['CreatorEmail'], 'do-not-modify')

    def test_auto_tag_days_must_be_btwn_1_and_90(self):
        with self.assertRaises(FilterValidationError):
            p = self.load_policy({
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'actions': [
                    {'type': 'auto-tag-user',
                     'tag': 'CreatorEmail',
                     'days': 91}
                ],
            })
            p.run()

        with self.assertRaises(FilterValidationError):
            p = self.load_policy({
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'actions': [
                    {'type': 'auto-tag-user',
                     'tag': 'CreatorEmail',
                     'days': 0}
                ],
            })
            p.run()

    def test_auto_tag_user_event_grid_mode_with_days_fails_validation(self):
        self.assertRaises(
            PolicyValidationError,
            self.load_policy,
            {
                'name': 'test-azure-tag',
                'resource': 'azure.resourcegroup',
                'mode': {
                    'type': 'azure-event-grid',
                    'events': [
                        {
                            'resourceProvider': 'Microsoft.Resources/subscriptions/resourceGroups',
                            'event': 'write'
                        }
                    ]},
                'actions': [
                    {'type': 'auto-tag-user',
                     'tag': 'CreatorEmail',
                     'days': 40}
                ],
            },
            session_factory=None,
            validate=True,
        )

    @arm_template('vm.json')
    def test_auto_tag_user_event_grid_user_event(self):
        policy = self.load_policy(
            {
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'mode': {
                    'type': 'azure-event-grid',
                    'events': [
                        {
                            'resourceProvider': 'Microsoft.Compute/virtualMachines',
                            'event': 'write'
                        }
                    ]},
                'actions': [
                    {'type': 'auto-tag-user',
                     'tag': 'CreatorEmail',
                     'update': True}
                ],
            },
            session_factory=None,
            validate=True,
        )

        vm_id = self.get_vm_resource_id()

        event = {
            'subject': vm_id,
            'data': {
                'authorization': {
                    'evidence': {
                        'principalType': 'User'
                    }
                },
                'claims': {
                    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn':
                        'cloud@custodian.com',
                },
                'operationName': 'Microsoft.Compute/virtualMachines/write',
            }
        }

        policy.push(event, None)

        after_tags = self.get_tags()
        self.assertEqual(after_tags['CreatorEmail'], 'cloud@custodian.com')

    @arm_template('vm.json')
    def test_auto_tag_user_event_grid_service_admin_event(self):
        policy = self.load_policy(
            {
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'mode': {
                    'type': 'azure-event-grid',
                    'events': [
                        {
                            'resourceProvider': 'Microsoft.Compute/virtualMachines',
                            'event': 'write'
                        }
                    ]},
                'actions': [
                    {'type': 'auto-tag-user',
                     'tag': 'SvcAdminEmail',
                     'update': True}
                ],
            },
            session_factory=None,
            validate=True,
        )

        vm_id = self.get_vm_resource_id()

        event = {
            'subject': vm_id,
            'data': {
                'authorization': {
                    'evidence': {
                        'role': 'Subscription Admin'
                    }
                },
                'claims': {
                    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress':
                        'cloud@custodian.com',
                },
                'operationName': 'Microsoft.Compute/virtualMachines/write',
            }
        }

        policy.push(event, None)

        after_tags = self.get_tags()
        self.assertEqual(after_tags['SvcAdminEmail'], 'cloud@custodian.com')

    @arm_template('vm.json')
    def test_auto_tag_user_event_grid_sp_event(self):
        policy = self.load_policy(
            {
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'mode': {
                    'type': 'azure-event-grid',
                    'events': [
                        {
                            'resourceProvider': 'Microsoft.Compute/virtualMachines',
                            'event': 'write'
                        }
                    ]},
                'actions': [
                    {'type': 'auto-tag-user',
                     'tag': 'CreatorEmail',
                     'update': True}
                ],
            },
            session_factory=None,
            validate=True,
        )

        vm_id = self.get_vm_resource_id()

        event = {
            'subject': vm_id,
            'data': {
                'authorization': {
                    'evidence': {
                        'principalType': 'ServicePrincipal'
                    }
                },
                'claims': {
                    'appid': '12345',
                },
                'operationName': 'Microsoft.Compute/virtualMachines/write',
            }
        }

        policy.push(event, None)

        after_tags = self.get_tags()
        self.assertEqual(after_tags['CreatorEmail'], '12345')

    @arm_template('vm.json')
    def test_auto_tag_user_event_grid_group_event(self):
        policy = self.load_policy(
            {
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'mode': {
                    'type': 'azure-event-grid',
                    'events': [
                        {
                            'resourceProvider': 'Microsoft.Compute/virtualMachines',
                            'event': 'write'
                        }
                    ]},
                'actions': [
                    {'type': 'auto-tag-user',
                     'tag': 'CreatorEmail',
                     'update': True}
                ],
            },
            session_factory=None,
            validate=True,
        )

        vm_id = self.get_vm_resource_id()

        event = {
            'subject': vm_id,
            'data': {
                'authorization': {
                    'evidence': {
                        'principalType': 'User'
                    }
                },
                'claims': {
                    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn':
                        'cloud@custodian.com',
                },
                'operationName': 'Microsoft.Compute/virtualMachines/write',
            }
        }

        policy.push(event, None)

        after_tags = self.get_tags()
        self.assertEqual(after_tags['CreatorEmail'], 'cloud@custodian.com')

    @arm_template('vm.json')
    def test_auto_tag_user_event_grid_default_to_upn(self):
        policy = self.load_policy(
            {
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'mode': {
                    'type': 'azure-event-grid',
                    'events': [
                        {
                            'resourceProvider': 'Microsoft.Compute/virtualMachines',
                            'event': 'write'
                        }
                    ]},
                'actions': [
                    {'type': 'auto-tag-user',
                     'tag': 'CreatorEmail',
                     'update': True}
                ],
            },
            session_factory=None,
            validate=True,
        )

        vm_id = self.get_vm_resource_id()

        event = {
            'subject': vm_id,
            'data': {
                'authorization': {
                    'evidence': {
                        'principalType': 'DoesNotMatter'
                    }
                },
                'claims': {
                    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn':
                        'cloud@custodian.com',
                    'claim1': 'myemail@contoso.com'
                },
                'operationName': 'Microsoft.Compute/virtualMachines/write',
            }
        }

        policy.push(event, None)

        after_tags = self.get_tags()
        self.assertEqual(after_tags['CreatorEmail'], 'cloud@custodian.com')

    @arm_template('vm.json')
    def test_auto_tag_user_event_grid_find_email_in_claims(self):
        policy = self.load_policy(
            {
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'mode': {
                    'type': 'azure-event-grid',
                    'events': [
                        {
                            'resourceProvider': 'Microsoft.Compute/virtualMachines',
                            'event': 'write'
                        }
                    ]},
                'actions': [
                    {'type': 'auto-tag-user',
                     'tag': 'CreatorEmail',
                     'update': True}
                ],
            },
            session_factory=None,
            validate=True,
        )

        vm_id = self.get_vm_resource_id()

        event = {
            'subject': vm_id,
            'data': {
                'authorization': {
                    'evidence': {
                        'principalType': 'DoesNotMatter'
                    }
                },
                'claims': {
                    'claim1': 'notEmailAddress',
                    'claim2': 'myemail@contoso.com'
                },
                'operationName': 'Microsoft.Compute/virtualMachines/write',
            }
        }

        policy.push(event, None)

        after_tags = self.get_tags()
        self.assertEqual(after_tags['CreatorEmail'], 'myemail@contoso.com')

    @arm_template('vm.json')
    def test_auto_tag_user_event_grid_unknown_principal_event(self):
        policy = self.load_policy(
            {
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'mode': {
                    'type': 'azure-event-grid',
                    'events': [
                        {
                            'resourceProvider': 'Microsoft.Compute/virtualMachines',
                            'event': 'write'
                        }
                    ]},
                'actions': [
                    {'type': 'auto-tag-user',
                     'tag': 'CreatorEmail',
                     'update': True}
                ],
            },
            session_factory=None,
            validate=True,
        )

        vm_id = self.get_vm_resource_id()

        event = {
            'subject': vm_id,
            'data': {
                'authorization': {
                    'evidence': {
                        'principalType': 'Group'
                    }
                },
                'claims': {
                },
                'operationName': 'Microsoft.Compute/virtualMachines/write',
            }
        }

        policy.push(event, None)

        after_tags = self.get_tags()
        self.assertEqual(after_tags['CreatorEmail'], 'Unknown')

    @arm_template('vm.json')
    def test_auto_tag_user_event_grid_user_event_missing_info(self):
        policy = self.load_policy(
            {
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'mode': {
                    'type': 'azure-event-grid',
                    'events': [
                        {
                            'resourceProvider': 'Microsoft.Compute/virtualMachines',
                            'event': 'write'
                        }
                    ]},
                'actions': [
                    {'type': 'auto-tag-user',
                     'tag': 'CreatorEmail',
                     'update': True}
                ],
            },
            session_factory=None,
            validate=True,
        )

        vm_id = self.get_vm_resource_id()

        event = {
            'subject': vm_id,
            'data': {
                'authorization': {
                    'evidence': {
                        'principalType': 'User'
                    }
                },
                'claims': {
                },
                'operationName': 'Microsoft.Compute/virtualMachines/write',
            }
        }

        policy.push(event, None)

        after_tags = self.get_tags()
        self.assertEqual(after_tags['CreatorEmail'], AutoTagUser.default_user)

    @arm_template('vm.json')
    def test_auto_tag_user_event_grid_sp_event_missing_info(self):
        policy = self.load_policy(
            {
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'mode': {
                    'type': 'azure-event-grid',
                    'events': [
                        {
                            'resourceProvider': 'Microsoft.Compute/virtualMachines',
                            'event': 'write'
                        }
                    ]},
                'actions': [
                    {'type': 'auto-tag-user',
                     'tag': 'CreatorEmail',
                     'update': True}
                ],
            },
            session_factory=None,
            validate=True,
        )

        vm_id = self.get_vm_resource_id()

        event = {
            'subject': vm_id,
            'data': {
                'authorization': {
                    'evidence': {
                        'principalType': 'ServicePrincipal'
                    }
                },
                'claims': {
                },
                'operationName': 'Microsoft.Compute/virtualMachines/write',
            }
        }

        policy.push(event, None)

        after_tags = self.get_tags()
        self.assertEqual(after_tags['CreatorEmail'], AutoTagUser.default_user)

    def test_tag_trim_space_must_be_btwn_0_and_15(self):
        with self.assertRaises(FilterValidationError):
            p = self.load_policy({
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'actions': [
                    {'type': 'tag-trim',
                     'space': -1}
                ],
            })
            p.run()

        with self.assertRaises(FilterValidationError):
            p = self.load_policy({
                'name': 'test-azure-tag',
                'resource': 'azure.vm',
                'actions': [
                    {'type': 'tag-trim',
                     'space': 16}
                ],
            })
            p.run()

    @arm_template('vm.json')
    def test_tag_trim_does_nothing_if_space_available(self):
        """Verifies tag trim returns without trimming tags
        if the resource has space equal to or greater than
        the space value.
        """

        # verify there is at least 1 space for a tag
        self.assertLess(len(self.before_tags), 15)

        # trim for space for 1 tag
        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'}
            ],
            'actions': [
                {'type': 'tag-trim',
                 'space': 1}
            ],
        })
        p.run()

        # verify that tags are unchanged
        after_tags = self.get_tags(self.rg_name, self.vm_name)
        self.assertEqual(self.before_tags, after_tags)

    @arm_template('vm.json')
    def test_tag_trim_removes_tags_for_space(self):
        """Verifies tag trim removes tags when the space value
        and number of tags on the resource are greater than the max
        tag value (15)
        """

        # Add tags to trim
        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'}
            ],
            'actions': [
                {'type': 'tag',
                 'tags': {'tag-to-trim1': 'value1', 'tag-to-trim2': 'value2'}}
            ],
        })
        p.run()

        after_tags = self.get_tags(self.rg_name, self.vm_name)
        self.assertTrue(len(after_tags) > 1)

        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'}
            ],
            'actions': [
                {'type': 'tag-trim',
                 'space': 15 - len(self.before_tags),
                 'preserve': [k for k in self.before_tags.keys()]
                 }
            ],
        })
        p.run()

        # verify that tags were trimmed to
        # have 14 spaces and 1 preserved
        after_tags = self.get_tags(self.rg_name, self.vm_name)
        self.assertEqual(self.before_tags, after_tags)

    @arm_template('vm.json')
    def test_tag_trim_space_0_removes_all_tags_but_preserve(self):
        """Verifies tag trim removes all other tags but tags
        listed in preserve
        """

        # Add tags to trim
        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'}
            ],
            'actions': [
                {'type': 'tag',
                 'tags': {'tag-to-trim1': 'value1', 'tag-to-trim2': 'value2',
                          'tag-to-trim3': 'value3'}}
            ],
        })
        p.run()

        # verify initial tags contain more than testtag
        after_tags = self.get_tags(self.rg_name, self.vm_name)
        self.assertTrue('tag-to-trim1' in after_tags)
        self.assertTrue('tag-to-trim2' in after_tags)
        self.assertTrue('tag-to-trim3' in after_tags)

        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'}
            ],
            'actions': [
                {'type': 'tag-trim',
                 'space': 0,
                 'preserve': [k for k in self.before_tags.keys()]
                 }
            ],
        })
        p.run()

        # verify all tags trimmed but testtag
        after_tags = self.get_tags(self.rg_name, self.vm_name)
        self.assertEqual(self.before_tags, after_tags)

    @arm_template('vm.json')
    @patch('logging.Logger.warning')
    def test_tag_trim_warns_no_candidates(self, logger_mock):
        """Verifies tag trim warns when there are no candidates
        to trim
        """

        p = self.load_policy({
            'name': 'test-azure-tag',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'}
            ],
            'actions': [
                {'type': 'tag-trim',
                 'space': 0,
                 'preserve': [k for k in self.before_tags.keys()]
                 }
            ],
        })
        p.run()

        expected_warning_regex = (
            "Could not find any candidates to trim "
            "/subscriptions/[^/]+/resourceGroups/[^/]+/"
            "providers/Microsoft.Compute/virtualMachines/[^/]+"
        )

        args, _ = logger_mock.call_args
        self.assertTrue(re.match(expected_warning_regex, args[0]) is not None)

    @arm_template('vm.json')
    def test_tag_filter(self):
        policy = {
            'name': 'test-azure-metric',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'}],
            'actions': [
                {'type': 'tag',
                 'tag': 'Pythontest',
                 'value': 'ItWorks'}],
        }
        p = self.load_policy(policy)
        resources = p.run()

        policy = {
            'name': 'test-azure-metric',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'tag:Pythontest': 'present'}]
        }
        p = self.load_policy(policy)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        policy = {
            'name': 'test-azure-metric',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'tag:Pythontest': 'absent'}]
        }
        p = self.load_policy(policy)
        resources = p.run()
        self.assertEqual(len(resources), 0)

        policy = {
            'name': 'test-azure-metric',
            'resource': 'azure.vm',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'eq',
                 'value_type': 'normalize',
                 'value': 'cctestvm'},
                {'tag:Pythontest': 'ItWorks'}]
        }
        p = self.load_policy(policy)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    DAYS = 10

    @arm_template('vm.json')
    def test_mark_for_op(self):
        with patch('c7n_azure.utils.now') as utc_patch:
            utc_patch.return_value = self.get_test_date()

            policy = {
                'name': 'test-mark-for-op',
                'resource': 'azure.vm',
                'filters': [
                    {'type': 'value',
                     'key': 'name',
                     'op': 'eq',
                     'value_type': 'normalize',
                     'value': 'cctestvm'}],
                'actions': [
                    {'type': 'mark-for-op',
                     'op': 'stop',
                     'days': self.DAYS}
                ]
            }
            p = self.load_policy(policy)
            resources = p.run()
            self.assertEqual(len(resources), 1)

            policy = {
                'name': 'test-mark-for-op',
                'resource': 'azure.vm',
                'filters': [
                    {'type': 'value',
                     'key': 'name',
                     'op': 'eq',
                     'value_type': 'normalize',
                     'value': 'cctestvm'},
                    {'type': 'marked-for-op',
                     'op': 'stop'}]
            }
            p = self.load_policy(policy)
            resources = p.run()
            self.assertEqual(len(resources), 0)

            utc_patch.return_value = self.get_test_date() + datetime.timedelta(days=self.DAYS)
            policy = {
                'name': 'test-mark-for-op',
                'resource': 'azure.vm',
                'filters': [
                    {'type': 'value',
                     'key': 'name',
                     'op': 'eq',
                     'value_type': 'normalize',
                     'value': 'cctestvm'},
                    {'type': 'marked-for-op',
                     'op': 'stop'}]
            }
            p = self.load_policy(policy)
            resources = p.run()
            self.assertEqual(len(resources), 1)
