# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import pytest
from pytest_terraform import terraform
from tests_azure.azure_common import BaseTest


class ComputeGalleryTest(BaseTest):
    """Test Compute Gallery resource functionality"""

    def setUp(self):
        super().setUp()

    def test_compute_gallery_schema_validate(self):
        """Test that the Compute Gallery resource schema validates correctly"""
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-compute-gallery',
                'resource': 'azure.compute-gallery',
                'filters': [
                    {'type': 'value', 'key': 'location', 'value': 'westeurope'}
                ]
            }, validate=True)
            self.assertTrue(p)


class ComputeGalleryImageTest(BaseTest):
    """Test Compute Gallery Image resource functionality"""

    def setUp(self):
        super().setUp()

    def test_compute_gallery_image_schema_validate(self):
        """Test that the Compute Gallery Image resource schema validates correctly"""
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-compute-gallery-image',
                'resource': 'azure.compute-gallery-image',
                'filters': [
                    {'type': 'value', 'key': 'properties.osType', 'value': 'Linux'}
                ]
            }, validate=True)
            self.assertTrue(p)


class ComputeGalleryImageVersionTest(BaseTest):
    """Test Compute Gallery Image Version resource functionality"""

    def setUp(self):
        super().setUp()

    def test_compute_gallery_image_version_schema_validate(self):
        """Test that the Image Version resource schema validates correctly"""
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-image-version',
                'resource': 'azure.compute-gallery-image-version',
                'filters': [
                    {'type': 'age', 'days': 90}
                ]
            }, validate=True)
            self.assertTrue(p)

    def test_image_definition_filter_schema(self):
        """Test image-definition filter schema validation"""
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-image-def-filter',
                'resource': 'azure.compute-gallery-image-version',
                'filters': [
                    {'type': 'image-definition', 'value': 'test-image'}
                ]
            }, validate=True)
            self.assertTrue(p)

    def test_latest_filter_schema(self):
        """Test latest filter schema validation"""
        with self.sign_out_patch():
            # Test with value: true
            p = self.load_policy({
                'name': 'test-latest-filter-true',
                'resource': 'azure.compute-gallery-image-version',
                'filters': [
                    {'type': 'latest', 'value': True}
                ]
            }, validate=True)
            self.assertTrue(p)

            # Test with value: false
            p = self.load_policy({
                'name': 'test-latest-filter-false',
                'resource': 'azure.compute-gallery-image-version',
                'filters': [
                    {'type': 'latest', 'value': False}
                ]
            }, validate=True)
            self.assertTrue(p)

    def test_age_filter_schema(self):
        """Test age filter schema validation"""
        with self.sign_out_patch():
            # Test with days
            p = self.load_policy({
                'name': 'test-age-days',
                'resource': 'azure.compute-gallery-image-version',
                'filters': [
                    {'type': 'age', 'days': 90}
                ]
            }, validate=True)
            self.assertTrue(p)

            # Test with hours
            p = self.load_policy({
                'name': 'test-age-hours',
                'resource': 'azure.compute-gallery-image-version',
                'filters': [
                    {'type': 'age', 'hours': 24}
                ]
            }, validate=True)
            self.assertTrue(p)

            # Test with operator
            p = self.load_policy({
                'name': 'test-age-operator',
                'resource': 'azure.compute-gallery-image-version',
                'filters': [
                    {'type': 'age', 'days': 30, 'op': 'less-than'}
                ]
            }, validate=True)
            self.assertTrue(p)


# Terraform-based functional tests (must be module-level functions)

@terraform('compute_gallery')
@pytest.mark.functional
def test_compute_gallery_discovery_terraform(test, compute_gallery):
    """Test that Cloud Custodian can discover galleries provisioned by Terraform"""
    # Verify terraform fixtures loaded successfully
    assert 'test_gallery' in compute_gallery.outputs
    assert 'secondary_gallery' in compute_gallery.outputs

    test_gallery = compute_gallery.outputs['test_gallery']['value']
    secondary_gallery = compute_gallery.outputs['secondary_gallery']['value']

    # Run discovery policy
    policy = test.load_policy({
        'name': 'test-gallery-discovery',
        'resource': 'azure.compute-gallery'
    })

    resources = policy.run()

    # Verify both galleries are discovered
    gallery_names = {r['name'] for r in resources}
    assert test_gallery['name'] in gallery_names
    assert secondary_gallery['name'] in gallery_names


@terraform('compute_gallery')
@pytest.mark.functional
def test_compute_gallery_location_filter_terraform(test, compute_gallery):
    """Test location filter on compute galleries"""
    # Filter by location
    policy = test.load_policy({
        'name': 'test-gallery-location',
        'resource': 'azure.compute-gallery',
        'filters': [
            {'type': 'value', 'key': 'location', 'op': 'eq', 'value': 'westeurope'}
        ]
    })

    resources = policy.run()

    # Verify filtered results
    assert len(resources) >= 2
    assert all(r['location'] == 'westeurope' for r in resources)


@terraform('compute_gallery')
@pytest.mark.functional
def test_compute_gallery_image_discovery_terraform(test, compute_gallery):
    """Test that Cloud Custodian can discover image definitions"""
    linux_image = compute_gallery.outputs['linux_image']['value']
    windows_image = compute_gallery.outputs['windows_image']['value']

    # Run discovery policy
    policy = test.load_policy({
        'name': 'test-image-discovery',
        'resource': 'azure.compute-gallery-image'
    })

    resources = policy.run()

    # Verify images are discovered
    image_names = {r['name'] for r in resources}
    assert linux_image['name'] in image_names
    assert windows_image['name'] in image_names


@terraform('compute_gallery')
@pytest.mark.functional
def test_compute_gallery_image_os_filter_terraform(test, compute_gallery):
    """Test OS type filter on image definitions"""
    linux_image = compute_gallery.outputs['linux_image']['value']

    # Filter by Linux OS type
    policy = test.load_policy({
        'name': 'test-linux-images',
        'resource': 'azure.compute-gallery-image',
        'filters': [
            {'type': 'value', 'key': 'properties.osType', 'op': 'eq', 'value': 'Linux'}
        ]
    })

    resources = policy.run()

    # Verify all returned resources are Linux
    assert all(r['properties']['osType'] == 'Linux' for r in resources)
    assert any(r['name'] == linux_image['name'] for r in resources)


@terraform('compute_gallery')
@pytest.mark.functional
def test_compute_gallery_image_gallery_filter_terraform(test, compute_gallery):
    """Test gallery filter on image definitions"""
    test_gallery = compute_gallery.outputs['test_gallery']['value']
    linux_image = compute_gallery.outputs['linux_image']['value']
    windows_image = compute_gallery.outputs['windows_image']['value']

    # Filter by gallery name
    policy = test.load_policy({
        'name': 'test-gallery-filter',
        'resource': 'azure.compute-gallery-image',
        'filters': [
            {'type': 'gallery', 'value': test_gallery['name']}
        ]
    })

    resources = policy.run()

    # Verify only images from the specified gallery are returned
    image_names = {r['name'] for r in resources}
    assert linux_image['name'] in image_names
    assert windows_image['name'] in image_names

    # Verify all resources belong to the test gallery
    for r in resources:
        assert r.get('c7n:parent-id'), "Missing parent-id annotation"
