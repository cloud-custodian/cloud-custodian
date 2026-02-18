# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging
import subprocess  # nosec B404
import json
import re
import datetime

from c7n_azure.provider import resources
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.resources.arm import ArmResourceManager
from c7n.utils import type_schema

log = logging.getLogger('custodian.azure.acr')


@resources.register('container-registry', aliases=['containerregistry'])
class ContainerRegistry(ArmResourceManager):
    """Container Registry Resource

    :example:

    This policy will find all Azure Container Registries with encryption disabled.

    .. code-block:: yaml

        policies:
          - name: acr-encryption-disabled
            resource: azure.container-registry
            filters:
              - type: value
                key: properties.encryption.status
                value: 'disabled'

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Containers']

        service = 'azure.mgmt.containerregistry'
        client = 'ContainerRegistryManagementClient'
        enum_spec = ('registries', 'list', None)
        resource_type = 'Microsoft.ContainerRegistry/registries'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'sku.name',
            'properties.adminUserEnabled'
        )
        id = 'id'
        name = 'name'
        default_compare_fields = ('name', 'location')


@ContainerRegistry.action_registry.register('delete-images')
class DeleteImagesAction(AzureBaseAction):
    """
    Action to delete old images from an Azure Container Registry, keeping a specified number of
    recent images based on a timestamp cutoff.

    **Key Features**:

    - Deletes images older than a specified number of days.
    - Keeps a specified number of most recent images after the cutoff.
    - Supports filtering by repository name using a regex pattern.

    :param days:
        Number of days to look back for images to delete. Images older than this will be deleted
    :type days: int

    :param keep:
        Number of most recent images to keep after the cutoff date.
    :type keep: int

    :param match:
        Regex pattern matching repository names. Only process matching repositories.
    :type match: str

    **Examples**

     Delete all images older than 30 days, keeping the 5 most recent images in each repository:

    .. code-block:: yaml

        policies:
          - name: delete-old-acr-images
            resource: azure.container-registry
            actions:
              - type: delete-images
                days: 30
                keep: 5

     Delete images older than 30 days from repositories with names that start with "myapp":

    .. code-block:: yaml

        policies:
          - name: delete-old-acr-images-myapp
            resource: azure.container-registry
            actions:
              - type: delete-images
                days: 30
                keep: 0
                match: '^myapp.*'

    """
    schema = type_schema(
        'delete-images',
        required=['days', 'keep'],
        **{
            'days': {'type': 'integer', 'minimum': 1},
            'keep': {'type': 'integer', 'minimum': 0},
            'match': {'type': 'string'}
        }
    )

    def process(self, resources):
        results = []

        # Since this action is applied to a container registry, we want to reflect what images
        # were deleted in the registry resource itself.
        for r in resources:
            updated = self._process_resource(r)
            if updated is not None:
                results.append(updated)
        return results

    def _process_resource(self, registry):
        days = self.data['days']
        keep = self.data['keep']
        pattern = self.data.get('match', '.*')

        # Get the current time and calculate the cutoff time
        now = datetime.datetime.utcnow()
        cutoff = now - datetime.timedelta(days=days)

        # Get all repositories in the container registry
        name = registry['name']
        repos = self._az_cli(['acr', 'repository', 'list', '--name', name])

        deleted = []  # List to store info about deleted images
        for repo in repos:
            # Check if the repository name matches the specified pattern
            if not re.search(pattern, repo):
                continue

            self.log.info(f"Checking repo: {repo}")

            # Get all manifests for the repository
            manifests = self._az_cli([
                'acr', 'repository', 'show-manifests',
                '--name', name, '--repository', repo
            ])
            # Sort by timestamp descending
            manifests.sort(key=lambda m: m['timestamp'], reverse=True)

            to_delete = []
            kept = 0
            for i, m in enumerate(manifests):
                # Convert timestamp to datetime object
                timestamp_str = m['timestamp']
                timestamp_str = re.sub(r'\.(\d{6})\d*Z$', r'.\1Z', timestamp_str)
                timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%fZ")

                # Check if the timestamp is older than the cutoff
                if timestamp < cutoff:
                    # Keep specified number of images after the cutoff
                    if kept < keep:
                        kept += 1
                    else:
                        to_delete.append(m)

            for image in to_delete:
                # Use image tag in debug output, or digest if no tag is available
                tag = image['tags'][0] if 'tags' in image else image['digest']
                self.log.debug(f"Deleting image: {repo}:{tag} (timestamp: {image['timestamp']})")

                # Delete the image from the repository
                self._az_cli([
                    'acr', 'repository', 'delete',
                    '--name', name, '--image', f"{repo}@{image['digest']}", '--yes',
                ], expect_json=False)  # expect_json=False since command does not return JSON output

                # Append deleted image info to the list
                deleted.append({'repository': repo, 'tag': tag, 'timestamp': image['timestamp']})

        # Update the registry resource with info on deleted images
        registry['c7n:deleted-images'] = deleted

        return registry

    def _az_cli(self, args, expect_json=True):
        cmd = ['az'] + args + ['--output', 'json'] if expect_json else ['az'] + args
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                check=True, text=True)  # nosec B603
        return json.loads(result.stdout) if expect_json else result.stdout
