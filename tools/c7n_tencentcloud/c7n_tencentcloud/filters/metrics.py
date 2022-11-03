# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

"""
Monitoring Metrics filters suppport for resources
"""
import jmespath
import logging
import math
from statistics import mean
from datetime import datetime, timedelta, timezone
from c7n.exceptions import PolicyValidationError, PolicyExecutionError
from c7n.manager import ResourceManager
from c7n.filters.core import Filter, OPERATORS
from c7n.utils import type_schema, chunks, local_session
from c7n_tencentcloud.provider import resources as provider_resources
from c7n_tencentcloud.query import ResourceTypeInfo


log = logging.getLogger("custodian.tencentcloud.filter")


STATISTICS_OPERATORS = {
    "Average": mean,
    "Sum": sum,
    "Maximum": max,
    "Minimum": min
}


class MetricsFilter(Filter):
    """MetricsFilter"""
    name = "metrics"
    schema = type_schema(
        name,
        **{
            "name": {"type": "string"},
            "namespace": {"type": "string"},
            "statistics": {"type": "string", "enum": list(STATISTICS_OPERATORS.keys())},
            "days": {"type": "number"},
            "op": {"type": "string", "enum": list(OPERATORS.keys())},  # TODO, remove unsupported op
            "value": {"type": "number"},
            "missing-value": {"type": "number"},
            "period": {"type": "number"},
            "required": ("value", "name")
        }
    )
    schema_alias = True
    permissions = ()

    DEFAULT_NAMESPACE = {
        "cvm:instance": "QCE/CVM",
        "vpc:nat": "QCE/NAT_GATEWAY",
    }

    def __init__(self, data, manager=None):
        super().__init__(data, manager)
        self.days = self.data.get("days", 0)
        self.start_time, self.end_time = self.get_metric_window()
        self.metric_name = self.data["name"]
        self.period = self.data.get("period", 300)
        self.batch_size = self.get_batch_size()
        self.statistics = self.data.get("statistics", "Average")
        self.op = self.data.get("op", "less-than")
        self.missing_value = self.data.get("missing-value")
        self.value = self.data["value"]
        self.resource_metadata: ResourceTypeInfo = self.manager.get_model()
        ns = self.data.get("namespace")
        if not ns:
            ns = self.resource_metadata.metrics_namespace
            if not ns:
                key = f"{self.resource_metadata.service}:{self.resource_metadata.resource_prefix}"
                ns = self.DEFAULT_NAMESPACE[key]
        self.namespace = ns

    def get_metric_window(self):
        """get_metric_window"""
        duration = timedelta(days=self.days)
        # delete microsecond to meet SKD api
        now = datetime.now(timezone.utc).replace(microsecond=0)
        start = now - duration
        return start.isoformat(), now.isoformat()

    def get_batch_size(self):
        """get_batch_size
        refer doc: https://www.tencentcloud.com/document/product/248/33881
        one request only support 1440 data points
        so it need to calc the batch size
        """
        data_points_per_resource = math.ceil(self.days * 86400 / self.period)
        return math.floor(1440 / data_points_per_resource)

    def _get_request_params(self, resources):
        ids = [res[self.resource_metadata.id] for res in resources]
        dimensions = []
        for iter_id in ids:
            dimensions.append({
                "Dimensions": [{
                    "Name": self.resource_metadata.metrics_instance_id_name,
                    "Value": iter_id
                }]
            })
        return {
            "Namespace": self.namespace,
            "MetricName": self.metric_name,
            "Period": self.period,
            "StartTime": self.start_time,
            "EndTime": self.end_time,
            "Instances": dimensions
        }

    def validate(self):
        """validate"""
        if self.statistics not in STATISTICS_OPERATORS:
            raise PolicyValidationError(f"unknown statistics: {self.statistics}")
        self.statistics_op = STATISTICS_OPERATORS[self.statistics]
        if self.op not in OPERATORS:
            raise PolicyValidationError(f"unknown op: f{self.op}")
        self.op = OPERATORS[self.op]
        if self.days == 0:
            raise PolicyValidationError("metrics filter days value cannot be 0")
        if self.batch_size == 0:
            raise PolicyValidationError("too many data points, "
                                        "pls reduce the days or use large granularity")

    def get_client(self):
        """get_client"""
        return local_session(self.manager.session_factory).client("monitor.tencentcloudapi.com",
                                                                  "service",
                                                                  "2018-07-24",
                                                                  self.manager.config.region)

    def process(self, resources, event=None):
        """process"""
        log.debug("[metrics filter]start_time=%s, end_time=%s", self.start_time, self.end_time)

        matched_resource_ids = []
        for data_point in self.get_metrics_data_point(resources):
            if self.match(data_point):
                matched_resource_ids.append(data_point["Dimensions"][0]["Value"])
            else:
                log.debug("[metrics filter]drop resource=%s", data_point["Dimensions"][0]["Value"])

        matched_resources = []
        if len(matched_resource_ids) > 0:
            for res in resources:
                if res[self.resource_metadata.id] in matched_resource_ids:
                    matched_resources.append(res)
        return matched_resources

    def get_metrics_data_point(self, resources):
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
            params = self._get_request_params(batch)
            resp = cli.execute_query("GetMonitorData", params)
            data_points = jmespath.search("Response.DataPoints[]", resp)
            for point in data_points:
                yield point

    def match(self, data_point):
        """match"""
        # - do calc according to statistics
        values = data_point["Values"]
        if not values and self.missing_value is None:
            raise PolicyExecutionError("there is no metrics, but not set missing-value")
        if not values:
            metric_value = self.missing_value
        else:
            metric_value = self.statistics_op(values)
        # - compare
        return self.op(metric_value, self.value)

    @classmethod
    def register_resources(cls, registry, resource_class: ResourceManager):
        """register_resources"""
        if cls.name in resource_class.filter_registry:
            # to support resource to define its own metrics filter
            return
        resource_class.filter_registry.register(cls.name, cls)


# finish to register metrics filter to resources
provider_resources.subscribe(MetricsFilter.register_resources)
