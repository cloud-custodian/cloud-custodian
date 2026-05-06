# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from ..azure_common import BaseTest, arm_template, cassette_name
from c7n.exceptions import PolicyValidationError


class AIFoundryProjectTest(BaseTest):

    def test_ai_foundry_project_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-ai-foundry-project',
                'resource': 'azure.ai-foundry-project'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('ai-foundry-project.json')
    @cassette_name('ai-foundry-projects-query')
    def test_ai_foundry_project_query(self):
        p = self.load_policy({
            'name': 'test-ai-foundry-project-query',
            'resource': 'azure.ai-foundry-project',
        })

        resources = p.run()
        self.assertGreaterEqual(len(resources), 1)
        self.assertIn('/projects/', resources[0].get('id', '').lower())

    @arm_template('ai-foundry-project.json')
    @cassette_name('ai-foundry-projects-filter')
    def test_ai_foundry_project_filter(self):
        p = self.load_policy({
            'name': 'test-ai-foundry-project-filter',
            'resource': 'azure.ai-foundry-project',
            'filters': [{
                'type': 'value',
                'key': 'id',
                'op': 'contains',
                'value': '/projects/cctest-aifoundry-project'
            }]
        })

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertIn('/projects/cctest-aifoundry-project', resources[0].get('id', '').lower())


class AIFoundryConnectionTest(BaseTest):

    def test_ai_foundry_connection_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-ai-foundry-connection',
                'resource': 'azure.ai-foundry-connection'
            }, validate=True)
            self.assertTrue(p)

    def test_ai_foundry_connection_tag_not_supported(self):
        with self.sign_out_patch():
            policy = {
                'name': 'test-ai-foundry-connection-tag',
                'resource': 'azure.ai-foundry-connection',
                'actions': [{'type': 'tag', 'tags': {'env': 'test'}}]
            }
            self.assertRaises(
                PolicyValidationError, self.load_policy, policy, validate=True
            )

    def test_ai_foundry_connection_update_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-ai-foundry-connection-update',
                'resource': 'azure.ai-foundry-connection',
                'actions': [{
                    'type': 'update',
                    'properties': {
                        'isSharedToAll': True
                    }
                }]
            }, validate=True)
            self.assertTrue(p)

    def test_ai_foundry_connection_update_invalid_field(self):
        with self.sign_out_patch():
            policy = {
                'name': 'test-ai-foundry-connection-update-invalid-field',
                'resource': 'azure.ai-foundry-connection',
                'actions': [{
                    'type': 'update',
                    'properties': {
                        'notWritableField': 'x'
                    }
                }]
            }
            self.assertRaises(
                PolicyValidationError, self.load_policy, policy, validate=True
            )

    def test_ai_foundry_connection_delete_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-ai-foundry-connection-delete',
                'resource': 'azure.ai-foundry-connection',
                'actions': [{'type': 'delete'}]
            }, validate=True)
            self.assertTrue(p)

    @arm_template('ai-foundry-connection.json')
    @cassette_name('ai-foundry-connections')
    def test_ai_foundry_connection_query(self):
        project_policy = self.load_policy({
            'name': 'test-ai-foundry-project-prereq',
            'resource': 'azure.ai-foundry-project',
        })

        projects = project_policy.run()
        self.assertGreaterEqual(len(projects), 1)

        p = self.load_policy({
            'name': 'test-ai-foundry-connection-query',
            'resource': 'azure.ai-foundry-connection',
        })

        resources = p.run()
        self.assertGreaterEqual(len(resources), 1)
        self.assertIn('/connections/', resources[0].get('id', '').lower())

    @arm_template('ai-foundry-connection.json')
    @cassette_name('ai-foundry-connections-filter')
    def test_ai_foundry_connection_filter(self):
        read_policy = self.load_policy({
            'name': 'test-ai-foundry-connection-read-for-filter',
            'resource': 'azure.ai-foundry-connection',
        })

        resources = read_policy.run()
        self.assertGreaterEqual(len(resources), 1)

        target_name = resources[0]['name']
        filter_policy = self.load_policy({
            'name': 'test-ai-foundry-connection-filter',
            'resource': 'azure.ai-foundry-connection',
            'filters': [{
                'type': 'value',
                'key': 'name',
                'op': 'eq',
                'value': target_name
            }]
        })

        filtered = filter_policy.run()
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['name'], target_name)

    @arm_template('ai-foundry-connection.json')
    @cassette_name('ai-foundry-connections-update')
    def test_ai_foundry_connection_update(self):
        read_policy = self.load_policy({
            'name': 'test-ai-foundry-connection-read-before-update',
            'resource': 'azure.ai-foundry-connection',
        })

        before = read_policy.run()
        self.assertEqual(len(before), 1)
        current = before[0].get('properties', {}).get('isSharedToAll', False)
        updated = not current

        update_policy = self.load_policy({
            'name': 'test-ai-foundry-connection-update',
            'resource': 'azure.ai-foundry-connection',
            'actions': [{
                'type': 'update',
                'properties': {
                    'isSharedToAll': updated
                }
            }]
        })

        update_policy.run()
        self.sleep_in_live_mode(10)

        after = read_policy.run()
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0].get('properties', {}).get('isSharedToAll'), updated)

    @arm_template('ai-foundry-connection.json')
    @cassette_name('ai-foundry-connections-delete')
    def test_z_ai_foundry_connection_delete(self):
        read_policy = self.load_policy({
            'name': 'test-ai-foundry-connection-read-before-delete',
            'resource': 'azure.ai-foundry-connection',
        })

        delete_policy = self.load_policy({
            'name': 'test-ai-foundry-connection-delete',
            'resource': 'azure.ai-foundry-connection',
            'actions': [{'type': 'delete'}],
        })

        resources = read_policy.run()
        self.assertEqual(len(resources), 1)
        delete_policy.resource_manager.actions[0].process(resources)
        self.sleep_in_live_mode(10)

        remaining = read_policy.run()
        self.assertEqual(len(remaining), 0)


