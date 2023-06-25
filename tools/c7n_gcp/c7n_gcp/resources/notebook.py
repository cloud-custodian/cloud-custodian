# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo


@resources.register('notebook-instance')
class NotebookInstance(QueryResourceManager):
    """ GC resource: https://cloud.google.com/vertex-ai/docs/workbench/reference/rest

    GCP Vertex AI Workbench has public IPs.

    :example: GCP Vertex AI Workbench has public IPs

    .. yaml:

     policies:
      - name: epam-gcp-vertex-ai-workbench-does-not-have-public-ips
        description: |
          GCP Vertex AI Workbench has public IPs
        resource: gcp.notebook-instance
        filters:
          - type: value
            key: noPublicIp
            op: ne
            value: true
    """
    class resource_type(TypeInfo):
        service = 'notebooks'
        version = 'v1'
        component = 'projects.locations.instances'
        enum_spec = ('list', 'instances[]', None)
        scope_key = 'parent'
        name = id = 'id'
        scope_template = "projects/{}/locations/-"
        permissions = ('notebooks.instances.list',)
        default_report_fields = ['displayName', 'expireTime']
