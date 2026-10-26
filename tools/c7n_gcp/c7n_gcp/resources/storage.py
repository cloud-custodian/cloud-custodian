# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.exceptions import PolicyValidationError
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
        labels_perm = 'update'

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
        return {"bucket": resource["name"]}


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


@Bucket.action_registry.register('set-public-access-prevention')
class BucketSetPublicAccess(MethodAction):
    '''Set public access prevention on a bucket.

    ``state`` is required and accepts:

    - ``enforced``: requests authorized through ``allUsers`` or
      ``allAuthenticatedUsers`` are rejected. Existing IAM policies and ACLs
      granting that access are left in place but overridden. To remove them,
      also use the ``set-iam-policy`` action with ``remove-bindings``.
    - ``inherited``: public access prevention is determined by the
      ``storage.publicAccessPrevention`` organization policy constraint. If
      that constraint is not enforced, any existing public IAM policies or
      ACLs on the bucket take effect again.

    https://cloud.google.com/storage/docs/public-access-prevention

    Example Policy:

    .. code-block:: yaml

      policies:
       - name: enforce-bucket-public-access-prevention
         resource: gcp.bucket
         filters:
          - type: value
            key: iamConfiguration.publicAccessPrevention
            value: enforced
            op: ne
         actions:
          - type: set-public-access-prevention
            state: enforced
    '''

    schema = type_schema(
        'set-public-access-prevention',
        required=['state'],
        state={'type': 'string', 'enum': ['enforced', 'inherited']})
    method_spec = {'op': 'patch'}
    # buckets.patch requires setIamPolicy in addition to update when
    # changing public access prevention.
    # https://cloud.google.com/storage/docs/json_api/v1/buckets/patch
    permissions = ('storage.buckets.update', 'storage.buckets.setIamPolicy')

    def get_resource_params(self, model, resource):
        return {'bucket': resource['name'],
                'fields': 'iamConfiguration',
                'projection': 'noAcl',
                'body': {'iamConfiguration': {'publicAccessPrevention': self.data['state']}}}


@Bucket.action_registry.register('set-lifecycle-rule')
class BucketSetLifecycleRule(MethodAction):
    '''Add a lifecycle rule to a bucket, keeping its existing rules.

    ``rule`` is one Cloud Storage lifecycle rule, an ``action`` and a
    ``condition``, in the API's format:
    https://cloud.google.com/storage/docs/lifecycle. ``sizeAboveBytes`` and
    ``sizeBelowBytes`` are strings, as the API returns them.

    Buckets that already have the rule are skipped. If a bucket changes while
    the rule is being added, the update fails rather than overwriting the
    change. ``SetStorageClass`` rules and ``matchesStorageClass`` conditions
    are rejected on Autoclass buckets.

    Rules can take up to 24 hours to take effect, and ``age`` counts from each
    object's creation, so a ``Delete`` rule applies to existing objects as
    well as new ones.

    :example:

    Add a 90 day delete rule to buckets that have no lifecycle rules:

    .. code-block:: yaml

        policies:
          - name: gcp-bucket-add-delete-lifecycle-rule
            resource: gcp.bucket
            filters:
              - type: value
                key: lifecycle.rule
                value: absent
            actions:
              - type: set-lifecycle-rule
                rule:
                  action:
                    type: Delete
                  condition:
                    age: 90
    '''

    schema = type_schema(
        'set-lifecycle-rule',
        required=['rule'],
        rule={
            'type': 'object',
            'additionalProperties': False,
            'required': ['action', 'condition'],
            'properties': {
                'action': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['type'],
                    'properties': {
                        'type': {'enum': [
                            'Delete', 'SetStorageClass', 'AbortIncompleteMultipartUpload']},
                        'storageClass': {'enum': [
                            'STANDARD', 'NEARLINE', 'COLDLINE', 'ARCHIVE',
                            'MULTI_REGIONAL', 'REGIONAL', 'DURABLE_REDUCED_AVAILABILITY']},
                    },
                },
                'condition': {
                    'type': 'object',
                    'additionalProperties': False,
                    'minProperties': 1,
                    'properties': {
                        'age': {'type': 'integer', 'minimum': 0},
                        'createdBefore': {
                            'type': 'string', 'pattern': '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'},
                        'customTimeBefore': {
                            'type': 'string', 'pattern': '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'},
                        'daysSinceCustomTime': {'type': 'integer', 'minimum': 0},
                        'daysSinceNoncurrentTime': {'type': 'integer', 'minimum': 0},
                        'isLive': {'type': 'boolean'},
                        'matchesPattern': {'type': 'string'},
                        'matchesPrefix': {'type': 'array', 'items': {'type': 'string'}},
                        'matchesStorageClass': {'type': 'array', 'items': {'type': 'string'}},
                        'matchesSuffix': {'type': 'array', 'items': {'type': 'string'}},
                        'noncurrentTimeBefore': {
                            'type': 'string', 'pattern': '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'},
                        'numNewerVersions': {'type': 'integer', 'minimum': 0},
                        'sizeAboveBytes': {'type': 'string', 'pattern': '^[0-9]+$'},
                        'sizeBelowBytes': {'type': 'string', 'pattern': '^[0-9]+$'},
                    },
                },
            },
        })
    method_spec = {'op': 'patch'}
    permissions = ('storage.buckets.get', 'storage.buckets.update')

    def validate(self):
        super().validate()
        action = self.data['rule']['action']
        condition = self.data['rule']['condition']
        if (action['type'] == 'SetStorageClass') != ('storageClass' in action):
            raise PolicyValidationError(
                "policy:%s action:%s storageClass is required for SetStorageClass "
                "and not allowed otherwise" % (self.manager.ctx.policy.name, self.type))
        if (action['type'] == 'AbortIncompleteMultipartUpload' and
                condition.keys() - {'age', 'matchesPrefix', 'matchesSuffix'}):
            raise PolicyValidationError(
                "policy:%s action:%s AbortIncompleteMultipartUpload only allows the age, "
                "matchesPrefix and matchesSuffix conditions" % (
                    self.manager.ctx.policy.name, self.type))
        return self

    def process_resource_set(self, client, model, resources):
        rule = self.data['rule']
        for resource in resources:
            # Read the rules now: the listed resource can be stale, for example
            # after an earlier action in the same policy added a rule.
            bucket = client.execute_query(
                'get', {'bucket': resource['name'], 'fields': 'lifecycle,metageneration'})
            rules = bucket.get('lifecycle', {}).get('rule', [])
            if rule in rules:
                self.log.info(
                    "policy:%s action:%s bucket:%s already has the rule",
                    self.manager.ctx.policy.name, self.type, resource['name'])
                continue
            self.invoke_api(client, 'patch', {
                'bucket': resource['name'],
                'ifMetagenerationMatch': bucket['metageneration'],
                'fields': 'lifecycle',
                'projection': 'noAcl',
                'body': {'lifecycle': {'rule': rules + [rule]}}})


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
        if remove_bindings == 'matched':
            matched_pairs = resource.get(IamPolicyFilter.annotation_key, [])
            bindings_to_set = self._remove_matched_bindings(bindings_to_set, matched_pairs)
        else:
            bindings_to_set = self._remove_bindings(bindings_to_set, remove_bindings)
        params['body'] = {'bindings': bindings_to_set} if bindings_to_set else {}
        return params
