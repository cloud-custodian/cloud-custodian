# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
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
