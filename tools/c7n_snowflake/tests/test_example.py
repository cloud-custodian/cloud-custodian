# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json
import os
import pytest
from unittest.mock import patch

from c7n.config import Config
from c7n.testing import C7N_FUNCTIONAL


class TestSnowflakeVCRExample:
    """Example test class showing how to use the Snowflake VCR testing framework"""
    
    def test_basic_session_factory(self, test):
        """Test basic session factory creation with VCR"""
        # This test will record/replay Snowflake API interactions
        # Explicitly pass test class and method names to avoid stack inspection issues
        session_factory = test.snowflake_session_factory(
            test_class=self.__class__.__name__,
            test_case='test_basic_session_factory'
        )
        assert session_factory is not None
        assert hasattr(session_factory, '__call__')
    
    def test_session_factory_serialization(self, test):
        """Test that SessionFactory can be JSON serialized"""
        from c7n.utils import dumps
        
        # Create session factory
        session_factory = test.snowflake_session_factory(
            test_class=self.__class__.__name__,
            test_case='test_session_factory_serialization'
        )
        
        # Test that it can be JSON serialized (this was the failing point)
        serialized = dumps({'session_factory': session_factory})
        assert 'SnowflakeSessionFactory' in serialized
        
        # Parse it back to verify it's valid JSON
        data = json.loads(serialized)
        assert data['session_factory']['type'] == 'SnowflakeSessionFactory'
    
    @patch.dict(os.environ, {'SNOWFLAKE_ACCOUNT': 'test', 'SNOWFLAKE_USER': 'test', 'SNOWFLAKE_API_KEY': 'test'})
    def test_policy_loading_with_session_factory(self, test):
        """Test loading a policy with session factory without running it"""
        # Example policy configuration
        policy_config = {
            'name': 'test-warehouses',
            'resource': 'snowflake.warehouse',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'regex',
                 'value': 'TEST_.*'}
            ]
        }
        
        # Create policy with VCR session factory
        session_factory = test.snowflake_session_factory(
            test_class=self.__class__.__name__,
            test_case='test_policy_loading_with_session_factory'
        )
        
        # Load policy without running it
        policy = test.load_policy(policy_config, session_factory=session_factory)
        assert policy is not None
        assert policy.name == 'test-warehouses'
        assert policy.resource_type == 'snowflake.warehouse'
    
    @patch.dict(os.environ, {'SNOWFLAKE_ACCOUNT': 'test', 'SNOWFLAKE_USER': 'test', 'SNOWFLAKE_API_KEY': 'test'})
    def test_mocked_credentials(self, test):
        """Test with mocked credentials to verify VCR setup works"""
        session_factory = test.snowflake_session_factory(
            test_class=self.__class__.__name__,
            test_case='test_mocked_credentials'
        )
        
        # Verify that the session factory was created
        assert session_factory is not None
        
        # In a real test, this would make actual API calls that get recorded/replayed
        # For this example, we're just testing the VCR infrastructure setup
