# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime

from c7n.filters import Filter, AgeFilter
from c7n.utils import type_schema, group_by
from c7n_azure.provider import resources
from c7n_azure.query import ChildTypeInfo
from c7n_azure.resources.arm import ArmResourceManager, ChildArmResourceManager, ArmTypeInfo
from c7n_azure.utils import ResourceIdParser


@resources.register('compute-gallery', aliases=['image-gallery'])
class ComputeGallery(ArmResourceManager):
    """Azure Compute Gallery (formerly Shared Image Gallery)

    :example:

    Find all compute galleries in a specific region

    .. code-block:: yaml

        policies:
          - name: compute-galleries-westus
            resource: azure.compute-gallery
            filters:
              - type: value
                key: location
                op: eq
                value: westus2

    """
    class resource_type(ArmTypeInfo):
        doc_groups = ['Compute']

        service = 'azure.mgmt.compute'
        client = 'ComputeManagementClient'
        enum_spec = ('galleries', 'list', None)
        resource_type = 'Microsoft.Compute/galleries'

        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )


@resources.register('compute-gallery-image', aliases=['image-gallery-image'])
class ComputeGalleryImage(ChildArmResourceManager):
    """Azure Compute Gallery Image Definition

    :example:

    Find all Linux-based image definitions

    .. code-block:: yaml

        policies:
          - name: find-linux-images
            resource: azure.compute-gallery-image
            filters:
              - type: value
                key: properties.osType
                op: eq
                value: Linux
    
    :example:

    Get image definitions within a specific gallery

    .. code-block:: yaml

        policies:
          - name: images-within-mygallery
            resource: azure.compute-gallery-image
            filters:
              - type: gallery
                value: MyGallery

    """
    class resource_type(ChildTypeInfo, ArmTypeInfo):
        doc_groups = ['Compute']

        service = 'azure.mgmt.compute'
        client = 'ComputeManagementClient'
        resource_type = 'Microsoft.Compute/galleries/images'

        enum_spec = (
            'gallery_images',
            'list_by_gallery',
            None
        )

        parent_manager_name = 'compute-gallery'

        @classmethod
        def extra_args(cls, parent_resource):
            return {
                'resource_group_name': parent_resource['resourceGroup'],
                'gallery_name': parent_resource['name']
            }


@ComputeGalleryImage.filter_registry.register('gallery')
class GalleryFilter(Filter):
    """Filter images by gallery name.

    :example:

    Find all image definitions in a specific gallery

    .. code-block:: yaml

        policies:
          - name: images-in-my-gallery
            resource: azure.compute-gallery-image
            filters:
              - type: gallery
                value: MyImageGallery
    """
    schema = type_schema('gallery', value={'type': 'string'})

    def process(self, resources, event=None):
        gallery_name = self.data.get('value')
        parent_key = self.manager.resource_type.parent_key
        return [r for r in resources
                if ResourceIdParser.get_resource_name(r[parent_key]) == gallery_name]


@resources.register('compute-gallery-image-version', aliases=['image-gallery-image-version'])
class ComputeGalleryImageVersion(ChildArmResourceManager):
    """Azure Compute Gallery Image Version

    :example:

    Find all image versions published in the last 30 days

    .. code-block:: yaml

        policies:
          - name: recent-compute-gallery-image-versions
            resource: azure.compute-gallery-image-version
            filters:
              - type: value
                key: properties.publishingProfile.publishedDate
                op: greater-than
                value_type: age
                value: 30

    """
    class resource_type(ChildTypeInfo, ArmTypeInfo):
        doc_groups = ['Compute']

        service = 'azure.mgmt.compute'
        client = 'ComputeManagementClient'
        resource_type = 'Microsoft.Compute/galleries/images/versions'

        enum_spec = (
            'gallery_image_versions',
            'list_by_gallery_image',
            None
        )

        parent_manager_name = 'compute-gallery-image'
        parent_key = 'image_name'
        raise_on_exception = False

        @classmethod
        def extra_args(cls, parent_resource):
            # parent_resource is the gallery image
            # Get gallery name from the image's parent ID
            gallery_id = parent_resource.get('c7n:parent-id')
            gallery_name = ResourceIdParser.get_resource_name(gallery_id) if gallery_id else None

            return {
                'resource_group_name': parent_resource['resourceGroup'],
                'gallery_name': gallery_name,
                'gallery_image_name': parent_resource['name']
            }


