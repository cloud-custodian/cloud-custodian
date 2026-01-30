# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import gzip
import json
import pickle
from io import BytesIO
from unittest.mock import Mock, patch, MagicMock

import pytest

from c7n_azure.storage_utils import StorageUtilities


class FakeCache:
    """Test cache implementation for verifying caching behavior."""

    def __init__(self):
        self.state = {}
        self.gets = 0
        self.saves = 0

    def get(self, key):
        self.gets += 1
        return self.state.get(pickle.dumps(key))

    def save(self, key, data):
        self.saves += 1
        self.state[pickle.dumps(key)] = data

    def load(self):
        return True

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args, **kw):
        return


class TestAzureBlobResolver:
    """Test suite for Azure Blob Storage resolver functionality."""

    def test_parse_basic_azure_url(self):
        """Test parsing a basic azure:// URL."""
        uri = "azure://myaccount.blob.core.windows.net/mycontainer/blob.json"
        storage = StorageUtilities.get_storage_from_uri(uri)

        assert storage.account_url == "https://myaccount.blob.core.windows.net"
        assert storage.container_name == "mycontainer"
        assert storage.file_prefix == "blob.json"

    def test_parse_azure_url_with_nested_path(self):
        """Test parsing azure:// URL with nested path structure."""
        uri = "azure://myaccount.blob.core.windows.net/mycontainer/path/to/blob.json"
        storage = StorageUtilities.get_storage_from_uri(uri)

        assert storage.account_url == "https://myaccount.blob.core.windows.net"
        assert storage.container_name == "mycontainer"
        assert storage.file_prefix == "path/to/blob.json"

    def test_parse_azure_url_with_gz_extension(self):
        """Test parsing azure:// URL with .gz extension."""
        uri = "azure://myaccount.blob.core.windows.net/mycontainer/data.json.gz"
        storage = StorageUtilities.get_storage_from_uri(uri)

        assert storage.account_url == "https://myaccount.blob.core.windows.net"
        assert storage.container_name == "mycontainer"
        assert storage.file_prefix == "data.json.gz"

    def test_parse_azure_url_without_blob_path(self):
        """Test parsing azure:// URL with only container (no blob path)."""
        uri = "azure://myaccount.blob.core.windows.net/mycontainer"
        storage = StorageUtilities.get_storage_from_uri(uri)

        assert storage.account_url == "https://myaccount.blob.core.windows.net"
        assert storage.container_name == "mycontainer"
        assert storage.file_prefix == ""

    @patch('c7n_azure.resolver.OldBlobServiceClient')
    def test_resolve_json_blob(self, mock_blob_client):
        """Test resolving JSON content from Azure blob."""
        from c7n_azure.resolver import resolve_azure_blob

        # Setup mock
        json_content = json.dumps({"test": "data"})
        mock_client_instance = MagicMock()
        mock_client_instance.get_blob_to_bytes.return_value = json_content.encode('utf-8')
        mock_blob_client.return_value = mock_client_instance

        # Create mock session factory
        mock_session = Mock()
        mock_session.get_credentials.return_value = "fake_credentials"
        mock_session_factory = Mock(return_value=mock_session)

        # Create cache
        cache = FakeCache()

        # Test resolve
        uri = "azure://myaccount.blob.core.windows.net/mycontainer/test.json"
        result = resolve_azure_blob(uri, mock_session_factory, cache)

        assert result == json_content
        assert mock_client_instance.get_blob_to_bytes.called
        # Verify cache was used
        assert cache.saves == 1

    @patch('c7n_azure.resolver.OldBlobServiceClient')
    def test_resolve_csv_blob(self, mock_blob_client):
        """Test resolving CSV content from Azure blob."""
        from c7n_azure.resolver import resolve_azure_blob

        # Setup mock
        csv_content = "name,value\ntest,123"
        mock_client_instance = MagicMock()
        mock_client_instance.get_blob_to_bytes.return_value = csv_content.encode('utf-8')
        mock_blob_client.return_value = mock_client_instance

        # Create mock session factory
        mock_session = Mock()
        mock_session.get_credentials.return_value = "fake_credentials"
        mock_session_factory = Mock(return_value=mock_session)

        # Create cache
        cache = FakeCache()

        # Test resolve
        uri = "azure://myaccount.blob.core.windows.net/mycontainer/data.csv"
        result = resolve_azure_blob(uri, mock_session_factory, cache)

        assert result == csv_content
        assert mock_client_instance.get_blob_to_bytes.called

    @patch('c7n_azure.resolver.OldBlobServiceClient')
    def test_resolve_txt_blob(self, mock_blob_client):
        """Test resolving plain text content from Azure blob."""
        from c7n_azure.resolver import resolve_azure_blob

        # Setup mock
        txt_content = "line1\nline2\nline3"
        mock_client_instance = MagicMock()
        mock_client_instance.get_blob_to_bytes.return_value = txt_content.encode('utf-8')
        mock_blob_client.return_value = mock_client_instance

        # Create mock session factory
        mock_session = Mock()
        mock_session.get_credentials.return_value = "fake_credentials"
        mock_session_factory = Mock(return_value=mock_session)

        # Create cache
        cache = FakeCache()

        # Test resolve
        uri = "azure://myaccount.blob.core.windows.net/mycontainer/list.txt"
        result = resolve_azure_blob(uri, mock_session_factory, cache)

        assert result == txt_content
        assert mock_client_instance.get_blob_to_bytes.called

    @patch('c7n_azure.resolver.OldBlobServiceClient')
    def test_resolve_gzip_compressed_blob(self, mock_blob_client):
        """Test resolving gzip-compressed blob (file extension based)."""
        from c7n_azure.resolver import resolve_azure_blob

        # Setup mock - create gzip compressed content
        original_content = json.dumps({"compressed": "data"})
        compressed_buffer = BytesIO()
        with gzip.GzipFile(fileobj=compressed_buffer, mode='wb') as gz:
            gz.write(original_content.encode('utf-8'))
        compressed_content = compressed_buffer.getvalue()

        mock_client_instance = MagicMock()
        mock_client_instance.get_blob_to_bytes.return_value = compressed_content
        mock_blob_client.return_value = mock_client_instance

        # Create mock session factory
        mock_session = Mock()
        mock_session.get_credentials.return_value = "fake_credentials"
        mock_session_factory = Mock(return_value=mock_session)

        # Create cache
        cache = FakeCache()

        # Test resolve with .gz extension
        uri = "azure://myaccount.blob.core.windows.net/mycontainer/data.json.gz"
        result = resolve_azure_blob(uri, mock_session_factory, cache)

        assert result == original_content
        assert mock_client_instance.get_blob_to_bytes.called

    @patch('c7n_azure.resolver.OldBlobServiceClient')
    def test_resolve_zip_compressed_blob(self, mock_blob_client):
        """Test resolving deflate-compressed blob with .zip extension.

        Note: This tests deflate compression (like gzip but with .zip extension),
        not full ZIP archives. ZIP archives are not supported by zlib.decompress.
        """
        from c7n_azure.resolver import resolve_azure_blob

        # Setup mock - create deflate compressed content (same as gzip)
        # This matches what S3 resolver can handle with .zip extension
        original_content = "test data for zip"
        compressed_buffer = BytesIO()
        with gzip.GzipFile(fileobj=compressed_buffer, mode='wb') as gz:
            gz.write(original_content.encode('utf-8'))
        compressed_content = compressed_buffer.getvalue()

        mock_client_instance = MagicMock()
        mock_client_instance.get_blob_to_bytes.return_value = compressed_content
        mock_blob_client.return_value = mock_client_instance

        # Create mock session factory
        mock_session = Mock()
        mock_session.get_credentials.return_value = "fake_credentials"
        mock_session_factory = Mock(return_value=mock_session)

        # Create cache
        cache = FakeCache()

        # Test resolve with .zip extension (deflate-compressed, not ZIP archive)
        uri = "azure://myaccount.blob.core.windows.net/mycontainer/data.zip"
        result = resolve_azure_blob(uri, mock_session_factory, cache)

        # We expect the decompressed content
        assert result == original_content
        assert mock_client_instance.get_blob_to_bytes.called

    @patch('c7n_azure.resolver.OldBlobServiceClient')
    def test_resolve_gzip_extension_variant(self, mock_blob_client):
        """Test resolving blob with .gzip extension (variant)."""
        from c7n_azure.resolver import resolve_azure_blob

        # Setup mock
        original_content = "gzip variant test"
        compressed_buffer = BytesIO()
        with gzip.GzipFile(fileobj=compressed_buffer, mode='wb') as gz:
            gz.write(original_content.encode('utf-8'))
        compressed_content = compressed_buffer.getvalue()

        mock_client_instance = MagicMock()
        mock_client_instance.get_blob_to_bytes.return_value = compressed_content
        mock_blob_client.return_value = mock_client_instance

        # Create mock session factory
        mock_session = Mock()
        mock_session.get_credentials.return_value = "fake_credentials"
        mock_session_factory = Mock(return_value=mock_session)

        # Create cache
        cache = FakeCache()

        # Test resolve with .gzip extension
        uri = "azure://myaccount.blob.core.windows.net/mycontainer/data.gzip"
        result = resolve_azure_blob(uri, mock_session_factory, cache)

        assert result == original_content
        assert mock_client_instance.get_blob_to_bytes.called

    @patch('c7n_azure.resolver.OldBlobServiceClient')
    def test_caching_behavior(self, mock_blob_client):
        """Test that caching works correctly for Azure blob content."""
        from c7n_azure.resolver import resolve_azure_blob

        # Setup mock
        content = "cached content"
        mock_client_instance = MagicMock()
        mock_client_instance.get_blob_to_bytes.return_value = content.encode('utf-8')
        mock_blob_client.return_value = mock_client_instance

        # Create mock session factory
        mock_session = Mock()
        mock_session.get_credentials.return_value = "fake_credentials"
        mock_session_factory = Mock(return_value=mock_session)

        # Create cache
        cache = FakeCache()

        # First resolve - should hit Azure and cache
        uri = "azure://myaccount.blob.core.windows.net/mycontainer/cached.txt"
        result1 = resolve_azure_blob(uri, mock_session_factory, cache)

        assert result1 == content
        assert cache.saves == 1
        assert mock_client_instance.get_blob_to_bytes.call_count == 1

        # Second resolve - should use cache, not hit Azure again
        result2 = resolve_azure_blob(uri, mock_session_factory, cache)

        assert result2 == content
        # Cache should have been checked but not saved again
        assert cache.gets == 2  # Once for each call
        # Blob client should not be called again
        assert mock_client_instance.get_blob_to_bytes.call_count == 1

    @patch('c7n_azure.resolver.OldBlobServiceClient')
    def test_blob_not_found_error(self, mock_blob_client):
        """Test handling of blob not found (404) errors."""
        from c7n_azure.resolver import resolve_azure_blob
        from azure.core.exceptions import ResourceNotFoundError

        # Setup mock to raise ResourceNotFoundError
        mock_client_instance = MagicMock()
        mock_client_instance.get_blob_to_bytes.side_effect = ResourceNotFoundError("Blob not found")
        mock_blob_client.return_value = mock_client_instance

        # Create mock session factory
        mock_session = Mock()
        mock_session.get_credentials.return_value = "fake_credentials"
        mock_session_factory = Mock(return_value=mock_session)

        # Create cache
        cache = FakeCache()

        # Test that appropriate error is raised
        uri = "azure://myaccount.blob.core.windows.net/mycontainer/missing.json"
        with pytest.raises(ResourceNotFoundError):
            resolve_azure_blob(uri, mock_session_factory, cache)

    @patch('c7n_azure.resolver.OldBlobServiceClient')
    def test_authentication_error(self, mock_blob_client):
        """Test handling of authentication (403) errors."""
        from c7n_azure.resolver import resolve_azure_blob
        from azure.core.exceptions import ClientAuthenticationError

        # Setup mock to raise authentication error
        mock_client_instance = MagicMock()
        mock_client_instance.get_blob_to_bytes.side_effect = ClientAuthenticationError(
            "Authentication failed"
        )
        mock_blob_client.return_value = mock_client_instance

        # Create mock session factory
        mock_session = Mock()
        mock_session.get_credentials.return_value = "fake_credentials"
        mock_session_factory = Mock(return_value=mock_session)

        # Create cache
        cache = FakeCache()

        # Test that appropriate error is raised
        uri = "azure://myaccount.blob.core.windows.net/mycontainer/protected.json"
        with pytest.raises(ClientAuthenticationError):
            resolve_azure_blob(uri, mock_session_factory, cache)

    @patch('c7n_azure.resolver.OldBlobServiceClient')
    def test_permission_denied_error(self, mock_blob_client):
        """Test handling of permission denied errors."""
        from c7n_azure.resolver import resolve_azure_blob
        from azure.core.exceptions import HttpResponseError

        # Setup mock to raise permission error (403)
        mock_client_instance = MagicMock()
        error = HttpResponseError("Access denied")
        error.status_code = 403
        mock_client_instance.get_blob_to_bytes.side_effect = error
        mock_blob_client.return_value = mock_client_instance

        # Create mock session factory
        mock_session = Mock()
        mock_session.get_credentials.return_value = "fake_credentials"
        mock_session_factory = Mock(return_value=mock_session)

        # Create cache
        cache = FakeCache()

        # Test that appropriate error is raised
        uri = "azure://myaccount.blob.core.windows.net/mycontainer/restricted.json"
        with pytest.raises(HttpResponseError):
            resolve_azure_blob(uri, mock_session_factory, cache)

    def test_invalid_url_missing_container(self):
        """Test that URLs without a container path are handled."""
        # This should work - container name would be empty string
        uri = "azure://myaccount.blob.core.windows.net/"
        storage = StorageUtilities.get_storage_from_uri(uri)

        assert storage.account_url == "https://myaccount.blob.core.windows.net"
        assert storage.container_name == ""
        assert storage.file_prefix == ""

    def test_session_credentials_usage(self):
        """Test that session credentials are properly obtained and used."""
        from c7n_azure.resolver import resolve_azure_blob

        with patch('c7n_azure.resolver.OldBlobServiceClient') as mock_blob_client:
            # Setup mock
            content = "test content"
            mock_client_instance = MagicMock()
            mock_client_instance.get_blob_to_bytes.return_value = content.encode('utf-8')
            mock_blob_client.return_value = mock_client_instance

            # Create mock session factory
            mock_credentials = Mock()
            mock_session = Mock()
            mock_session.get_credentials.return_value = mock_credentials
            mock_session_factory = Mock(return_value=mock_session)

            # Create cache
            cache = FakeCache()

            # Test resolve
            uri = "azure://myaccount.blob.core.windows.net/mycontainer/test.txt"
            resolve_azure_blob(uri, mock_session_factory, cache)

            # Verify session factory was called
            mock_session_factory.assert_called_once()
            # Verify get_credentials was called
            mock_session.get_credentials.assert_called_once()
            # Verify BlobServiceClient was created with correct params
            mock_blob_client.assert_called_once_with(
                account_url="https://myaccount.blob.core.windows.net",
                credential=mock_credentials
            )
