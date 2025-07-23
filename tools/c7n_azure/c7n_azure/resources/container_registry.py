import logging
from c7n_azure.provider import resources
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.resources.arm import ArmResourceManager
from c7n.utils import type_schema

import subprocess
import json
import re
import datetime

from c7n_azure.actions.base import AzureBaseAction
from c7n.utils import type_schema
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager

log = logging.getLogger('custodian.azure.acr')

@resources.register('container-registry')
class ContainerRegistry(ArmResourceManager):
    """Container Registry Resource

    :example:

    Returns all container registry named my-test-container-registry

    .. code-block:: yaml

        policies:
        - name: get-container-registry
          resource: azure.container-registry
          filters:
            - type: value
              key: name
              op: eq
              value: my-test-container-registry

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['ContainerRegistry']

        service = 'azure.mgmt.containerregistry'
        client = 'ContainerRegistryManagementClient'
        enum_spec = ('registries', 'list', None)
        resource_type = 'Microsoft.ContainerRegistry/registries'
        default_report_fields = (
            'name',
            'location',
            'sku.name',
            'resourceGroup',
            'properties.adminUserEnabled'
        )
        id = 'id'
        name = 'name'
        default_compare_fields = ('name', 'location')


@ContainerRegistry.action_registry.register('delete-images')
class DeleteImagesAction(AzureBaseAction):
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
      for r in resources:
          updated = self._process_resource(r)
          if updated is not None:
              results.append(updated)
      return results  # this populates resources.json

    def _process_resource(self, registry):
      days = self.data['days']
      keep = self.data['keep']
      pattern = self.data.get('match', '.*')
      now = datetime.datetime.utcnow()
      cutoff = now - datetime.timedelta(days=days)

      name = registry['name']
      repos = self._az_cli(['acr', 'repository', 'list', '--name', name])

      # only keep first 3 repos for testing
      if len(repos) > 3:
          repos = repos[:3]

      deleted = []
      DELETED_FR = False
      for repo in repos:
          if not re.search(pattern, repo):
              continue

          self.log.info(f"Checking repo: {repo}")
          manifests = self._az_cli([
              'acr', 'repository', 'show-manifests',
              '--name', name, '--repository', repo
          ])
          # Sort by timestamp descending
          manifests.sort(key=lambda m: m['timestamp'], reverse=True)

          to_delete = []
          kept = 0
          for i, m in enumerate(manifests):
              timestamp_str = m['timestamp']
              timestamp_str = re.sub(r'\.(\d{6})\d*Z$', r'.\1Z', timestamp_str)
              timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%fZ")
              if timestamp < cutoff:
                  if kept < keep:
                      kept += 1
                  else:
                      to_delete.append(m)

          for image in to_delete:
              tag = image['tags'][0] if 'tags' in image else image['digest']
              self.log.debug(f"Deleting image: {repo}:{tag} (timestamp: {image['timestamp']})")
              self._az_cli([
                  'acr', 'repository', 'delete',
                  '--name', name, '--image', f'{repo}@{image['digest']}', '--yes',
              ], expect_json=False)
              deleted.append({'repository': repo, 'tag': tag, 'timestamp': image['timestamp']})
      
      registry['c7n:deleted-images'] = deleted

      return registry
  
    def _az_cli(self, args, expect_json=True):
      cmd = ['az'] + args + ['--output', 'json'] if expect_json else ['az'] + args
      result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
      return json.loads(result.stdout) if expect_json else result.stdout