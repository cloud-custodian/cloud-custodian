# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging

import oci.dns

from c7n.utils import type_schema
from c7n_oci.actions.base import OCIBaseAction, RemoveTagBaseAction
from c7n_oci.provider import resources
from c7n_oci.query import QueryResourceManager

log = logging.getLogger("custodian.oci.resources.dns")


@resources.register("zone")
class Zone(QueryResourceManager):
    """Oracle Cloud Infrastructure Zone Resource

    :example:

    Returns all Zone resources in the tenancy

    .. code-block:: yaml

        policies:
            - name: find-all-zone-resources
              resource: oci.zone

    """

    class resource_type:
        doc_groups = ["DNS"]
        service = "oci.dns"
        client = "DnsClient"
        enum_spec = ("list_zones", "items[]", None)
        extra_params = {"compartment_id"}
        resource_type = "OCI.Dns/Zone"
        id = "identifier"
        name = "display_name"
        search_resource_type = "customerdnszone"


@Zone.action_registry.register("update_zone")
class UpdateZone(OCIBaseAction):
    """
        Update zone Action

        :example:

        Updates the zone with the specified information.

    Global secondary zones may have their external masters updated. For more information about secondary
    zones, see [Manage DNS Service Zone](/iaas/Content/DNS/Tasks/managingdnszones.htm). When the zone name
    is provided as a path parameter and `PRIVATE` is used for the scope query parameter then the viewId
    query parameter is required.


        Please refer to the Oracle Cloud Infrastructure Python SDK documentation for parameter details to this action
        https://docs.oracle.com/en-us/iaas/tools/python/latest/api/dns/client/oci.dns.DnsClient.html#oci.dns.DnsClient.update_zone

        .. code-block:: yaml

            policies:
                - name: perform-update-zone-action
                  resource: oci.zone
                  actions:
                    - type: update_zone

    """

    schema = type_schema(
        "update_zone", params={"type": "object"}, rinherit=OCIBaseAction.schema
    )

    def perform_action(self, resource):
        client = self.manager.get_client()
        params_dict = {}
        params_model = {}
        additional_details = resource.get("additional_details")
        if self.data.get("params") and self.data.get("params").get("zone_name_or_id"):
            params_dict["zone_name_or_id"] = self.data.get("params").get(
                "zone_name_or_id"
            )
        else:
            params_dict["zone_name_or_id"] = resource.get(
                "identifier", additional_details.get("identifier")
            )
        if self.data.get("params").get("update_zone_details"):
            update_zone_details_user = self.data.get("params").get(
                "update_zone_details"
            )
            params_model = self.update_params(resource, update_zone_details_user)
            params_dict["update_zone_details"] = oci.dns.models.UpdateZoneDetails(
                **params_model
            )
        if self.data.get("params") and self.data.get("params").get("scope"):
            params_dict["scope"] = self.data.get("params").get("scope")
        if self.data.get("params") and self.data.get("params").get("view_id"):
            params_dict["view_id"] = self.data.get("params").get("view_id")
        if self.data.get("params") and self.data.get("params").get("compartment_id"):
            params_dict["compartment_id"] = self.data.get("params").get(
                "compartment_id"
            )
        response = client.update_zone(
            zone_name_or_id=params_dict["zone_name_or_id"],
            update_zone_details=params_dict["update_zone_details"],
        )
        log.info(
            f"Received status {response.status} for PUT:update_zone {response.request_id}"
        )
        return response


@Zone.action_registry.register("remove_tag")
class RemoveTagActionZone(RemoveTagBaseAction):
    """
    Remove Tag Action

    :example:

        Remove the specified tags from the resource. Defined tag needs to be referred as 'namespace.tagName' as below in the policy file.

    .. code-block:: yaml

        policies:
            - name: remove-tag
              resource: oci.zone
            actions:
              - type: remove_tag
                defined_tags: ['cloud_custodian.environment']
                freeform_tags: ['organization', 'team']

    """

    def perform_action(self, resource):
        client = self.manager.get_client()
        params_dict = {}
        additional_details = resource.get("additional_details")
        params_dict["zone_name_or_id"] = resource.get(
            "identifier", additional_details.get("identifier")
        )
        original_tag_count = self.tag_count(resource)
        params_model = self.remove_tag(resource)
        updated_tag_count = self.tag_count(params_model)
        params_dict["update_zone_details"] = oci.dns.models.UpdateZoneDetails(
            **params_model
        )
        if self.tag_removed_from_resource(original_tag_count, updated_tag_count):
            response = client.update_zone(
                zone_name_or_id=params_dict["zone_name_or_id"],
                update_zone_details=params_dict["update_zone_details"],
            )
            log.info(
                f"Received status {response.status} for PUT:update_zone:remove_tag {response.request_id}"
            )
            return response
        else:
            log.info(
                "No tags matched. Skipping the remove_tag action on this resource - %s",
                resource.get("display_name"),
            )
            return None
