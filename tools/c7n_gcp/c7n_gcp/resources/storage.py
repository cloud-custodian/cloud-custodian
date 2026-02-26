# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.utils import type_schema
from c7n_gcp.actions import MethodAction
from c7n_gcp.actions.iampolicy import SetIamPolicy
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo
from c7n_gcp.filters import IamPolicyFilter


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
        scc_type = "google.cloud.storage.Bucket"
        metric_key = 'resource.labels.bucket_name'
        urn_component = "bucket"
        labels = True
        labels_op = 'patch'

        @staticmethod
        def get(client, resource_info):
            # pull mode passes the bucket name in the info using bucket_name.
            # gcp-scc mode passes in the full resourceName
            if not (bucket_name := resource_info.get("bucket_name")):
                # There is no nice way to return no resource, so if there is no
                # resourceName in the info, we will raise a KeyError.
                prefix = "//storage.googleapis.com/"
                bucket_name = resource_info["resourceName"].removeprefix(prefix)

            return client.execute_command("get", {"bucket": bucket_name})

        @staticmethod
        def get_label_params(resource, all_labels):
            return {'bucket': resource['name'], 'body': {'labels': all_labels}}


@Bucket.filter_registry.register('iam-policy')
class BucketIamPolicyFilter(IamPolicyFilter):
    """
    Overrides the base implementation to process bucket resources correctly.
    """
    permissions = ('storage.buckets.getIamPolicy',)

    def _verb_arguments(self, resource):
        verb_arguments = {{"bucket": resource["name"]}}
        return verb_arguments


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
    method_perm = 'update'

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


@Bucket.action_registry.register('set-iam-policy')
class BucketSetIamPolicy(SetIamPolicy):
    """Manage GCP bucket IAM policy bindings.

    This action supports ``add-bindings`` and ``remove-bindings`` to manage
    bucket-level IAM policies. A common use case is removing ``allUsers`` and
    ``allAuthenticatedUsers`` from buckets that have been misconfigured with
    public access.

    The ``remove-bindings`` list specifies which members to remove from which
    roles. If removing a member leaves a role binding with no members, that
    binding is dropped entirely. Use ``members: '*'`` as a wildcard to remove
    all members from a role.

    Example policy to detect and remediate publicly accessible buckets.
    To fully remove anonymous and public access, all predefined storage roles
    must be covered:

    .. code-block:: yaml

      policies:
        - name: gcp-bucket-remove-public-access
          resource: gcp.bucket
          filters:
            - type: iam-policy
              doc:
                key: 'bindings[*].members[]'
                op: intersect
                value:
                  - allUsers
                  - allAuthenticatedUsers
          actions:
            - type: set-iam-policy
              remove-bindings:
                - members: [allUsers, allAuthenticatedUsers]
                  role: roles/storage.admin
                - members: [allUsers, allAuthenticatedUsers]
                  role: roles/storage.objectAdmin
                - members: [allUsers, allAuthenticatedUsers]
                  role: roles/storage.objectCreator
                - members: [allUsers, allAuthenticatedUsers]
                  role: roles/storage.objectUser
                - members: [allUsers, allAuthenticatedUsers]
                  role: roles/storage.objectViewer
                - members: [allUsers, allAuthenticatedUsers]
                  role: roles/storage.bucketViewer
                - members: [allUsers, allAuthenticatedUsers]
                  role: roles/storage.folderAdmin
                - members: [allUsers, allAuthenticatedUsers]
                  role: roles/storage.legacyBucketOwner
                - members: [allUsers, allAuthenticatedUsers]
                  role: roles/storage.legacyBucketReader
                - members: [allUsers, allAuthenticatedUsers]
                  role: roles/storage.legacyBucketWriter
                - members: [allUsers, allAuthenticatedUsers]
                  role: roles/storage.legacyObjectOwner
                - members: [allUsers, allAuthenticatedUsers]
                  role: roles/storage.legacyObjectReader
    """

    permissions = ('storage.buckets.getIamPolicy', 'storage.buckets.setIamPolicy')

    def _verb_arguments(self, resource):
        return {'bucket': resource['name']}

    def get_resource_params(self, model, resource):
        params = self._verb_arguments(resource)
        existing_bindings = self._get_existing_bindings(model, resource)
        add_bindings = self.data.get('add-bindings', [])
        remove_bindings = self.data.get('remove-bindings', [])
        bindings_to_set = self._add_bindings(existing_bindings, add_bindings)
        bindings_to_set = self._remove_bindings(bindings_to_set, remove_bindings)
        params['body'] = {'bindings': bindings_to_set} if bindings_to_set else {}
        return params
