# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import os
import re
import pytest

from c7n.vendored.distutils.util import strtobool

try:
    from pytest_terraform.tf import LazyPluginCacheDir, LazyReplay
    from c7n.testing import TestUtils
    from c7n.config import Bag, Config
    from c7n.policy import ExecutionContext
    from c7n_azure.session import Session
except ImportError:
    # Fallback if pytest-terraform is not available
    class LazyReplay:
        pass

    class LazyPluginCacheDir:
        pass

    class TestUtils:
        pass


# If we have C7N_FUNCTIONAL make sure Replay is False otherwise enable Replay
LazyReplay.value = not strtobool(os.environ.get('C7N_FUNCTIONAL', 'no'))
LazyPluginCacheDir.value = '../.tfcache'


class TerraformAzureRewriteHooks:
    """Local pytest plugin for Azure terraform tests

    Work around to allow for dynamic registration of hooks based on plugin availability
    """
    def pytest_terraform_modify_state(self, tfstate):
        """Sanitize functional testing account data for Azure"""
        # Azure-specific sanitization - replace Azure GUIDs with placeholder
        # Azure GUID pattern
        azure_guid_pattern = (
            r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
            r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b'
        )
        tfstate.update(
            re.sub(
                azure_guid_pattern,
                '00000000-0000-0000-0000-000000000000',
                str(tfstate)
            )
        )


def pytest_configure(config):
    # Only register pytest-terraform hooks if the plugin is available
    if config.pluginmanager.hasplugin("terraform"):
        config.pluginmanager.register(TerraformAzureRewriteHooks())


class AzureTerraformTesting(TestUtils):
    """Pytest Azure Testing Fixture for Terraform tests"""

    def __init__(self, request):
        self.request = request
        # Set up Azure test context similar to BaseTest
        self.test_context = ExecutionContext(
            Session,
            Bag(name="terraform-test", provider_name='azure'),
            Config.empty()
        )


@pytest.fixture(scope='function')
def test(request):
    """Azure test fixture that provides Cloud Custodian testing utilities"""
    test_utils = AzureTerraformTesting(request)
    return test_utils
