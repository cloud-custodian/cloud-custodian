# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from retrying import RetryError
from tencentcloud.common.exception import TencentCloudSDKException

from c7n.exceptions import PolicyExecutionError
from c7n.utils import type_schema, chunks, jmespath_search
from c7n_tencentcloud.actions import TencentCloudBaseAction
from c7n_tencentcloud.provider import resources
from c7n_tencentcloud.query import ResourceTypeInfo, QueryResourceManager, DescribeSource
from c7n_tencentcloud.utils import PageMethod


@resources.register("cvm")
class CVM(QueryResourceManager):
    """CVM Cloud Virtual Machine

    Docs on CVM resource
    https://www.tencentcloud.com/document/product/213

    :example:

    .. code-block:: yaml

        policies:
        - name: tencentcloud-cvm
          resource: tencentcloud.cvm
          filters:
            - type: value
              key: InstanceType
              op: in
              value:
                - S1.SMALL1
    """

    class resource_type(ResourceTypeInfo):
        """resource_type"""
        id = "InstanceId"
        endpoint = "cvm.tencentcloudapi.com"
        service = "cvm"
        version = "2017-03-12"
        enum_spec = ("DescribeInstances", "Response.InstanceSet[]", {})
        paging_def = {"method": PageMethod.Offset, "limit": {"key": "Limit", "value": 20}}
        resource_prefix = "instance"
        taggable = True
        batch_size = 10
        metrics_enabled = True
        metrics_dimension_def = [("InstanceId", "InstanceId")]
        metrics_instance_id_name = "InstanceId"
        metrics_namespace = "QCE/CVM"

    def get_qcs_for_cbs(self, resources):
        """
        get cvm resource qcs
        Get the qcs of the cvm to which the cbs belongs
        """
        # qcs::${ServiceType}:${Region}:${Account}:${ResourcePrefix}/${ResourceId}
        qcs_list = []
        for r in resources:
            qcs = DescribeSource.get_qcs(r["InstanceType"].lower(),
                                         self.config.region,
                                         None,
                                         "instance",
                                         r["InstanceId"])
            qcs_list.append(qcs)
        return qcs_list

    def augment(self, resources):
        return resources


class CvmAction(TencentCloudBaseAction):
    schema_alias = True

    """cvm base api_method_name """

    def process(self, resources):
        for batch in chunks(resources, self.resource_type.batch_size):
            params = self.get_request_params(batch)
            if params is not None:
                self.do_request(params)

    def do_request(self, params):
        """process_cvm"""
        try:
            client = self.get_client()
            resp = client.execute_query(self.t_api_method_name, params)
            failed_resources = jmespath_search("Response.Error", resp)
            if failed_resources is not None:
                raise PolicyExecutionError(f"{self.data.get('type')} error")
            self.log.debug("%s resources: %s, cvm: %s",
                           self.data.get('type'),
                           params['InstanceIds'],
                           params)
        except (RetryError, TencentCloudSDKException) as err:
            raise PolicyExecutionError(err) from err

    def get_request_params(self, resources):
        """
        The default value returns InstanceIds , if there is customization,
        it will be implemented in subclasses
        """
        return {"InstanceIds": [r[self.resource_type.id] for r in resources]}


@CVM.action_registry.register('stop')
class CvmStopAction(CvmAction):
    """Action to stop a running cvm instance

    :example:

    .. code-block:: yaml

        policies:
        - name: cvm-marked-for-op-stop
          resource: tencentcloud.cvm
          filters:
            - type: marked-for-op
              op: stop
              skew: 14
          actions:
            - type: stop
    """
    schema = type_schema("stop")
    t_api_method_name = "StopInstances"

    def process(self, resources):
        # only applies to running instances
        resources = self.filter_resources(resources, "InstanceState", ("RUNNING",))
        return super().process(resources)

    def get_request_params(self, resources):
        """get_params_stop"""
        return {
            "InstanceIds": [r[self.resource_type.id] for r in resources],
            "StopType": "SOFT",
            "StoppedMode": "STOP_CHARGING"
        }


@CVM.action_registry.register('start')
class CvmStartAction(CvmAction):
    """Action to stop a running cvm instance

    :example:

    .. code-block:: yaml

        policies:
        - name: cvm-start
          resource: tencentcloud.cvm
          actions:
            - type: start
    """
    schema = type_schema("start")
    t_api_method_name = "StartInstances"


@CVM.action_registry.register('terminate')
class CvmTerminateAction(CvmAction):
    """Action to stop a running cvm instance

    :example:

    .. code-block:: yaml

        policies:
        - name: cvm-marked-for-op-terminate
          resource: tencentcloud.cvm
          filters:
            - type: marked-for-op
              op: terminate
              skew: 14
          actions:
            - type: terminate
    """
    schema = type_schema("terminate")
    t_api_method_name = "TerminateInstances"
