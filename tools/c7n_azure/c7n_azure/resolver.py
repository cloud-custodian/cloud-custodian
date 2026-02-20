# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
import zlib

from c7n_azure.storage_utils import StorageUtilities, OldBlobServiceClient

log = logging.getLogger('custodian.azure.resolver')

# Use the same constant as core c7n for consistency
ZIP_OR_GZIP_HEADER_DETECT = zlib.MAX_WBITS | 32


def resolve_azure_blob(uri, session_factory, cache):
    """Resolve an azure:// URI to blob content.

    Args:
        uri: Azure blob URI in format azure://account.blob.core.windows.net/container/blob
        session_factory: Factory function that returns an Azure session
        cache: Cache instance for storing resolved content

    Returns:
        String content of the blob, decompressed if needed

    Raises:
        ResourceNotFoundError: If blob doesn't exist
        ClientAuthenticationError: If authentication fails
        HttpResponseError: For other Azure API errors
    """
    # Check cache first
    cached = cache.get(("azure-blob-resolver", uri))
    if cached is not None:
        log.debug(f"Returning cached content for {uri}")
        return cached

    # Parse the Azure URI
    storage = StorageUtilities.get_storage_from_uri(uri)

    # Get Azure session and credentials
    session = session_factory()
    credentials = session.get_credentials()

    # Create blob service client
    blob_service = OldBlobServiceClient(
        account_url=storage.account_url,
        credential=credentials
    )

    # Download blob content
    log.debug(f"Downloading blob from {uri}")
    blob_bytes = blob_service.get_blob_to_bytes(
        storage.container_name,
        storage.file_prefix
    )

    # Handle compression based on file extension (matches S3 behavior)
    blob_name = storage.file_prefix.lower()
    if blob_name.endswith(('.gz', '.zip', '.gzip')):
        log.debug(f"Decompressing blob {uri}")
        content = zlib.decompress(blob_bytes, ZIP_OR_GZIP_HEADER_DETECT).decode('utf-8')
    else:
        # Handle both bytes and string content
        if isinstance(blob_bytes, bytes):
            content = blob_bytes.decode('utf-8')
        else:
            content = blob_bytes

    # Cache the result
    cache.save(("azure-blob-resolver", uri), content)

    return content
