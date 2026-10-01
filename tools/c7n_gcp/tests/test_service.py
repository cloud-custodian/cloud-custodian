# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import time

from gcp_common import BaseTest


class ServiceTest(BaseTest):

    def test_service_query(self):
        factory = self.replay_flight_data('service-query')
        p = self.load_policy(
            {'name': 'all-services',
             'resource': 'gcp.service'},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 16)
        self.assertEqual(
            p.resource_manager.get_urns(resources),
            [
                "gcp:serviceusage::cloud-custodian:service/bigquery.googleapis.com",
                "gcp:serviceusage::cloud-custodian:service/bigquerystorage.googleapis.com",
                "gcp:serviceusage::cloud-custodian:service/cloudapis.googleapis.com",
                "gcp:serviceusage::cloud-custodian:service/clouddebugger.googleapis.com",
                "gcp:serviceusage::cloud-custodian:service/cloudtrace.googleapis.com",
                "gcp:serviceusage::cloud-custodian:service/datastore.googleapis.com",
                "gcp:serviceusage::cloud-custodian:service/logging.googleapis.com",
                "gcp:serviceusage::cloud-custodian:service/monitoring.googleapis.com",
                "gcp:serviceusage::cloud-custodian:service/pubsub.googleapis.com",
                "gcp:serviceusage::cloud-custodian:service/servicemanagement.googleapis.com",
                "gcp:serviceusage::cloud-custodian:service/serviceusage.googleapis.com",
                "gcp:serviceusage::cloud-custodian:service/source.googleapis.com",
                "gcp:serviceusage::cloud-custodian:service/sql-component.googleapis.com",
                "gcp:serviceusage::cloud-custodian:service/storage-api.googleapis.com",
                "gcp:serviceusage::cloud-custodian:service/storage-component.googleapis.com",
                "gcp:serviceusage::cloud-custodian:service/storage.googleapis.com",
            ],
        )

    def test_service_query_params(self):
        p = self.load_policy({'name': 'enabled-services', 'resource': 'gcp.service'})
        self.assertEqual(p.resource_manager.get_resource_query(), {'filter': 'state:ENABLED'})
        self.assertEqual(p.resource_manager.get_permissions(), ('serviceusage.services.list',))
        p = self.load_policy(
            {'name': 'named-services',
             'resource': 'gcp.service',
             'query': [{'names': ['cloudasset.googleapis.com']}]})
        self.assertEqual(
            p.resource_manager.get_resource_query(),
            {'names': ['cloudasset.googleapis.com']})
        self.assertEqual(p.resource_manager.get_permissions(), ('serviceusage.services.get',))

    def test_service_query_names(self):
        # Services are fetched whatever their state, which depends on the
        # project, so only check that each one has a valid state.
        factory = self.replay_flight_data('service-query-names')
        p = self.load_policy(
            {'name': 'named-services',
             'resource': 'gcp.service',
             'query': [{'names': [
                 'cloudasset.googleapis.com', 'serviceusage.googleapis.com']}]},
            session_factory=factory)
        resources = {r['config']['name']: r for r in p.run()}
        self.assertEqual(
            set(resources), {'cloudasset.googleapis.com', 'serviceusage.googleapis.com'})
        for r in resources.values():
            self.assertIn(r['state'], ('ENABLED', 'DISABLED'))

    def wait_for_state(self, manager, name, state):
        # enable/disable return long running operations, poll until the
        # service reaches the expected state.
        for _ in range(30):
            service = manager.get_resource({'resourceName': name})
            if service['state'] == state:
                break
            if self.recording:
                time.sleep(5)
        return service

    def test_service_enable_disable(self):
        # Flip the service to the opposite state and back, so both actions
        # are exercised and the project is left as it was found.
        factory = self.replay_flight_data('service-enable-disable')
        p = self.load_policy(
            {'name': 'service-toggle',
             'resource': 'gcp.service',
             'actions': ['enable', 'disable']},
            session_factory=factory)
        manager = p.resource_manager
        enable, disable = manager.actions
        self.assertEqual(enable.get_permissions(), ('serviceusage.services.enable',))

        name = 'projects/{}/services/cloudasset.googleapis.com'.format(
            factory().get_default_project())
        original = manager.get_resource({'resourceName': name})
        if original['state'] == 'ENABLED':
            flip, restore, flipped = disable, enable, 'DISABLED'
        else:
            flip, restore, flipped = enable, disable, 'ENABLED'

        try:
            flip.process([original])
            self.assertEqual(self.wait_for_state(manager, name, flipped)['state'], flipped)
        finally:
            restore.process([original])
        self.assertEqual(
            self.wait_for_state(manager, name, original['state'])['state'],
            original['state'])

    def test_service_disable(self):
        factory = self.replay_flight_data('service-disable')
        p = self.load_policy(
            {'name': 'disable-service',
             'resource': 'gcp.service',
             'filters': [
                 {'config.name': 'deploymentmanager.googleapis.com'}],
             'actions': ['disable']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertJmes('config.name', resources[0], 'deploymentmanager.googleapis.com')

    def test_service_get(self):
        factory = self.replay_flight_data('service-get')
        p = self.load_policy(
            {'name': 'one-service', 'resource': 'gcp.service'},
            session_factory=factory)
        service = p.resource_manager.get_resource(
            {'resourceName': 'projects/stacklet-sam/services/deploymentmanager.googleapis.com'})
        self.assertJmes('config.name', service, 'deploymentmanager.googleapis.com')
        self.assertEqual(
            p.resource_manager.get_urns([service]),
            [
                "gcp:serviceusage::cloud-custodian:service/deploymentmanager.googleapis.com",
            ],
        )