@ComputeGalleryImageVersion.filter_registry.register('image-definition')
class ImageDefinitionFilter(Filter):
    """Filter image versions by image definition name.

    :example:

    Find all versions of a specific image definition

    .. code-block:: yaml

        policies:
          - name: versions-of-my-image
            resource: azure.compute-gallery-image-version
            filters:
              - type: image-definition
                value: MyImageDefinition
    """
    schema = type_schema('image-definition', value={'type': 'string'})

    def process(self, resources, event=None):
        image_name = self.data.get('value')
        parent_key = self.manager.resource_type.parent_key
        return [r for r in resources
                if ResourceIdParser.get_resource_name(r.get(parent_key, '')) == image_name]


@ComputeGalleryImageVersion.filter_registry.register('age')
class ImageVersionAgeFilter(AgeFilter):
    """Filter image versions by age based on the image published date.

    :example:

    Find image versions older than 90 days

    .. code-block:: yaml

        policies:
          - name: old-image-versions
            resource: azure.compute-gallery-image-version
            filters:
              - type: age
                days: 90
    """
    date_attribute = 'properties.publishingProfile.publishedDate'
    schema = type_schema(
        'age',
        days={'type': 'number', 'minimum': 0},
        hours={'type': 'number', 'minimum': 0},
        minutes={'type': 'number', 'minimum': 0},
        op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )

    def get_resource_date(self, resource):
        """Safely extract the published date from nested resource properties."""
        try:
            date_str = resource.get('properties', {}).get('publishingProfile', {}).get('publishedDate')
            if not date_str:
                return None

            # Parse ISO format datetime
            if not isinstance(date_str, datetime):
                from dateutil.parser import parse
                from dateutil.tz import tzutc
                v = parse(date_str)
                if not v.tzinfo:
                    v = v.replace(tzinfo=tzutc())
                return v
            return date_str
        except (ValueError, AttributeError, TypeError):
            return None


@ComputeGalleryImageVersion.filter_registry.register('latest')
class LatestImageVersionFilter(Filter):
    """Filter to include or exclude the latest image version per image definition.

    When true, only the latest version of each image is returned.
    When false, all versions except the latest are returned.

    The latest version is derived from the publishedDate field.

    :example:

    Find only the latest version of each image

    .. code-block:: yaml

        policies:
          - name: latest-image-versions
            resource: azure.compute-gallery-image-version
            filters:
              - type: latest
                value: true

    :example:

    Get all versions except the latest one

    .. code-block:: yaml

        policies:
          - name: get-old-image-versions
            resource: azure.compute-gallery-image-version
            filters:
              - type: latest
                value: false
    """
    schema = type_schema('latest', value={'type': 'boolean'})

    def process(self, resources, event=None):
        include_latest = self.data.get('value', True)
        parent_key = self.manager.resource_type.parent_key

        # Group resources by parent image
        grouped = group_by(resources, parent_key)

        result = []
        for image_id, versions in grouped.items():
            if not versions:
                continue

            # Find the latest version by published date
            latest_version = max(
                versions,
                key=lambda v: self._get_published_date(v)
            )

            if include_latest:
                # Only include the latest version
                result.append(latest_version)
            else:
                # Include all versions except the latest
                result.extend([v for v in versions if v != latest_version])

        return result

    def _get_published_date(self, resource):
        """Extract published date from resource, defaulting to epoch if not found."""
        try:
            date_str = resource.get('properties', {}).get('publishingProfile', {}).get('publishedDate')
            if date_str:
                # Parse ISO format datetime
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass
        # Return epoch as fallback for unpublished or malformed dates
        return datetime(1970, 1, 1)
