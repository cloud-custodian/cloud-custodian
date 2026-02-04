# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import re

from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo, ChildTypeInfo, ChildResourceManager
from c7n.utils import type_schema, local_session
from c7n_gcp.actions import MethodAction
from c7n_gcp.utils import get_firewall_port_ranges

from c7n.filters import ValueFilter


@resources.register('gke-cluster')
class KubernetesCluster(QueryResourceManager):
    """GCP resource:
    https://cloud.google.com/kubernetes-engine/docs/reference/rest/v1/projects.locations.clusters
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
            'name',
            'description',
            'status',
            'currentMasterVersion',
            'currentNodeVersion',
            'currentNodeCount',
            'location',
        ]
        asset_type = 'container.googleapis.com/Cluster'
        scc_type = 'google.container.Cluster'
        metric_key = 'resource.labels.cluster_name'
        urn_component = 'cluster'
        labels = True
        labels_op = 'setResourceLabels'
        urn_zonal = True

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get',
                verb_arguments={
                    'name': 'projects/{}/locations/{}/clusters/{}'.format(
                        resource_info['project_id'],
                        resource_info['location'],
                        resource_info['cluster_name'],
                    )
                },
            )

        @staticmethod
        def get_label_params(resource, all_labels):
            location_str = "locations"
            if resource['selfLink'].find(location_str) < 0:
                location_str = "zones"
            path_param_re = re.compile(
                "%s%s%s" % ('.*?/projects/(.*?)/', location_str, '/(.*?)/clusters/(.*)')
            )
            project, zone, cluster_name = path_param_re.match(resource['selfLink']).groups()
            return {
                'name': "%s%s%s%s%s%s"
                % ('projects/', project, '/locations/', zone, '/clusters/', cluster_name),
                'body': {
                    'resourceLabels': all_labels,
                    'labelFingerprint': resource['labelFingerprint'],
                },
            }

        @classmethod
        def refresh(cls, client, resource):
            project_id = resource['selfLink'].split("/")[5]
            return cls.get(
                client,
                {
                    'project_id': project_id,
                    'location': resource['zone'],
                    'cluster_name': resource['name'],
                },
            )

    def augment(self, resources):
        if not resources:
            return []
        for r in resources:
            if r.get('resourceLabels'):
                r['labels'] = r['resourceLabels']
        return resources


@KubernetesCluster.filter_registry.register('effective-firewall')
class EffectiveFirewall(ValueFilter):
    """Filters gke clusters  by their effective firewall rules.
    See `getEffectiveFirewalls
    https://cloud.google.com/workflows/docs/reference/googleapis/compute/v1/networks/getEffectiveFirewalls`_
    for valid fields.

    :example:

    Filter all gke clusters that have a firewall rule that allows public
    access

    .. code-block:: yaml

        policies:
           - name: find-publicly-accessable-clusters
             resource: gcp.gke-cluster
             filters:
             - type: effective-firewall
               key: sourceRanges[]
               op: contains
               value: "0.0.0.0/0"
    """

    schema = type_schema('effective-firewall', rinherit=ValueFilter.schema)
    permissions = ('compute.instances.getEffectiveFirewalls',)
    annotation_key = "c7n:firewall"

    def get_firewalls(self, client, p, r):
        if self.annotation_key not in r:
            firewalls = client.execute_command(
                'getEffectiveFirewalls', verb_arguments={'project': p, 'network': r['network']}
            ).get('firewalls', [])

            r[self.annotation_key] = get_firewall_port_ranges(firewalls)
        return super(EffectiveFirewall, self).process(r[self.annotation_key], None)

    def process(self, resources, event=None):
        session = local_session(self.manager.session_factory)
        project = session.get_default_project()
        client = session.client("compute", "v1", "networks")
        resource_list = [r for r in resources if self.get_firewalls(client, project, r)]
        return resource_list


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
                parent_instance['name'],
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
        urn_component = 'cluster-node-pool'
        urn_zonal = True

        @staticmethod
        def get(client, resource_info):
            cluster_name = resource_info['cluster_name']
            name = re.match(
                r".*{}-(.*)-[^-]+-[^-]?".format(cluster_name), resource_info['resourceName']
            ).group(1)

            return client.execute_command(
                'get',
                verb_arguments={
                    'name': 'projects/{}/locations/{}/clusters/{}/nodePools/{}'.format(
                        resource_info['project_id'],
                        resource_info['location'],
                        resource_info['cluster_name'],
                        name,
                    )
                },
            )

        @classmethod
        def _get_location(cls, resource):
            "Get the region from the parent - the cluster"
            return super()._get_location(cls.get_parent(resource))


@KubernetesCluster.filter_registry.register('server-config')
@KubernetesClusterNodePool.filter_registry.register('server-config')
class ServerConfig(ValueFilter):
    """Filters kubernetes clusters or nodepools by their server config.
    See `getServerConfig
    https://cloud.google.com/kubernetes-engine/docs/reference/rest/v1/projects.locations/getServerConfig`
    for valid fields.

    :example:

    Filter all clusters that is not running a supported version

    .. code-block:: yaml

        policies:
           - name: find-unsupported-cluster-version
             resource: gcp.gke-cluster
             filters:
             - type: server-config
               key: contains(serverConfig.validMasterVersions, resource.currentMasterVersion)
               value: false

    Filter all nodepools that is not running a supported version

    .. code-block:: yaml

        policies:
           - name: find-unsupported-cluster-nodepools-version
             resource: gcp.gke-nodepool
             filters:
             - type: server-config
               key: contains(serverConfig.validNodeVersions, resource.version)
               value: false
    """

    schema = type_schema('server-config', rinherit=ValueFilter.schema)
    permissions = ('container.nodes.get', 'container.clusters.get')
    annotation_key = "c7n:config"

    def _get_location(self, r):
        return r["location"] if "location" in r else r['selfLink'].split('/')[-5]

    def get_config(self, client, project, resource):
        if self.annotation_key in resource:
            return
        location = self._get_location(resource)
        resource[self.annotation_key] = client.execute_command(
            'getServerConfig',
            verb_arguments={'name': 'projects/{}/locations/{}'.format(project, location)},
        )

    def __call__(self, r):
        return super().__call__({"serverConfig": r[self.annotation_key], "resource": r})

    def process(self, resources, event=None):
        session = local_session(self.manager.session_factory)
        project = session.get_default_project()
        client = session.client("container", "v1", "projects.locations")
        for r in resources:
            self.get_config(client, project, r)
        return super().process(resources)


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

        return {
            'name': 'projects/{}/locations/{}/clusters/{}'.format(
                project, resource_info['location'], resource_info['name']
            )
        }


@KubernetesClusterNodePool.action_registry.register('delete')
class NodepoolDeleteAction(MethodAction):
    """Action to delete GKE nodepools

    It is recommended to use a filter to avoid unwanted deletion of GKE nodepools

    :example:

    .. code-block:: yaml

            policies:
              - name: gcp-delete-testing-gke-nodepools
                resource: gcp.gke-nodepool
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
    permissions = ('container.clusters.update',)

    def get_resource_params(self, model, resource):
        project = local_session(self.manager.source.query.session_factory).get_default_project()
        # Extract location and cluster name from the nodepool selfLink
        # selfLink format: projects/{project}/zones/{zone}/clusters/{cluster}/nodePools/{nodepool}
        project_param_re = re.compile(
            '.*?/projects/([^/]+)/(?:zones|locations)/([^/]+)/clusters/([^/]+)/nodePools/([^/]+)'
        )
        match = re.match(project_param_re, resource['selfLink'])
        if match:
            _, location, cluster_name, nodepool_name = match.groups()
        else:
            # Fallback: try to extract from parent info
            parent_info = self.manager._get_parent_resource_info(resource)
            location = parent_info['location']
            cluster_name = parent_info['cluster_name']
            nodepool_name = resource['name']

        return {
            'name': 'projects/{}/locations/{}/clusters/{}/nodePools/{}'.format(
                project, location, cluster_name, nodepool_name
            )
        }
