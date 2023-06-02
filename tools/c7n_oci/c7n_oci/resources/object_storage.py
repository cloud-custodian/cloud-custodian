# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

import oci.object_storage

from c7n.utils import type_schema
from c7n_oci.actions.base import OCIBaseAction, RemoveTagBaseAction
from c7n_oci.provider import resources
from c7n_oci.query import QueryResourceManager

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
        enum_spec = ("list_buckets", "items[]", None)
        extra_params = {"compartment_id", "namespace_name"}
        resource_type = "OCI.ObjectStorage/Bucket"
        id = "identifier"
        name = "display_name"
        search_resource_type = "bucket"

    def _construct_query_params(self):
        default_filters = super().get_default_filters()
        """ Only return the params that are eligible to be passed to the api, as defined in extra_params """
        default_filters = dict(
            (k, v)
            for k, v in default_filters.items()
            if k in self.resource_type.extra_params
        )
        return default_filters


@Bucket.action_registry.register("update_bucket")
class UpdateBucket(OCIBaseAction):
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
                    - type: update_bucket

    """

    schema = type_schema(
        "update_bucket", params={"type": "object"}, rinherit=OCIBaseAction.schema
    )

    def perform_action(self, resource):
        client = self.manager.get_client()
        params_dict = {}
        params_model = {}
        additional_details = resource.get("additional_details")
        if self.data.get("params") and self.data.get("params").get("namespace_name"):
            params_dict["namespace_name"] = self.data.get("params").get(
                "namespace_name"
            )
        else:
            params_dict["namespace_name"] = resource.get(
                "namespace", additional_details.get("namespace")
            )
        if self.data.get("params") and self.data.get("params").get("bucket_name"):
            params_dict["bucket_name"] = self.data.get("params").get("bucket_name")
        else:
            params_dict["bucket_name"] = resource.get(
                "display_name", additional_details.get("display_name")
            )
        if self.data.get("params").get("update_bucket_details"):
            update_bucket_details_user = self.data.get("params").get(
                "update_bucket_details"
            )
            params_model = self.update_params(resource, update_bucket_details_user)
            params_dict[
                "update_bucket_details"
            ] = oci.object_storage.models.UpdateBucketDetails(**params_model)
        response = client.update_bucket(
            namespace_name=params_dict["namespace_name"],
            bucket_name=params_dict["bucket_name"],
            update_bucket_details=params_dict["update_bucket_details"],
        )
        log.info(
            f"Received status {response.status} for POST:update_bucket {response.request_id}"
        )
        return response


@Bucket.action_registry.register("remove_tag")
class RemoveTagAction(RemoveTagBaseAction):
    """
    Remove Tag Action

    :example:

        Remove the specified tags from the resource. Defined tag needs to be referred as 'namespace.tagName' as below in the policy file.

    .. code-block:: yaml

        policies:
            - name: remove-tag
              resource: oci.bucket
            actions:
              - type: remove_tag
                defined_tags: ['cloud_custodian.environment']
                freeform_tags: ['organization', 'team']

    """

    def perform_action(self, resource):
        client = self.manager.get_client()
        params_dict = {}
        additional_details = resource.get("additional_details")
        params_dict["namespace_name"] = resource.get(
            "namespace", additional_details.get("namespace")
        )
        params_dict["bucket_name"] = resource.get(
            "display_name", additional_details.get("display_name")
        )
        original_tag_count = self.tag_count(resource)
        params_model = self.remove_tag(resource)
        updated_tag_count = self.tag_count(params_model)
        params_dict[
            "update_bucket_details"
        ] = oci.object_storage.models.UpdateBucketDetails(**params_model)
        if self.tag_removed_from_resource(original_tag_count, updated_tag_count):
            response = client.update_bucket(
                namespace_name=params_dict["namespace_name"],
                bucket_name=params_dict["bucket_name"],
                update_bucket_details=params_dict["update_bucket_details"],
            )
            log.info(
                f"Received status {response.status} for POST:update_bucket:remove_tag {response.request_id}"
            )
            return response
        else:
            log.info(
                "No tags matched. Skipping the remove_tag action on this resource - %s",
                resource.get("display_name"),
            )
            return None
