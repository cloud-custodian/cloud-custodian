# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for Azure Blob Storage resolver with c7n core."""
import json
import pickle
from unittest.mock import Mock, patch, MagicMock

from c7n.config import Bag
from c7n.resolver import URIResolver, ValuesFrom


class FakeCache:
    """Test cache implementation for integration testing."""

    def __init__(self):
        self.state = {}

    def get(self, key):
        return self.state.get(pickle.dumps(key))

    def save(self, key, data):
        self.state[pickle.dumps(key)] = data

    def load(self):
        return True

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args, **kw):
        return


class TestAzureBlobResolverIntegration:
    """Integration tests verifying azure:// URLs work through c7n core."""

    def test_provider_registers_azure_scheme(self):
        """Test that importing the Azure provider registers the azure:// scheme."""
        # Force reimport to ensure registration happens
        import c7n_azure.provider  # noqa: F401
        from c7n.resolver import URIResolver

        # Verify azure scheme is registered
        assert 'azure' in URIResolver._uri_providers
        assert URIResolver._uri_providers['azure'] is not None

    @patch('c7n_azure.resolver.OldBlobServiceClient')
    def test_uri_resolver_handles_azure_urls(self, mock_blob_client):
        """Test that URIResolver can resolve azure:// URLs."""
        # Ensure provider is imported (registers the handler)
        import c7n_azure.provider  # noqa: F401

        # Setup mock
        json_content = json.dumps({"test": "data"})
        mock_client_instance = MagicMock()
        mock_client_instance.get_blob_to_bytes.return_value = json_content.encode('utf-8')
        mock_blob_client.return_value = mock_client_instance

        # Create mock session factory
        mock_session = Mock()
        mock_session.get_credentials.return_value = "fake_credentials"
        mock_session_factory = Mock(return_value=mock_session)

        # Create resolver and test
        cache = FakeCache()
        resolver = URIResolver(mock_session_factory, cache)
        uri = "azure://myaccount.blob.core.windows.net/mycontainer/test.json"

        result = resolver.resolve(uri, {})

        assert result == json_content
        assert mock_client_instance.get_blob_to_bytes.called

    @patch('c7n_azure.resolver.OldBlobServiceClient')
    def test_values_from_with_azure_blob(self, mock_blob_client):
        """Test ValuesFrom filter with azure:// URL."""
        # Ensure provider is imported
        import c7n_azure.provider  # noqa: F401

        # Setup mock - return a list of values
        values_data = json.dumps(["value1", "value2", "value3"])
        mock_client_instance = MagicMock()
        mock_client_instance.get_blob_to_bytes.return_value = values_data.encode('utf-8')
        mock_blob_client.return_value = mock_client_instance

        # Create mock session factory
        mock_session = Mock()
        mock_session.get_credentials.return_value = "fake_credentials"
        mock_session_factory = Mock(return_value=mock_session)

        # Create ValuesFrom instance
        cache = FakeCache()
        manager = Bag(
            session_factory=mock_session_factory,
            _cache=cache,
            config=Bag(account_id="test-account", region="us-east-1")
        )

        values_from = ValuesFrom({
            'url': 'azure://myaccount.blob.core.windows.net/mycontainer/values.json',
            'format': 'json'
        }, manager)

        # Get values
        result = values_from.get_values()

        # Verify
        assert set(result) == {"value1", "value2", "value3"}
        assert mock_client_instance.get_blob_to_bytes.called

    @patch('c7n_azure.resolver.OldBlobServiceClient')
    def test_values_from_with_jmespath_expression(self, mock_blob_client):
        """Test ValuesFrom with JMESPath expression on Azure blob data."""
        # Ensure provider is imported
        import c7n_azure.provider  # noqa: F401

        # Setup mock - return complex JSON structure
        complex_data = json.dumps({
            "resources": [
                {"name": "vm1", "type": "VirtualMachine"},
                {"name": "vm2", "type": "VirtualMachine"},
                {"name": "db1", "type": "Database"}
            ]
        })
        mock_client_instance = MagicMock()
        mock_client_instance.get_blob_to_bytes.return_value = complex_data.encode('utf-8')
        mock_blob_client.return_value = mock_client_instance

        # Create mock session factory
        mock_session = Mock()
        mock_session.get_credentials.return_value = "fake_credentials"
        mock_session_factory = Mock(return_value=mock_session)

        # Create ValuesFrom instance with JMESPath expression
        cache = FakeCache()
        manager = Bag(
            session_factory=mock_session_factory,
            _cache=cache,
            config=Bag(account_id="test-account", region="us-east-1")
        )

        values_from = ValuesFrom({
            'url': 'azure://myaccount.blob.core.windows.net/mycontainer/resources.json',
            'format': 'json',
            'expr': 'resources[?type==`VirtualMachine`].name'
        }, manager)

        # Get values
        result = values_from.get_values()

        # Verify - should only get VM names
        assert set(result) == {"vm1", "vm2"}
        assert mock_client_instance.get_blob_to_bytes.called

    @patch('c7n_azure.resolver.OldBlobServiceClient')
    def test_values_from_with_csv_format(self, mock_blob_client):
        """Test ValuesFrom with CSV format from Azure blob."""
        # Ensure provider is imported
        import c7n_azure.provider  # noqa: F401

        # Setup mock - return CSV data without header row
        csv_data = "resource1\nresource2\nresource3"
        mock_client_instance = MagicMock()
        mock_client_instance.get_blob_to_bytes.return_value = csv_data.encode('utf-8')
        mock_blob_client.return_value = mock_client_instance

        # Create mock session factory
        mock_session = Mock()
        mock_session.get_credentials.return_value = "fake_credentials"
        mock_session_factory = Mock(return_value=mock_session)

        # Create ValuesFrom instance for CSV (single column, no header)
        cache = FakeCache()
        manager = Bag(
            session_factory=mock_session_factory,
            _cache=cache,
            config=Bag(account_id="test-account", region="us-east-1")
        )

        values_from = ValuesFrom({
            'url': 'azure://myaccount.blob.core.windows.net/mycontainer/data.csv',
            'format': 'csv',
            'expr': 0  # Get first (and only) column
        }, manager)

        # Get values
        result = values_from.get_values()

        # Verify - should get all values from column 0
        assert set(result) == {"resource1", "resource2", "resource3"}
        assert mock_client_instance.get_blob_to_bytes.called

    @patch('c7n_azure.resolver.OldBlobServiceClient')
    def test_values_from_caching_across_calls(self, mock_blob_client):
        """Test that caching works properly across multiple ValuesFrom calls."""
        # Ensure provider is imported
        import c7n_azure.provider  # noqa: F401

        # Setup mock
        values_data = json.dumps(["cached1", "cached2"])
        mock_client_instance = MagicMock()
        mock_client_instance.get_blob_to_bytes.return_value = values_data.encode('utf-8')
        mock_blob_client.return_value = mock_client_instance

        # Create mock session factory
        mock_session = Mock()
        mock_session.get_credentials.return_value = "fake_credentials"
        mock_session_factory = Mock(return_value=mock_session)

        # Shared cache
        cache = FakeCache()
        manager = Bag(
            session_factory=mock_session_factory,
            _cache=cache,
            config=Bag(account_id="test-account", region="us-east-1")
        )

        # First ValuesFrom call
        values_from1 = ValuesFrom({
            'url': 'azure://myaccount.blob.core.windows.net/mycontainer/cached.json',
            'format': 'json'
        }, manager)
        result1 = values_from1.get_values()

        # Second ValuesFrom call with same URL
        values_from2 = ValuesFrom({
            'url': 'azure://myaccount.blob.core.windows.net/mycontainer/cached.json',
            'format': 'json'
        }, manager)
        result2 = values_from2.get_values()

        # Both should return same values
        assert result1 == result2
        # Blob client should only be called once due to caching
        assert mock_client_instance.get_blob_to_bytes.call_count == 1

    def test_azure_scheme_handler_signature(self):
        """Test that the registered Azure handler has the correct signature."""
        # Ensure provider is imported
        import c7n_azure.provider  # noqa: F401
        from c7n.resolver import URIResolver

        handler = URIResolver._uri_providers.get('azure')
        assert handler is not None

        # Verify it's our resolve_azure_blob function
        from c7n_azure.resolver import resolve_azure_blob
        assert handler == resolve_azure_blob
