# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import ipaddress
import pytz

from c7n.utils import chunks, jmespath_search
from c7n_tencentcloud.filters import MetricsFilter
from c7n_tencentcloud.provider import resources
from c7n_tencentcloud.query import ResourceTypeInfo, QueryResourceManager
from c7n_tencentcloud.utils import PageMethod, isoformat_datetime_str


@resources.register("clb")
class CLB(QueryResourceManager):
    """CLB

    Docs on CLB resources
    https://www.tencentcloud.com/document/product/214
    """

    class resource_type(ResourceTypeInfo):
        """resource_type"""
        id = "LoadBalancerId"
        endpoint = "clb.tencentcloudapi.com"
        service = "clb"
        version = "2018-03-17"
        enum_spec = ("DescribeLoadBalancers", "Response.LoadBalancerSet[]", {})
        paging_def = {"method": PageMethod.Offset, "limit": {"key": "Limit", "value": 20}}
        resource_prefix = "clb"
        taggable = True

        datetime_fields_format = {
            "CreateTime": ("%Y-%m-%d %H:%M:%S", pytz.timezone("Asia/Shanghai"))
        }

    def augment(self, resources_param):
        instances = jmespath_search("filters[*].Instances", self.data)
        if instances:
            for resource in resources_param:
                cli = self.get_client()
                resp = cli.execute_query("DescribeTargets",
                                         {"LoadBalancerId": resource["LoadBalancerId"]})
                listeners = resp["Response"]["Listeners"]
                instance_ids = []
                for listener in listeners:
                    for rule in listener["Rules"]:
                        for target in rule["Targets"]:
                            instance_ids.append(target["InstanceId"])
                    for target in listener["Targets"]:
                        instance_ids.append(target["InstanceId"])
                resource["Instances"] = instance_ids
        for resource in resources_param:
            field_format = self.resource_type.datetime_fields_format["CreateTime"]
            resource["CreateTime"] = isoformat_datetime_str(resource["CreateTime"],
                                                        field_format[0],
                                                        field_format[1])
        return resources_param


@CLB.filter_registry.register("metrics")
class CLBMetricsFilter(MetricsFilter):
    """Filter a CLB resource by metrics

    Docs on CLB metrics

    - Public Network CLB
      https://www.tencentcloud.com/document/product/248/10997
    - Private Network CLB
      https://www.tencentcloud.com/document/product/248/39529

    :example:

    .. code-block:: yaml

        policies:
            - name: clb_metrics_filter
              resource: tencentcloud.clb
              filters:
                - type: value
                  key: CreateTime
                  value_type: age
                  value: 30
                  op: gte
                - type: metrics
                  name: TotalReq
                  statistics: Sum
                  period: 3600
                  days: 30
                  value: 0
                  missing-value: 0
                  op: eq
    """

    DEFAULT_NAMESPACE = {"clb:clb": "QCE/LB_PUBLIC"}

    def _get_request_params(self, resources, namespace):
        dimension_metadata = [(res["LoadBalancerVips"][0], res["VpcId"]) for res in resources]
        dimensions = []
        for metadata_pair in dimension_metadata:
            if namespace == "QCE/LB_PUBLIC":
                dimensions.append({
                    "Dimensions": [{
                        "Name": "vip",
                        "Value": metadata_pair[0]
                    }]
                })
            if namespace == "QCE/LB_PRIVATE":
                dimensions.append({
                    "Dimensions": [
                        {
                            "Name": "vip",
                            "Value": metadata_pair[0]
                        },
                        {
                            "Name": "vpcId",
                            "Value": metadata_pair[1]
                        }
                    ]
                })
        return {
            "Namespace": namespace,
            "MetricName": self.metric_name,
            "Period": self.period,
            "StartTime": self.start_time,
            "EndTime": self.end_time,
            "Instances": dimensions
        }

    def get_metrics_data_point(self, resources, namespace):
        """
        yield data_point
        data_point is a dict which format is the same as DataPoint:
        {
            "Dimensions": {
                "Name": "xxx",
                "Value": "yyy"
            }
            "Timestamps": [int]
            "Values": [float]
        }
        """
        cli = self.get_client()
        for batch in chunks(resources, self.batch_size):
            params = self._get_request_params(batch, namespace)
            resp = cli.execute_query("GetMonitorData", params)
            data_points = jmespath_search("Response.DataPoints[]", resp)
            for point in data_points:
                yield point

    def _process_open_clbs(self, resources):
        """
        resources is a dict which format as below:
        {
            key: clb_metadata
        }
        """
        matched_resources = []
        for point in self.get_metrics_data_point(resources.values(), "QCE/LB_PUBLIC"):
            if self.match(point):
                key = point["Dimensions"][0]["Value"]
                matched_resources.append(resources[key])
        return matched_resources

    def _process_internal_clbs(self, resources):
        """
        resources is a dict which format as below:
        {
            key: clb_metadata
        }
        """
        matched_resources = []
        for point in self.get_metrics_data_point(resources.values(), "QCE/LB_PRIVATE"):
            if self.match(point):
                key = f"{point['Dimensions'][1]['Value']}:{point['Dimensions'][0]['Value']}"
                matched_resources.append(resources[key])
        return matched_resources

    def process(self, resources, event=None):
        """process"""
        # separate resources by LoadBalancerType
        open_clbs = {}
        internal_clbs = {}
        for rs in resources:
            if rs["LoadBalancerType"] == "OPEN":
                # for OPEN CLB, just use internet ip as key
                key = rs['LoadBalancerVips'][0]
                open_clbs[key] = rs
            if rs["LoadBalancerType"] == "INTERNAL":
                for ip in rs["LoadBalancerVips"]:
                    # for INTERNAL CLB, use the intra ip to generate key
                    if ipaddress.ip_address(ip.strip()).is_private:
                        key = f"{rs['VpcId']}:{ip}"
                        break
                internal_clbs[key] = rs

        matched_resources = []
        matched_resources.extend(self._process_open_clbs(open_clbs))
        matched_resources.extend(self._process_internal_clbs(internal_clbs))
        return matched_resources