class AIFoundryApplicationTest(BaseTest):
    def test_ai_foundry_application_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-ai-foundry-application',
                'resource': 'azure.ai-foundry-application'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('ai-foundry-application.json')
    @cassette_name('ai-foundry-applications')
    def test_ai_foundry_application_query(self):
        project_policy = self.load_policy({
            'name': 'test-ai-foundry-project-prereq',
            'resource': 'azure.ai-foundry-project',
        })

        projects = project_policy.run()
        self.assertGreaterEqual(len(projects), 1)

        p = self.load_policy({
            'name': 'test-ai-foundry-application-query',
            'resource': 'azure.ai-foundry-application',
        })

        resources = p.run()
        self.assertGreaterEqual(len(resources), 1)
        self.assertTrue(
            any(r.get('id', '').lower().endswith('/applications/cctest-aifoundry-application')
                for r in resources)
        )

    @arm_template('ai-foundry-application.json')
    @cassette_name('ai-foundry-applications-filter')
    def test_ai_foundry_application_filter_by_name(self):
        project_policy = self.load_policy({
            'name': 'test-ai-foundry-project-prereq-filter',
            'resource': 'azure.ai-foundry-project',
        })

        projects = project_policy.run()
        self.assertGreaterEqual(len(projects), 1)

        p = self.load_policy({
            'name': 'test-ai-foundry-application-filter-name',
            'resource': 'azure.ai-foundry-application',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'eq',
                    'value': 'cctest-aifoundry-application'
                }
            ]
        })

        resources = p.run()
        self.assertGreaterEqual(len(resources), 1)
        self.assertTrue(all(r.get('name') == 'cctest-aifoundry-application' for r in resources))


class AIFoundryAgentTest(BaseTest):

    def test_ai_foundry_agent_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-ai-foundry-agent',
                'resource': 'azure.ai-foundry-agent'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('ai-foundry-application.json')
    @cassette_name('ai-foundry-agents')
    def test_ai_foundry_agent_query(self):
        app_policy = self.load_policy({
            'name': 'test-ai-foundry-application-prereq',
            'resource': 'azure.ai-foundry-application',
        })

        applications = app_policy.run()
        self.assertGreaterEqual(len(applications), 1)

        p = self.load_policy({
            'name': 'test-ai-foundry-agent-query',
            'resource': 'azure.ai-foundry-agent',
        })

        resources = p.run()
        self.assertGreaterEqual(len(resources), 1)
        self.assertTrue(any('/agents/' in r.get('id', '').lower() for r in resources))

    @arm_template('ai-foundry-application.json')
    @cassette_name('ai-foundry-agents-filter')
    def test_ai_foundry_agent_filter_by_name(self):
        app_policy = self.load_policy({
            'name': 'test-ai-foundry-application-prereq-filter',
            'resource': 'azure.ai-foundry-application',
        })

        applications = app_policy.run()
        self.assertGreaterEqual(len(applications), 1)

        p = self.load_policy({
            'name': 'test-ai-foundry-agent-filter-name',
            'resource': 'azure.ai-foundry-agent',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value': 'cctest-aifoundry-agent-*'
                }
            ]
        })

        resources = p.run()
        self.assertGreaterEqual(len(resources), 1)
        self.assertTrue(
            all(r.get('name', '').startswith('cctest-aifoundry-agent-') for r in resources)
        )
