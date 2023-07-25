# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging
import re  # noqa
import copy  # noqa

import oci.object_storage

from c7n.filters import Filter, ValueFilter  # noqa
from c7n.utils import type_schema
from c7n_oci.actions.base import OCIBaseAction, RemoveTagBaseAction
from c7n_oci.provider import resources
from c7n_oci.query import QueryResourceManager
from c7n_oci.constants import STORAGE_NAMESPACE

log = logging.getLogger("custodian.oci.resources.object_storage")


@resources.register("bucket")
class Bucket(QueryResourceManager):
    """Oracle Cloud Infrastructure Bucket Resource

    :example:

    Returns all Bucket resources in the tenancy

    .. code-block:: yaml

        policies:
            - name: find-all-bucket-resources
              resource: oci.bucket

    """

    class resource_type:
        doc_groups = ["ObjectStorage"]
        service = "oci.object_storage"
        client = "ObjectStorageClient"
        enum_spec = ("list_buckets", "items[]", {"fields": ["tags"]})
        extra_params = {"compartment_id", "namespace_name"}
        resource_type = "OCI.ObjectStorage/Bucket"
        id = name = "name"
        search_resource_type = "bucket"

    def _get_extra_params(self):
        kw = {}
        kw[STORAGE_NAMESPACE] = self.get_client().get_namespace().data
        return kw


@Bucket.action_registry.register("update")
class UpdateBucketAction(OCIBaseAction):
    """
        Update bucket Action

        :example:

        Performs a partial or full update of a bucket's user-defined metadata.

    Use UpdateBucket to move a bucket from one compartment to another within the same tenancy. Supply the compartmentID
    of the compartment that you want to move the bucket to. For more information about moving resources between compartments,
    see [Moving Resources to a Different Compartment](/iaas/Content/Identity/Tasks/managingcompartments.htm#moveRes).


        Please refer to the Oracle Cloud Infrastructure Python SDK documentation for parameter details to this action
        https://docs.oracle.com/en-us/iaas/tools/python/latest/api/object_storage/client/oci.object_storage.ObjectStorageClient.html#oci.object_storage.ObjectStorageClient.update_bucket

        .. code-block:: yaml

            policies:
                - name: perform-update-bucket-action
                  resource: oci.bucket
                  actions:
                    - type: update
                      defined_tags:
                         Cloud_Custodian: True
                      freeform_tags:
                         Environment: development
                      public_access_type: "NoPublicAccess"


    """  # noqa

    schema = type_schema(
        "update",
        **{
            "freeform_tags": {"type": "object"},
            "defined_tags": {"type": "object"},
            "public_access_type": {"type": "string"},
        },
    )

    def perform_action(self, resource):
        client = self.manager.get_client()
        update_bucket_details_user = self.extract_params(self.data)
        params_model = self.update_params(resource, update_bucket_details_user)
        update_bucket_details = oci.object_storage.models.UpdateBucketDetails(**params_model)
        response = client.update_bucket(
            namespace_name=resource.get("namespace"),
            bucket_name=resource.get("name"),
            update_bucket_details=update_bucket_details,
        )
        log.info(f"Received status {response.status} for POST:update_bucket {response.request_id}")
        return response


@Bucket.action_registry.register("remove-tag")
class RemoveTagActionBucket(RemoveTagBaseAction):
    """
    Remove Tag Action

    :example:

        Remove the specified tags from the resource. Defined tag needs to be referred as 'namespace.tagName' as below in the policy file.

    .. code-block:: yaml

        policies:
            - name: remove-tag
              resource: oci.bucket
            actions:
              - type: remove-tag
                defined_tags: ['cloud_custodian.environment']
                freeform_tags: ['organization', 'team']

    """  # noqa

    def perform_action(self, resource):
        client = self.manager.get_client()
        params_dict = {}
        params_dict["namespace_name"] = resource.get("namespace")
        params_dict["bucket_name"] = resource.get("name")
        original_tag_count = self.tag_count(resource)
        params_model = self.remove_tag(resource)
        updated_tag_count = self.tag_count(params_model)
        params_dict["update_bucket_details"] = oci.object_storage.models.UpdateBucketDetails(
            **params_model
        )
        if self.tag_removed_from_resource(original_tag_count, updated_tag_count):
            response = client.update_bucket(
                namespace_name=params_dict["namespace_name"],
                bucket_name=params_dict["bucket_name"],
                update_bucket_details=params_dict["update_bucket_details"],
            )
            log.debug(
                f"Received status {response.status} for POST:update_bucket:remove-tag"
                f" {response.request_id}"
            )
            return response
        else:
            log.debug(
                "No tags matched. Skipping the remove-tag action on this resource - %s",
                resource.get("name"),
            )
            return None


@Bucket.filter_registry.register("attributes")
class AttributesValueFilter(ValueFilter):
    """
    Get all the attributes attached to this resources

    :example:

        Get all the attributes associated with this Bucket resource

    .. code-block:: yaml

        policies:
            - name: get-bucket-attributes
              resource: oci.bucket
              filters:
                - type: attributes
                  key: attr1
                  value: value1
    """

    schema = type_schema("attributes", rinherit=ValueFilter.schema)

    def process(self, resources, event):
        result = []
        for resource in resources:
            response = self.manager.get_client().get_bucket(
                namespace_name=resource.get("namespace"),
                bucket_name=resource.get("name"),
            )
            bucket = oci.util.to_dict(response.data)
            resource = {**resource, **bucket}
            result.append(resource)
        return super().process(result)
