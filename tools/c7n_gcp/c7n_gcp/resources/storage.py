# Copyright 2017-2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from c7n.utils import type_schema
from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo


@resources.register('bucket')
class Bucket(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'storage'
        version = 'v1'
        component = 'buckets'
        scope = 'project'
        enum_spec = ('list', 'items[]', {'projection': 'full'})
        name = id = 'name'
        default_report_fields = [
            "name", "timeCreated", "location", "storageClass"]
        asset_type = "storage.googleapis.com/Bucket"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'bucket': resource_info['bucket_name']})


@Bucket.action_registry.register('set-uniform-access')
class BucketLevelAccess(MethodAction):
    '''Uniform access disables object ACLs on a bucket.

    Enabling this means only bucket policies (and organization bucket
    policies) govern access to a bucket.

    When enabled, users can only specify bucket level IAM policies
    and not Object level ACL's.

    Example Policy:

    .. code-block:: yaml

      policies:
       - name: enforce-uniform-bucket-level-access
         resource: gcp.bucket
         filters:
          - iamConfiguration.uniformBucketLevelAccess.enable: false
         actions:
          - type: set-uniform-access
            # The following is also the default
            state: true
    '''

    schema = type_schema('set-uniform-access', state={'type': 'boolean'})
    method_spec = {'op': 'patch'}

    # the google docs and example on this api appear to broken.
    # https://cloud.google.com/storage/docs/using-uniform-bucket-level-access#rest-apis
    #
    # instead we observe the behavior gsutil interaction to effect the same.
    # the key seems to be the undocumented projection parameter
    #
    def get_resource_params(self, model, resource):
        enabled = self.data.get('state', True)
        return {'bucket': resource['name'],
                'fields': 'iamConfiguration',
                'projection': 'noAcl',  # not documented but
                'body': {'iamConfiguration': {'uniformBucketLevelAccess': {'enabled': enabled}}}}
