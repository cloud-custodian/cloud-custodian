# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging
import re  # noqa
import copy  # noqa

import oci.core

from c7n.filters import Filter, ValueFilter  # noqa
from c7n.utils import type_schema
from c7n_oci.actions.base import OCIBaseAction, RemoveTagBaseAction
from c7n_oci.provider import resources
from c7n_oci.query import QueryResourceManager

log = logging.getLogger("custodian.oci.resources.virtual_network")


@resources.register("cross_connect")
class Cross_connect(QueryResourceManager):
    """Oracle Cloud Infrastructure Cross_connect Resource

    :example:

    Returns all Cross_connect resources in the tenancy

    .. code-block:: yaml

        policies:
            - name: find-all-cross_connect-resources
              resource: oci.cross_connect

    """

    class resource_type:
        doc_groups = ["Network"]
        service = "oci.core"
        client = "VirtualNetworkClient"
        enum_spec = ("list_cross_connects", "items[]", None)
        extra_params = {"compartment_id"}
        resource_type = "OCI.VirtualNetwork/Cross_connect"
        id = "id"
        name = "display_name"
        search_resource_type = "crossconnect"


Cross_connect.action_registry.register("update")


class UpdateCrossConnectAction(OCIBaseAction):
    """
    Update cross connect Action

    :example:

    Updates the specified cross-connect.

    Please refer to the Oracle Cloud Infrastructure Python SDK documentation for parameter details to this action
    https://docs.oracle.com/en-us/iaas/tools/python/latest/api/core/client/oci.core.VirtualNetworkClient.html#oci.core.VirtualNetworkClient.update_cross_connect

    .. code-block:: yaml

        policies:
            - name: perform-update-cross-connect-action
              resource: oci.cross_connect
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
        update_cross_connect_details_user = self.extract_params(self.data)
        params_model = self.update_params(resource, update_cross_connect_details_user)
        update_cross_connect_details = oci.core.models.UpdateCrossConnectDetails(**params_model)
        response = client.update_cross_connect(
            cross_connect_id=resource.get("id"),
            update_cross_connect_details=update_cross_connect_details,
        )
        log.info(
            f"Received status {response.status} for PUT:update_cross_connect {response.request_id}"
        )
        return response


@Cross_connect.action_registry.register("remove-tag")
class RemoveTagActionCross_connect(RemoveTagBaseAction):
    """
    Remove Tag Action

    :example:

        Remove the specified tags from the resource. Defined tag needs to be referred as 'namespace.tagName' as below in the policy file.

    .. code-block:: yaml

        policies:
            - name: remove-tag
              resource: oci.cross_connect
            actions:
              - type: remove-tag
                defined_tags: ['cloud_custodian.environment']
                freeform_tags: ['organization', 'team']

    """  # noqa

    def perform_action(self, resource):
        client = self.manager.get_client()
        params_dict = {}
        params_dict["cross_connect_id"] = resource.get("id")
        original_tag_count = self.tag_count(resource)
        params_model = self.remove_tag(resource)
        updated_tag_count = self.tag_count(params_model)
        params_dict["update_cross_connect_details"] = oci.core.models.UpdateCrossConnectDetails(
            **params_model
        )
        if self.tag_removed_from_resource(original_tag_count, updated_tag_count):
            response = client.update_cross_connect(
                cross_connect_id=params_dict["cross_connect_id"],
                update_cross_connect_details=params_dict["update_cross_connect_details"],
            )
            log.debug(
                f"Received status {response.status} for PUT:update_cross_connect:remove-tag"
                f" {response.request_id}"
            )
            return response
        else:
            log.debug(
                "No tags matched. Skipping the remove-tag action on this resource - %s",
                resource.get("display_name"),
            )
            return None


@resources.register("vcn")
class Vcn(QueryResourceManager):
    """Oracle Cloud Infrastructure Vcn Resource

    :example:

    Returns all Vcn resources in the tenancy

    .. code-block:: yaml

        policies:
            - name: find-all-vcn-resources
              resource: oci.vcn

    """

    class resource_type:
        doc_groups = ["Network"]
        service = "oci.core"
        client = "VirtualNetworkClient"
        enum_spec = ("list_vcns", "items[]", None)
        extra_params = {"compartment_id"}
        resource_type = "OCI.VirtualNetwork/Vcn"
        id = "id"
        name = "display_name"
        search_resource_type = "vcn"


@Vcn.action_registry.register("update")
class UpdateVcnAction(OCIBaseAction):
    """
    Update vcn Action

    :example:

    Updates the specified VCN.


    Please refer to the Oracle Cloud Infrastructure Python SDK documentation for parameter details to this action
    https://docs.oracle.com/en-us/iaas/tools/python/latest/api/core/client/oci.core.VirtualNetworkClient.html#oci.core.VirtualNetworkClient.update_vcn

    .. code-block:: yaml

        policies:
            - name: perform-update-vcn-action
              resource: oci.vcn
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
        update_vcn_details_user = self.extract_params(self.data)
        params_model = self.update_params(resource, update_vcn_details_user)
        update_vcn_details = oci.core.models.UpdateVcnDetails(**params_model)
        response = client.update_vcn(
            vcn_id=resource.get("id"), update_vcn_details=update_vcn_details
        )
        log.info(f"Received status {response.status} for PUT:update_vcn {response.request_id}")
        return response


