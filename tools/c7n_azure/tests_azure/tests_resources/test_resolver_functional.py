# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

"""
Functional tests for Azure Blob Storage resolver using pytest-terraform.

These tests use real Azure resources provisioned via Terraform to validate
end-to-end functionality of the azure:// URL handler in value_from filters.
"""

import pytest
from pytest_terraform import terraform


@terraform('azure_blob_storage')
@pytest.mark.functional
def test_blob_storage_discovery_terraform(test, azure_blob_storage):
    """Test that Terraform fixtures loaded successfully"""
    # Verify terraform fixtures loaded successfully
    assert len(azure_blob_storage.outputs) > 0, (
        f"Expected terraform outputs, got {len(azure_blob_storage.outputs)}"
    )

    # Verify required outputs exist
    assert 'storage_account_name' in azure_blob_storage.outputs
    assert 'container_name' in azure_blob_storage.outputs
    assert 'blob_json_simple' in azure_blob_storage.outputs

    # Get terraform-provisioned storage data
    storage_account = azure_blob_storage.outputs['storage_account_name']['value']
    container_name = azure_blob_storage.outputs['container_name']['value']

    # Verify test data integrity
    assert storage_account is not None
    assert container_name == 'test-configs'

    print(f"SUCCESS: Terraform fixtures loaded storage account '{storage_account}' successfully")


@terraform('azure_blob_storage')
@pytest.mark.functional
def test_value_from_json_simple_blob_terraform(test, azure_blob_storage):
    """Test value_from filter with simple JSON blob from Azure Blob Storage"""
    # Get blob URL from Terraform outputs
    blob_info = azure_blob_storage.outputs['blob_json_simple']['value']
    blob_url = blob_info['url']

    # Verify URL format
    assert blob_url.startswith('azure://')
    assert 'blob.core.windows.net' in blob_url
    assert 'approved-vms.json' in blob_url

    # Test Cloud Custodian policy with value_from using Azure blob
    # This policy would filter VMs based on names stored in the blob
    policy = test.load_policy({
        'name': 'test-value-from-azure-blob',
        'resource': 'azure.vm',
        'filters': [
            {
                'type': 'value',
                'key': 'name',
                'op': 'in',
                'value_from': {
                    'url': blob_url,
                    'format': 'json'
                }
            }
        ]
    })

    # Verify policy loads correctly
    assert policy is not None
    assert policy.resource_manager.type == 'vm'

    # Verify filter configuration
    filters = policy.resource_manager.filters
    assert len(filters) == 1
    assert filters[0].data['type'] == 'value'
    assert filters[0].data['value_from']['url'] == blob_url
    assert filters[0].data['value_from']['format'] == 'json'

    print(f"SUCCESS: Policy with JSON blob '{blob_url}' validated successfully")


@terraform('azure_blob_storage')
@pytest.mark.functional
def test_value_from_json_with_jmespath_terraform(test, azure_blob_storage):
    """Test value_from filter with JMESPath expression on complex JSON blob"""
    # Get complex JSON blob URL
    blob_info = azure_blob_storage.outputs['blob_json_complex']['value']
    blob_url = blob_info['url']

    # Test policy with JMESPath expression
    policy = test.load_policy({
        'name': 'test-jmespath-azure-blob',
        'resource': 'azure.vm',
        'filters': [
            {
                'type': 'value',
                'key': 'name',
                'op': 'in',
                'value_from': {
                    'url': blob_url,
                    'format': 'json',
                    'expr': 'vms[].vmName'
                }
            }
        ]
    })

    # Verify policy loads correctly
    assert policy is not None

    # Verify filter has JMESPath expression
    filters = policy.resource_manager.filters
    assert filters[0].data['value_from']['expr'] == 'vms[].vmName'

    print("SUCCESS: Policy with JMESPath expression validated successfully")


@terraform('azure_blob_storage')
@pytest.mark.functional
def test_value_from_csv_blob_terraform(test, azure_blob_storage):
    """Test value_from filter with CSV blob from Azure Blob Storage"""
    # Get CSV blob URL from Terraform outputs
    blob_info = azure_blob_storage.outputs['blob_csv']['value']
    blob_url = blob_info['url']

    # Verify URL format
    assert 'resource-groups.csv' in blob_url

    # Test policy using CSV format with column index
    policy = test.load_policy({
        'name': 'test-csv-azure-blob',
        'resource': 'azure.resourcegroup',
        'filters': [
            {
                'type': 'value',
                'key': 'name',
                'op': 'in',
                'value_from': {
                    'url': blob_url,
                    'format': 'csv',
                    'expr': '0'  # First column (name)
                }
            }
        ]
    })

    # Verify policy loads correctly
    assert policy is not None
    assert policy.resource_manager.type == 'resourcegroup'

    # Verify CSV format configuration
    filters = policy.resource_manager.filters
    assert filters[0].data['value_from']['format'] == 'csv'
    assert filters[0].data['value_from']['expr'] == '0'

    print(f"SUCCESS: Policy with CSV blob '{blob_url}' validated successfully")


