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


@Instance.action_registry.register("remove-tag")
class RemoveTagActionInstance(RemoveTagBaseAction):
    """
    Remove Tag Action

    :example:

        Remove the specified tags from the resource. Defined tag needs to be referred as
        'namespace.tagName' as below in the policy file.

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
        original_tag_count = self.tag_count(resource)
        params_model = self.remove_tag(resource)
        updated_tag_count = self.tag_count(params_model)
        update_instance_details = oci.core.models.UpdateInstanceDetails(**params_model)
        if self.tag_removed_from_resource(original_tag_count, updated_tag_count):
            response = client.update_instance(
                instance_id=resource.get("id"),
                update_instance_details=update_instance_details,
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


@Instance.action_registry.register("start")
class InstanceStart(OCIBaseAction):
    """Starts a stopped compute instance.

    :Example:

    .. code-block:: yaml

        policies:
          - name: start-compute-instance
            resource: oci.instance
            actions:
              - start

    https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/restartinginstance.htm
    """

    schema = type_schema("start", rinherit=OCIBaseAction.schema)

    def perform_action(self, resource):
        client = self.manager.get_client()
        response = client.instance_action(
            instance_id=resource["id"],
            action="START",
        )
        log.info(f"Received status {response.status} for POST:START {response.request_id}")
        return response


@Instance.action_registry.register("stop")
class InstanceStop(OCIBaseAction):
    """Stops a running compute instance.

    :Example:

    .. code-block:: yaml

        policies:
          - name: stop-compute-instance
            resource: oci.instance
            actions:
              - stop

          - name: force-stop-compute-instance
            resource: oci.instance
            actions:
              - type: stop
                force: true

    If 'force' option is passed, then a compute instance will be stopped immediately.

    https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/restartinginstance.htm
    """

    schema = type_schema("stop", force={"type": "boolean"})

    def perform_action(self, resource):
        client = self.manager.get_client()
        action = "STOP" if self.data.get("force") else "SOFTSTOP"
        response = client.instance_action(instance_id=resource["id"], action=action)
        log.info(f"Received status {response.status} for POST:{action} {response.request_id}")
        response = None
        return response


@Instance.action_registry.register("reboot")
class InstanceReboot(OCIBaseAction):
    """Restarts a compute instance.

    :Example:

    .. code-block:: yaml

        policies:
          - name: reboot-compute-instance
            resource: oci.instance
            actions:
              - reboot

          - name: force-reboot-compute-instance
            resource: oci.instance
            actions:
              - type: reboot
                force: true

    If 'force' option is passed, then a compute instance will be rebooted immediately.

    https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/restartinginstance.htm
    """

    schema = type_schema("reboot", force={"type": "boolean"})

    def perform_action(self, resource):
        client = self.manager.get_client()
        action = "RESET" if self.data.get("force") else "SOFTRESET"
        response = client.instance_action(instance_id=resource["id"], action=action)
        log.info(f"Received status {response.status} for POST:{action} {response.request_id}")
        return response


@Instance.action_registry.register("update")
class UpdateInstance(OCIBaseAction):
    """
    Update a compute instace

    :example:

    Updates certain fields on the specified instance. Fields that are not provided in the request will not be updated.

    Changes to metadata fields will be reflected in the instance metadata service (this may take up to a minute).

    The OCID of the instance remains the same.

    .. code-block:: yaml

        policies:
            - name: update-compute-instance
              resource: oci.instance
              actions:
                - type: update
                  shape: VM.Standard.E3.Flex

    https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/edit-instance.htm
    """  # noqa

    schema = type_schema(
        "update",
        **{
            "shape": {"type": "string"},
            "shape_config": {
                "type": "object",
                "properties": {
                    "memory_in_gbs": {"type": "number"},
                    "ocpus": {"type": "number"},
                    "nvmes": {"type": "integer"},
                },
            },
            "freeform_tags": {"type": "object"},
            "defined_tags": {"type": "object"},
        },
    )

    def perform_action(self, resource):
        client = self.manager.get_client()
        update_instance_details_user = self.extract_params(self.data)
        params_model = self.update_params(resource, update_instance_details_user)
        update_instance_details = oci.core.models.UpdateInstanceDetails(**params_model)
        response = client.update_instance(
            instance_id=resource.get("id"), update_instance_details=update_instance_details
        )
        log.info(f"Received status {response.status} for PUT:update_instance {response.request_id}")
        return response


@Instance.filter_registry.register("metrics")
class InstanceMetrics(Filter):
    """
    Instance Metrics Filter

    :example:

    This filter returns the resources with the aggregated metrics data that match the criteria specified in the request.
    Compartment OCID required. For information on metric queries, see `Building Metric Queries
    <https://docs.oracle.com/en-us/iaas/Content/Monitoring/Tasks/buildingqueries.htm>`_ and
    `Monitoring Query Language <https://docs.oracle.com/en-us/iaas/Content/Monitoring/Reference/mql.htm>`_.

    .. code-block:: yaml

        policies:
            - name: instance-with-low-cpu-utilization
            description: |
                Return the instances with the low CPU utilization
            resource: oci.instance
            filters:
                - type: metrics
                  query: 'CpuUtilization[30d].mean() < 6'

        policies:
            - name: instance-with-low-cpu-utilization
            description: Return the instances with the low CPU utilization is less than 50%
            resource: oci.instance
            filters:
                - type: metrics
                  query: 'CpuUtilization[10d]{region="us-ashburn-1"}.max() < 50'

    """  # noqa

    schema = type_schema("metrics", query={"type": "string"}, required=["query"])

    def process(self, resources, event):
        comp_resources = {}
        for resource in resources:
            comp_id = resource.get("compartment_id")
            if comp_id in comp_resources:
                comp_resources.get(comp_id)[resource["id"]] = resource
            else:
                comp_resources[comp_id] = {resource["id"]: resource}
        # Query the MonitoringClient with the query against each compartment and perform
        # the filtering
        monitoring_client = self.manager.get_session().client("oci.monitoring.MonitoringClient")
        result = []
        for compartment_id in comp_resources.keys():
            query = self.data.get("query")
            filter_resources = comp_resources.get(compartment_id)
            query = self.get_metrics_resource_query(query, filter_resources.keys())
            log.debug(
                f"Monitoring client will execute query: {query} for resources in the compartment:"
                f" {compartment_id}"
            )
            summarize_metrics = oci.monitoring.models.SummarizeMetricsDataDetails(
                query=query,
                namespace="oci_computeagent",
            )
            metric_response = monitoring_client.summarize_metrics_data(
                compartment_id=compartment_id,
                summarize_metrics_data_details=summarize_metrics,
            )
            metric_resources = metric_response.data
            for metric_data in metric_resources:
                resource_id = metric_data.dimensions["resourceId"]
                resource = filter_resources.get(resource_id)
                if resource is not None:
                    result.append(resource)
        return result

    @staticmethod
    def get_metrics_resource_query(query, resource_ids):
        if "resourceId" in query:
            return query
        # check for chunk size less than or equal to 10
        if len(resource_ids) <= 10:
            resource_query = 'resourceId=~"{}"'.format(
                "|".join(resource_id for resource_id in resource_ids)
            )
            if "}" in query:
                if "=" in query:
                    resource_query = f",{resource_query}}}"
                query = query.replace("}", resource_query, 1)
            else:
                if "]" in query:
                    query = query.replace("]", f"]{{{resource_query}}}", 1)

        return query