@Vcn.action_registry.register("remove-tag")
class RemoveTagActionVcn(RemoveTagBaseAction):
    """
    Remove Tag Action

    :example:

        Remove the specified tags from the resource. Defined tag needs to be referred as 'namespace.tagName' as below in the policy file.

    .. code-block:: yaml

        policies:
            - name: remove-tag
              resource: oci.vcn
            actions:
              - type: remove-tag
                defined_tags: ['cloud_custodian.environment']
                freeform_tags: ['organization', 'team']

    """  # noqa

    def perform_action(self, resource):
        client = self.manager.get_client()
        params_dict = {}
        params_dict["vcn_id"] = resource.get("id")
        original_tag_count = self.tag_count(resource)
        params_model = self.remove_tag(resource)
        updated_tag_count = self.tag_count(params_model)
        params_dict["update_vcn_details"] = oci.core.models.UpdateVcnDetails(**params_model)
        if self.tag_removed_from_resource(original_tag_count, updated_tag_count):
            response = client.update_vcn(
                vcn_id=params_dict["vcn_id"],
                update_vcn_details=params_dict["update_vcn_details"],
            )
            log.debug(
                f"Received status {response.status} for PUT:update_vcn:remove-tag"
                f" {response.request_id}"
            )
            return response
        else:
            log.debug(
                "No tags matched. Skipping the remove-tag action on this resource - %s",
                resource.get("display_name"),
            )
            return None


@resources.register("subnet")
class Subnet(QueryResourceManager):
    """Oracle Cloud Infrastructure Subnet Resource

    :example:

    Returns all Subnet resources in the tenancy

    .. code-block:: yaml

        policies:
            - name: find-all-subnet-resources
              resource: oci.subnet

    """

    class resource_type:
        doc_groups = ["Network"]
        service = "oci.core"
        client = "VirtualNetworkClient"
        enum_spec = ("list_subnets", "items[]", None)
        extra_params = {"compartment_id"}
        resource_type = "OCI.VirtualNetwork/Subnet"
        id = "id"
        name = "display_name"
        search_resource_type = "subnet"


@Subnet.action_registry.register("update")
class UpdateSubnetAction(OCIBaseAction):
    """
    Update subnet Action

    :example:

    Updates the specified subnet.


    Please refer to the Oracle Cloud Infrastructure Python SDK documentation for parameter details to this action
    https://docs.oracle.com/en-us/iaas/tools/python/latest/api/core/client/oci.core.VirtualNetworkClient.html#oci.core.VirtualNetworkClient.update_subnet

    .. code-block:: yaml

        policies:
            - name: perform-update-subnet-action
              resource: oci.subnet
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
        update_subnet_details_user = self.extract_params(self.data)
        params_model = self.update_params(resource, update_subnet_details_user)
        update_subnet_details = oci.core.models.UpdateSubnetDetails(**params_model)
        response = client.update_subnet(
            subnet_id=resource.get("id"), update_subnet_details=update_subnet_details
        )
        log.info(f"Received status {response.status} for PUT:update_subnet {response.request_id}")
        return response


@Subnet.action_registry.register("remove-tag")
class RemoveTagActionSubnet(RemoveTagBaseAction):
    """
    Remove Tag Action

    :example:

        Remove the specified tags from the resource. Defined tag needs to be referred as 'namespace.tagName' as below in the policy file.

    .. code-block:: yaml

        policies:
            - name: remove-tag
              resource: oci.subnet
            actions:
              - type: remove-tag
                defined_tags: ['cloud_custodian.environment']
                freeform_tags: ['organization', 'team']

    """  # noqa

    def perform_action(self, resource):
        client = self.manager.get_client()
        params_dict = {}
        params_dict["subnet_id"] = resource.get("id")
        original_tag_count = self.tag_count(resource)
        params_model = self.remove_tag(resource)
        updated_tag_count = self.tag_count(params_model)
        params_dict["update_subnet_details"] = oci.core.models.UpdateSubnetDetails(**params_model)
        if self.tag_removed_from_resource(original_tag_count, updated_tag_count):
            response = client.update_subnet(
                subnet_id=params_dict["subnet_id"],
                update_subnet_details=params_dict["update_subnet_details"],
            )
            log.debug(
                f"Received status {response.status} for PUT:update_subnet:remove-tag"
                f" {response.request_id}"
            )
            return response
        else:
            log.debug(
                "No tags matched. Skipping the remove-tag action on this resource - %s",
                resource.get("display_name"),
            )
            return None