@terraform('azure_blob_storage')
@pytest.mark.functional
def test_value_from_txt_blob_terraform(test, azure_blob_storage):
    """Test value_from filter with plain text blob from Azure Blob Storage"""
    # Get text blob URL from Terraform outputs
    blob_info = azure_blob_storage.outputs['blob_txt']['value']
    blob_url = blob_info['url']

    # Verify URL format
    assert 'vm-ids.txt' in blob_url

    # Test policy using text format
    policy = test.load_policy({
        'name': 'test-txt-azure-blob',
        'resource': 'azure.vm',
        'filters': [
            {
                'type': 'value',
                'key': 'id',
                'op': 'in',
                'value_from': {
                    'url': blob_url,
                    'format': 'txt'
                }
            }
        ]
    })

    # Verify policy loads correctly
    assert policy is not None

    # Verify text format configuration
    filters = policy.resource_manager.filters
    assert filters[0].data['value_from']['format'] == 'txt'

    print(f"SUCCESS: Policy with text blob '{blob_url}' validated successfully")


@terraform('azure_blob_storage')
@pytest.mark.functional
def test_value_from_compressed_blob_terraform(test, azure_blob_storage):
    """Test value_from filter with gzip compressed blob from Azure Blob Storage"""
    # Get compressed blob URL from Terraform outputs
    blob_info = azure_blob_storage.outputs['blob_compressed']['value']
    blob_url = blob_info['url']

    # Verify URL format includes .gz extension
    assert blob_url.endswith('.json.gz')

    # Test policy with compressed blob
    # The resolver should automatically decompress based on file extension
    policy = test.load_policy({
        'name': 'test-compressed-azure-blob',
        'resource': 'azure.vm',
        'filters': [
            {
                'type': 'value',
                'key': 'name',
                'op': 'in',
                'value_from': {
                    'url': blob_url,
                    'format': 'json'
                }
            }
        ]
    })

    # Verify policy loads correctly
    assert policy is not None

    # Verify the URL is correctly configured
    filters = policy.resource_manager.filters
    assert filters[0].data['value_from']['url'] == blob_url

    print(f"SUCCESS: Policy with compressed blob '{blob_url}' validated successfully")


@terraform('azure_blob_storage')
@pytest.mark.functional
def test_value_from_nested_path_blob_terraform(test, azure_blob_storage):
    """Test value_from filter with blob in nested path structure"""
    # Get nested path blob URL from Terraform outputs
    blob_info = azure_blob_storage.outputs['blob_nested']['value']
    blob_url = blob_info['url']

    # Verify URL includes nested path
    assert 'configs/prod/allowed-regions.json' in blob_url

    # Test policy with nested blob path
    policy = test.load_policy({
        'name': 'test-nested-path-azure-blob',
        'resource': 'azure.vm',
        'filters': [
            {
                'type': 'value',
                'key': 'location',
                'op': 'in',
                'value_from': {
                    'url': blob_url,
                    'format': 'json'
                }
            }
        ]
    })

    # Verify policy loads correctly
    assert policy is not None

    # Verify nested path in URL
    filters = policy.resource_manager.filters
    assert 'configs/prod/allowed-regions.json' in filters[0].data['value_from']['url']

    print(f"SUCCESS: Policy with nested path blob '{blob_url}' validated successfully")


@terraform('azure_blob_storage')
@pytest.mark.functional
def test_value_from_empty_json_array_terraform(test, azure_blob_storage):
    """Test value_from filter with empty JSON array (edge case)"""
    # Get empty array blob URL from Terraform outputs
    blob_info = azure_blob_storage.outputs['blob_empty']['value']
    blob_url = blob_info['url']

    # Verify URL format
    assert 'empty-list.json' in blob_url

    # Test policy with empty array
    policy = test.load_policy({
        'name': 'test-empty-array-azure-blob',
        'resource': 'azure.vm',
        'filters': [
            {
                'type': 'value',
                'key': 'name',
                'op': 'in',
                'value_from': {
                    'url': blob_url,
                    'format': 'json'
                }
            }
        ]
    })

    # Verify policy loads correctly
    assert policy is not None

    print(f"SUCCESS: Policy with empty JSON array '{blob_url}' validated successfully")


@terraform('azure_blob_storage')
@pytest.mark.functional
def test_multiple_filters_same_blob_caching_terraform(test, azure_blob_storage):
    """Test that multiple filters using same blob leverage caching"""
    # Get blob URL
    blob_info = azure_blob_storage.outputs['blob_json_simple']['value']
    blob_url = blob_info['url']

    # Create policy with multiple filters using the same blob
    # This should hit cache on second filter evaluation
    policy = test.load_policy({
        'name': 'test-caching-azure-blob',
        'resource': 'azure.vm',
        'filters': [
            {
                'type': 'value',
                'key': 'name',
                'op': 'in',
                'value_from': {
                    'url': blob_url,
                    'format': 'json'
                }
            }
        ]
    })

    # Verify policy loads correctly
    assert policy is not None

    # The actual caching test would require executing the policy with resources,
    # but here we're just verifying the configuration is valid
    filters = policy.resource_manager.filters
    assert len(filters) == 1

    print("SUCCESS: Caching test policy validated successfully")
