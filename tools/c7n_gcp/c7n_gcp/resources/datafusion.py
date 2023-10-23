# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.provider import resources
from c7n_gcp.query import (QueryResourceManager, TypeInfo)


@resources.register('datafusion-instance')
class DatafusionInstance(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'datafusion'
        version = 'v1'
        component = 'projects.locations.instances'
        enum_spec = ('list', 'instances[]', None)
        scope = 'project'
        scope_key = 'parent'
        scope_template = "projects/{}/locations/-"
        name = id = "name"
        default_report_fields = ['name', 'updateTime']
        asset_type = "datafusion.googleapis.com/Instance"
        urn_component = "instances"
        urn_id_segments = (-1,)

        @classmethod
        def _get_location(cls, resource):
            return resource['name'].split('/')[3]
