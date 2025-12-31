# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .azure_common import BaseTest, DEFAULT_SUBSCRIPTION_ID
from unittest.mock import patch
from c7n_azure.provider import Azure
from c7n.config import Config
from msrestazure.azure_cloud import (AZURE_CHINA_CLOUD, AZURE_GERMAN_CLOUD,
                                     AZURE_PUBLIC_CLOUD, AZURE_US_GOV_CLOUD)
import pytest


class ProviderTest(BaseTest):
    def test_initialize_default_account_id(self):
        # Patch get_subscription_id during provider initialization
        with patch('c7n_azure.session.Session.get_subscription_id',
                   return_value=DEFAULT_SUBSCRIPTION_ID):
            options = Config.empty()
            azure = Azure()
            azure.initialize(options)
            self.assertEqual(options['account_id'], DEFAULT_SUBSCRIPTION_ID)
            session = azure.get_session_factory(options)()

        self.assertEqual(DEFAULT_SUBSCRIPTION_ID, session.get_subscription_id())

    def test_initialize_custom_account_id(self):
        sample_account_id = "00000000-5106-4743-99b0-c129bfa71a47"
        options = Config.empty()
        options['account_id'] = sample_account_id
        azure = Azure()
        azure.initialize(options)
        self.assertEqual(options['account_id'], sample_account_id)

        session = azure.get_session_factory(options)()
        self.assertEqual(sample_account_id, session.get_subscription_id())

    def test_initialize_default_azure_cloud(self):
        with patch('c7n_azure.session.Session.get_subscription_id'):
            options = Config.empty()
            azure = Azure()
            azure.initialize(options)
            self.assertEqual(AZURE_PUBLIC_CLOUD, azure.cloud_endpoints)
            self.assertEqual(AZURE_PUBLIC_CLOUD.name, options['region'])
            session = azure.get_session_factory(options)()

        self.assertEqual(AZURE_PUBLIC_CLOUD.endpoints.active_directory_resource_id,
                         session.resource_endpoint)

    def test_initialize_azure_cloud(self):

        clouds = [AZURE_PUBLIC_CLOUD, AZURE_CHINA_CLOUD, AZURE_GERMAN_CLOUD, AZURE_US_GOV_CLOUD]
        with patch('c7n_azure.session.Session.get_subscription_id'):
            for cloud_endpoints in clouds:
                options = Config.empty(regions=[cloud_endpoints.name])
                azure = Azure()
                azure.initialize(options)
                self.assertEqual(cloud_endpoints, azure.cloud_endpoints)
                self.assertEqual(cloud_endpoints.name, options['region'])
                session = azure.get_session_factory(options)()
                self.assertEqual(cloud_endpoints.endpoints.active_directory_resource_id,
                         session.resource_endpoint)

    def test_exit_on_nonexistent_azure_cloud(self):
        with patch('c7n_azure.session.Session.get_subscription_id'):
            with pytest.raises(SystemExit) as exit:
                options = Config.empty(regions=['InvalidCloudName'])
                azure = Azure()
                azure.initialize(options)
                azure.get_session_factory(options)()

        self.assertEqual(SystemExit, exit.type)
        self.assertEqual(1, exit.value.code)
