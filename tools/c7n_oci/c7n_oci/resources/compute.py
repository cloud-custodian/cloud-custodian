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

log = logging.getLogger("custodian.oci.resources.compute")


@resources.register("instance")
class Instance(QueryResourceManager):
    """Oracle Cloud Infrastructure Instance Resource

    :example:

    Returns all Instance resources in the tenancy

    .. code-block:: yaml

        policies:
            - name: find-all-instance-resources
              resource: oci.instance

    """

    class resource_type:
        doc_groups = ["Compute"]
        service = "oci.core"
        client = "ComputeClient"
        enum_spec = ("list_instances", "items[]", None)
        extra_params = {"compartment_id", "instance_id"}
        resource_type = "OCI.Compute/Instance"
        id = "id"
        name = "display_name"
        search_resource_type = "instance"


@Instance.filter_registry.register("monitoring")
class InstanceMonitoring(Filter):
    """
    Instance Monitoring Filter

    :example:

    This filter returns the resources with the aggregated data that match the criteria specified in the request.
    Compartment OCID required. For information on metric queries, see `Building Metric Queries
    <https://docs.oracle.com/en-us/iaas/Content/Monitoring/Tasks/buildingqueries.htm>`_.

    .. code-block:: yaml

        policies:
            - name: instance-with-low-cpu-utilization
            description: |
                Return the instances with the low CPU utilization
            resource: oci.instance
            filters:
                - type: monitoring
                  query: 'CpuUtilization[30d].mean() < 6'

    """  # noqa

    schema = type_schema("monitoring", query={"type": "string"}, required=["query"])

    def process(self, resources, event):
        summarize_metrics = oci.monitoring.models.SummarizeMetricsDataDetails(
            query=self.data.get("query"),
            namespace="oci_computeagent",
        )
        monitoring_client = self.manager.get_session().get_monitoring_client()
        comp_resources = {}
        result = []
        for resource in resources:
            comp_id = resource.get("compartment_id")
            if comp_id in comp_resources:
                comp_resources.get(comp_id).append(resource)
            else:
                comp_resources[comp_id] = [resource]
        # Query the MonitoringClient with the query against each compartment and perform
        # the filtering
        for compartment_id in comp_resources.keys():
            metric_response = monitoring_client.summarize_metrics_data(
                compartment_id=compartment_id,
                summarize_metrics_data_details=summarize_metrics,
            )
            for metric_data in metric_response.data:
                resource_id = metric_data.dimensions["resourceId"]
                for resource in comp_resources.get(compartment_id):
                    if resource.get("id") == resource_id:
                        result.append(resource)
        return result


@Instance.action_registry.register("instance-action")
class InstanceAction(OCIBaseAction):
    """
        Instance action Action

        :example:

        Performs one of the following power actions on the specified instance:

    - **START** - Powers on the instance.

    - **STOP** - Powers off the instance.

    - **RESET** - Powers off the instance and then powers it back on.

    - **SOFTSTOP** - Gracefully shuts down the instance by sending a shutdown command to the operating system. After waiting 15 minutes for the OS to shut down, the instance is powered off. If the applications that run on the instance take more than 15 minutes to shut down, they could be improperly stopped, resulting in data corruption. To avoid this, manually shut down the instance using the commands available in the OS before you softstop the instance.

    - **SOFTRESET** - Gracefully reboots the instance by sending a shutdown command to the operating system.After waiting 15 minutes for the OS to shut down, the instance is powered off and then powered back on.

    - **SENDDIAGNOSTICINTERRUPT** - For advanced users. **Caution: Sending a diagnostic interrupt to a live system can cause data corruption or system failure.** Sends a diagnostic interrupt that causes the instance's OS to crash and then reboot. Before you send a diagnostic interrupt, you must configure the instance to generate a crash dump file when it crashes. The crash dump captures information about the state of the OS at the time of the crash. After the OS restarts, you can analyze the crash dump to diagnose the issue. For more information, see [Sending a Diagnostic Interrupt](/iaas/Content/Compute/Tasks/sendingdiagnosticinterrupt.htm).

    - **DIAGNOSTICREBOOT** - Powers off the instance, rebuilds it, and then powers it back on. Before you send a diagnostic reboot, restart the instance's OS, confirm that the instance and networking settings are configured correctly, and try other [troubleshooting steps](/iaas/Content/Compute/References/troubleshooting-compute-instances.htm). Use diagnostic reboot as a final attempt to troubleshoot an unreachable instance. For virtual machine (VM) instances only. For more information, see [Performing a Diagnostic Reboot](/iaas/Content/Compute/Tasks/diagnostic-reboot.htm).

    - **REBOOTMIGRATE** - Powers off the instance, moves it to new hardware, and then powers it back on. For more information, see [Infrastructure Maintenance](/iaas/Content/Compute/References/infrastructure-maintenance.htm).


    For more information about managing instance lifecycle states, see
    [Stopping and Starting an Instance](/iaas/Content/Compute/Tasks/restartinginstance.htm).


        Please refer to the Oracle Cloud Infrastructure Python SDK documentation for parameter details to this action
        https://docs.oracle.com/en-us/iaas/tools/python/latest/api/core/client/oci.core.ComputeClient.html#oci.core.ComputeClient.instance_action

        .. code-block:: yaml

            policies:
                - name: perform-instance-action-action
                  resource: oci.instance
                  actions:
                    - type: instance-action

    """  # noqa

    schema = type_schema(
        "instance-action", params={"type": "object"}, rinherit=OCIBaseAction.schema
    )

    def perform_action(self, resource):
        client = self.manager.get_client()
        params_dict = {}
        params_model = {}
        params_dict["instance_id"] = resource.get("id")
        if self.data.get("params") and self.data.get("params").get("action"):
            params_dict["action"] = self.data.get("params").get("action")
        else:
            params_dict["action"] = resource.get("action")
        if self.data.get("params").get("instance_power_action_details"):
            instance_power_action_details_user = self.data.get("params").get(
                "instance_power_action_details"
            )
            if instance_power_action_details_user.get("action_type"):
                params_dict["action_type"] = instance_power_action_details_user.get("action_type")
            params_model = self.update_params(resource, instance_power_action_details_user)
            params_dict[
                "instance_power_action_details"
            ] = oci.core.models.InstancePowerActionDetails(**params_model)
        response = client.instance_action(
            instance_id=params_dict["instance_id"],
            action=params_dict["action"],
        )
        log.info(
            f"Received status {response.status} for POST:instance_action {response.request_id}"
        )
        return response


