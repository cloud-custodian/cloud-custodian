# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.utils import type_schema
from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo


@resources.register('notebook')
class NotebookInstance(QueryResourceManager):
    """ GC resource: https://cloud.google.com/vertex-ai/docs/workbench/reference/rest

    GCP Vertex AI Workbench has public IPs.

    :example: GCP Vertex AI Workbench has public IPs

    .. yaml:

     policies:
      - name: gcp-vertex-ai-workbench-with-public-ips
        description: |
          GCP Vertex AI Workbench has public IPs
        resource: gcp.notebook
        filters:
          - type: value
            key: noPublicIp
            value: true
    """
    class resource_type(TypeInfo):
        service = 'notebooks'
        version = 'v1'
        component = 'projects.locations.instances'
        enum_spec = ('list', 'instances[]', None)
        scope_key = 'parent'
        name = id = 'name'
        scope_template = "projects/{}/locations/-"
        permissions = ('notebooks.instances.list',)
        default_report_fields = ['name', 'createTime', 'state']
        urn_id_segments = (-1,)
        urn_component = "instances"

        @classmethod
        def _get_location(cls, resource):
            return resource['name'].split('/')[3]


@resources.register('notebook-v2')
class NotebookInstanceV2(QueryResourceManager):
    """
    GC resource: https://docs.cloud.google.com/gemini-enterprise-agent-platform/notebooks/workbench/reference/rest/v2/projects.locations.instances

    :example: GCP Vertex AI Notebook allows public IPs

    .. yaml:

     policies:
      - name: gcp-vertex-ai-notebook-with-public-ips
        description: |
          GCP Vertex AI Notebook allows public IPs
        resource: gcp.notebook-v2
        filters:
          - type: value
            key: gceSetup.disablePublicIp
            # treats missing values as false
            op: ne
            value: true
    """
    class resource_type(TypeInfo):
        service = 'notebooks'
        version = 'v2'
        component = 'projects.locations.instances'
        enum_spec = ('list', 'instances[]', None)
        scope_key = 'parent'
        name = id = 'name'
        scope_template = "projects/{}/locations/-"
        permissions = ('notebooks.instances.list',)
        default_report_fields = ['name', 'createTime', 'state']
        urn_id_segments = (-1,)
        urn_component = "instances"
        asset_type = "notebooks.googleapis.com/Instance"

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get', {'name': resource_info['resourceName']})

        @classmethod
        def _get_location(cls, resource):
            return resource['name'].split('/')[3]


@NotebookInstanceV2.action_registry.register('update-metadata')
class UpdateMetadata(MethodAction):
    """Merge keys into a notebook-v2 instance's gceSetup.metadata.

    gceSetup.metadata is a map field, so a patch to it replaces the whole
    map -- this action merges the given keys into the instance's current
    metadata rather than replacing it outright.

    :example:

    .. yaml:

     policies:
      - name: notebook-v2-enforce-idle-timeout
        resource: gcp.notebook-v2
        filters:
          - type: value
            key: gceSetup.metadata."idle-timeout-seconds"
            value: absent
        actions:
          - type: update-metadata
            metadata:
              idle-timeout-seconds: "3600"
    """
    schema = type_schema(
        'update-metadata',
        required=('metadata',),
        metadata={'type': 'object', 'additionalProperties': {'type': 'string'}},
    )
    method_spec = {'op': 'patch'}
    method_perm = 'update'

    def get_resource_params(self, model, resource):
        metadata = dict(resource.get('gceSetup', {}).get('metadata') or {})
        metadata.update(self.data['metadata'])
        return {
            'name': resource['name'],
            'updateMask': 'gceSetup.metadata',
            'body': {'gceSetup': {'metadata': metadata}},
        }
