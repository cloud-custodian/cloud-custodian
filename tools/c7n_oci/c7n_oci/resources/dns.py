# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging
import re  # noqa
import copy  # noqa

import oci.dns

from c7n.filters import Filter, ValueFilter  # noqa
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
        id = "id"
        name = "name"
        search_resource_type = "customerdnszone"


@Zone.action_registry.register("update")
class UpdateZoneAction(OCIBaseAction):
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
                    - type: update
                      defined_tags:
                        Cloud_Custodian: True
                      freeform_tags:
                        Environment: development

    """  # noqa

    schema = type_schema(
        "update", **{"freeform_tags": {"type": "object"}, "defined_tags": {"type": "object"}}
    )

    def perform_action(self, resource):
        client = self.manager.get_client()
        update_zone_details_user = self.extract_params(self.data)
        params_model = self.update_params(resource, update_zone_details_user)
        update_zone_details = oci.dns.models.UpdateZoneDetails(**params_model)
        response = client.update_zone(
            zone_name_or_id=resource.get("id"),
            update_zone_details=update_zone_details,
        )
        log.info(f"Received status {response.status} for PUT:update_zone {response.request_id}")
        return response


@Zone.action_registry.register("remove-tag")
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
              - type: remove-tag
                defined_tags: ['cloud_custodian.environment']
                freeform_tags: ['organization', 'team']

    """  # noqa

    def perform_action(self, resource):
        client = self.manager.get_client()
        params_dict = {}
        params_dict["zone_name_or_id"] = resource.get("id")
        original_tag_count = self.tag_count(resource)
        params_model = self.remove_tag(resource)
        updated_tag_count = self.tag_count(params_model)
        params_dict["update_zone_details"] = oci.dns.models.UpdateZoneDetails(**params_model)
        if self.tag_removed_from_resource(original_tag_count, updated_tag_count):
            response = client.update_zone(
                zone_name_or_id=params_dict["zone_name_or_id"],
                update_zone_details=params_dict["update_zone_details"],
            )
            log.debug(
                f"Received status {response.status} for PUT:update_zone:remove-tag"
                f" {response.request_id}"
            )
            return response
        else:
            log.debug(
                "No tags matched. Skipping the remove-tag action on this resource - %s",
                resource.get("name"),
            )
            return None