@Instance.action_registry.register("update-instance")
class UpdateInstance(OCIBaseAction):
    """
    Update instance Action

    :example:

    Updates certain fields on the specified instance. Fields that are not provided in the request will not be updated. Avoid entering confidential information.

    Changes to metadata fields will be reflected in the instance metadata service (this may take up to a minute).

    The OCID of the instance remains the same.


    Please refer to the Oracle Cloud Infrastructure Python SDK documentation for parameter details to this action
    https://docs.oracle.com/en-us/iaas/tools/python/latest/api/core/client/oci.core.ComputeClient.html#oci.core.ComputeClient.update_instance

    .. code-block:: yaml

        policies:
            - name: perform-update-instance-action
              resource: oci.instance
              actions:
                - type: update-instance

    """  # noqa

    schema = type_schema(
        "update-instance", params={"type": "object"}, rinherit=OCIBaseAction.schema
    )

    def perform_action(self, resource):
        client = self.manager.get_client()
        params_dict = {}
        params_model = {}
        params_dict["instance_id"] = resource.get("id")
        if self.data.get("params").get("update_instance_details"):
            update_instance_details_user = self.data.get("params").get("update_instance_details")
            params_model = self.update_params(resource, update_instance_details_user)
            params_dict["update_instance_details"] = oci.core.models.UpdateInstanceDetails(
                **params_model
            )
        response = client.update_instance(
            instance_id=params_dict["instance_id"],
            update_instance_details=params_dict["update_instance_details"],
        )
        log.info(f"Received status {response.status} for PUT:update_instance {response.request_id}")
        return response


@Instance.action_registry.register("remove-tag")
class RemoveTagActionInstance(RemoveTagBaseAction):
    """
    Remove Tag Action

    :example:

        Remove the specified tags from the resource. Defined tag needs to be referred as 'namespace.tagName' as below in the policy file.

    .. code-block:: yaml

        policies:
            - name: remove-tag
              resource: oci.instance
            actions:
              - type: remove-tag
                defined_tags: ['cloud_custodian.environment']
                freeform_tags: ['organization', 'team']

    """  # noqa

    def perform_action(self, resource):
        client = self.manager.get_client()
        params_dict = {}
        params_dict["instance_id"] = resource.get("id")
        original_tag_count = self.tag_count(resource)
        params_model = self.remove_tag(resource)
        updated_tag_count = self.tag_count(params_model)
        params_dict["update_instance_details"] = oci.core.models.UpdateInstanceDetails(
            **params_model
        )
        if self.tag_removed_from_resource(original_tag_count, updated_tag_count):
            response = client.update_instance(
                instance_id=params_dict["instance_id"],
                update_instance_details=params_dict["update_instance_details"],
            )
            log.debug(
                f"Received status {response.status} for PUT:update_instance:remove-tag"
                f" {response.request_id}"
            )
            return response
        else:
            log.debug(
                "No tags matched. Skipping the remove-tag action on this resource - %s",
                resource.get("display_name"),
            )
            return None
