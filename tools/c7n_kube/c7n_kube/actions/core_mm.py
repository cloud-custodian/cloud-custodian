# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
# This is an MM upgrade: to be able to use save-options-tag on patch action

import copy
import logging
from .core import PatchAction, PatchResource

log = logging.getLogger("custodian.k8s.actions")


class PatchActionMM(PatchAction):
    """Extended PatchAction with custom resource support"""

    def patch_resources(self, client, resources, **patch_args):
        from kubernetes.client.exceptions import ApiException
        op = getattr(client, self.manager.get_model().patch)
        namespaced = self.manager.get_model().namespaced
        for r in resources:
            patch_args["name"] = r["metadata"]["name"]
            if namespaced:
                patch_args["namespace"] = r["metadata"]["namespace"]

            # Add custom resource parameters if needed
            if self.manager.get_model().patch == 'patch_cluster_custom_object':
                # Get custom resource details from manager's query
                if hasattr(self.manager, 'get_resource_query'):
                    query = self.manager.get_resource_query()
                    if query and isinstance(query, dict):
                        patch_args['group'] = query.get('group')
                        patch_args['version'] = query.get('version')
                        patch_args['plural'] = query.get('plural')
            elif self.manager.get_model().patch == 'patch_namespaced_custom_object':
                # Handle namespaced custom resources
                if hasattr(self.manager, 'get_resource_query'):
                    query = self.manager.get_resource_query()
                    if query and isinstance(query, dict):
                        patch_args['group'] = query.get('group')
                        patch_args['version'] = query.get('version')
                        patch_args['plural'] = query.get('plural')

            try:
                op(**patch_args)
            except ApiException as e:
                if e.status == 404:
                    log.warning(f"Resource {r['metadata']['name']} not found - it was likely deleted during execution")
                else:
                    raise

    def patch_resources_replicas(self, client, resources, patch):
        from kubernetes.client.exceptions import ApiException
        op = getattr(client, self.manager.get_model().patch)
        namespaced = self.manager.get_model().namespaced
        for r in resources:
            patch_args = patch[r['metadata']['name']]
            patch_args['name'] = r['metadata']['name']
            if namespaced:
                patch_args['namespace'] = r['metadata']['namespace']

            # Add custom resource parameters if needed
            if self.manager.get_model().patch == 'patch_cluster_custom_object':
                # Get custom resource details from manager's query
                if hasattr(self.manager, 'get_resource_query'):
                    query = self.manager.get_resource_query()
                    if query and isinstance(query, dict):
                        patch_args['group'] = query.get('group')
                        patch_args['version'] = query.get('version')
                        patch_args['plural'] = query.get('plural')
            elif self.manager.get_model().patch == 'patch_namespaced_custom_object':
                # Handle namespaced custom resources
                if hasattr(self.manager, 'get_resource_query'):
                    query = self.manager.get_resource_query()
                    if query and isinstance(query, dict):
                        patch_args['group'] = query.get('group')
                        patch_args['version'] = query.get('version')
                        patch_args['plural'] = query.get('plural')

            try:
                op(**patch_args)
            except ApiException as e:
                if e.status == 404:
                    log.warning(f"Resource {r['metadata']['name']} not found - it was likely deleted during execution")
                else:
                    raise


class PatchResourceMM(PatchActionMM):
    """Extended PatchResource with support for NodePools and other custom resources"""

    schema = PatchResource.schema

    def process_resource_set(self, client, resources):
        patch = {}

        for r in resources:
            patch_args = copy.deepcopy({'body': self.data.get('options', {})})

            if 'save-options-tag' in self.data:
                save_tag = self.data.get('save-options-tag', {})

                # Handle different resource types
                if 'spec' in r:
                    if 'replicas' in r['spec']:
                        # For deployments, statefulsets, etc.
                        value = r['spec']['replicas']
                        save_value = f'replicas-{value}'
                    elif 'limits' in r['spec'] and 'cpu' in r['spec']['limits']:
                        # For NodePools
                        value = r['spec']['limits']['cpu']
                        save_value = f'cpu-{value}'
                    else:
                        # Generic fallback
                        save_value = 'saved'
                else:
                    save_value = 'saved'

                if not r['metadata'].get('labels'):
                    r['metadata']['labels'] = {}
                r['metadata']['labels'][save_tag] = save_value
                patch_args['body']['metadata'] = {}
                patch_args['body']['metadata']['labels'] = r['metadata']['labels']
                patch[r['metadata']['name']] = patch_args
            elif 'restore-options-tag' in self.data:
                restore_tag = self.data.get('restore-options-tag', {})

                if restore_tag in r['metadata'].get('labels', {}):
                    saved_value = r['metadata']['labels'][restore_tag]
                    if saved_value.startswith('replicas-'):
                        # Restore replicas for deployments, etc.
                        replicas = saved_value.split('-')[1]
                        patch_args['body']['spec'] = {'replicas': int(replicas)}
                    elif saved_value.startswith('cpu-'):
                        # Restore CPU for NodePools
                        cpu_value = saved_value.split('-')[1]
                        patch_args['body']['spec'] = {'limits': {'cpu': cpu_value}}

            patch[r['metadata']['name']] = patch_args

        self.patch_resources_replicas(client, resources, patch)

    @classmethod
    def register_resources(klass, registry, resource_class):
        model = resource_class.resource_type
        if hasattr(model, "patch") and hasattr(model, "namespaced"):
            resource_class.action_registry.register("patch", klass)


# Override the original classes to use the extended versions transparently
PatchAction.patch_resources = PatchActionMM.patch_resources
PatchAction.patch_resources_replicas = PatchActionMM.patch_resources_replicas
PatchResource.process_resource_set = PatchResourceMM.process_resource_set