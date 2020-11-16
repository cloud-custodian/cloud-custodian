# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import re

from c7n_gcp.provider import resources
from c7n_gcp.query import (QueryResourceManager, TypeInfo, ChildTypeInfo,
                           ChildResourceManager)
from c7n.utils import type_schema, local_session
from c7n_gcp.actions import MethodAction


@resources.register('gke-cluster')
class KubernetesCluster(QueryResourceManager):
    """GCP resource:
    https://cloud.google.com/kubernetes-engine/docs/reference/rest/v1/projects.zones.clusters
    """

    class resource_type(TypeInfo):
        service = 'container'
        version = 'v1'
        component = 'projects.locations.clusters'
        enum_spec = ('list', 'clusters[]', None)
        scope = 'project'
        scope_key = 'parent'
        scope_template = "projects/{}/locations/-"
        name = id = "name"
        default_report_fields = [
            'name', 'description', 'status', 'currentMasterVersion', 'currentNodeVersion',
            'currentNodeCount', 'location']
        asset_type = 'container.googleapis.com/Cluster'

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get', verb_arguments={
                    'name': 'projects/{}/locations/{}/clusters/{}'.format(
                        resource_info['project_id'],
                        resource_info['location'],
                        resource_info['cluster_name'])})


@resources.register('gke-nodepool')
class KubernetesClusterNodePool(ChildResourceManager):
    """GCP resource:
    https://cloud.google.com/kubernetes-engine/docs/reference/rest/v1/projects.zones.clusters.nodePools
    """

    def _get_parent_resource_info(self, child_instance):
        project_param_re = re.compile(
            '.*?/projects/(.*?)/zones/(.*?)/clusters/(.*?)/nodePools/(.*?)'
        )
        parent_values = re.match(project_param_re, child_instance['selfLink']).groups()
        parent_info = dict(
            zip(('project_id', 'location', 'cluster_name', 'node_name'), parent_values)
        )

        return parent_info

    def _get_child_enum_args(self, parent_instance):
        return {
            'parent': 'projects/{}/locations/{}/clusters/{}'.format(
                local_session(self.session_factory).get_default_project(),
                parent_instance['location'],
                parent_instance['name']
            )
        }

    class resource_type(ChildTypeInfo):
        service = 'container'
        version = 'v1'
        component = 'projects.locations.clusters.nodePools'
        enum_spec = ('list', 'nodePools[]', None)
        scope = 'global'
        name = id = 'name'
        parent_spec = {'resource': 'gke-cluster'}
        asset_type = 'container.googleapis.com/NodePool'
        default_report_fields = ['name', 'status', 'version']
        permissions = ('container.nodes.list',)

        @staticmethod
        def get(client, resource_info):
            cluster_name = resource_info['cluster_name']
            name = re.match(
                r".*{}-(.*)-[^-]+-[^-]?".format(cluster_name),
                resource_info['resourceName']).group(1)

            return client.execute_command(
                'get', verb_arguments={
                    'name': 'projects/{}/locations/{}/clusters/{}/nodePools/{}'.format(
                        resource_info['project_id'],
                        resource_info['location'],
                        resource_info['cluster_name'],
                        name)}
            )


@KubernetesCluster.action_registry.register('delete')
class Delete(MethodAction):
    """Action to delete GKE clusters

    It is recommended to use a filter to avoid unwanted deletion of GKE clusters

    :example:

    .. code-block:: yaml

            policies:
              - name: gcp-delete-testing-gke-clusters
                resource: gcp.gke-cluster
                filters:
                  - type: value
                    key: name
                    op: regex
                    value: '^(test-|demo-)*'
                actions:
                  - type: delete
    """

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}

    def get_resource_params(self, model, resource_info):
        project = local_session(self.manager.source.query.session_factory).get_default_project()

        return {'name': 'projects/{}/locations/{}/clusters/{}'.format(
                        project,
                        resource_info['location'],
                        resource_info['name'])}
