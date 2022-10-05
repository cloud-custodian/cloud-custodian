# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

"""
Monitoring Metrics filters suppport for resources
"""
import jmespath
import logging
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
        "cvm": "QCE/CVM",
    }

    def __init__(self, data, manager=None):
        super().__init__(data, manager)
        self.days = self.data.get("days", 0)
        self.start_time, self.end_time = self.get_metric_window()
        self.metric_name = self.data["name"]
        self.period = self.data.get("period", 300)
        self.statistics = self.data.get("statistics", "Average")
        self.op = self.data.get("op", "less-than")
        self.missing_value = self.data.get("missing-value")
        self.value = self.data["value"]
        self.resource_metadata: ResourceTypeInfo = self.manager.get_model()
        ns = self.data.get("namespace")
        if not ns:
            ns = self.resource_metadata.metrics_namespace
            if not ns:
                ns = self.DEFAULT_NAMESPACE[self.resource_metadata.service]
        self.namespace = ns

    def get_metric_window(self):
        """get_metric_window"""
        duration = timedelta(days=self.days)
        # delete microsecond to meet SKD api
        now = datetime.now(timezone.utc).replace(microsecond=0)
        start = now - duration
        return start.isoformat(), now.isoformat()

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
        self.statistics = STATISTICS_OPERATORS[self.statistics]
        if self.op not in OPERATORS:
            raise PolicyValidationError(f"unknown op: f{self.op}")
        self.op = OPERATORS[self.op]
        if self.days == 0:
            raise PolicyValidationError("metrics filter days value cannot be 0")

    def process(self, resources, event=None):
        """process"""
        log.debug("[metrics filter]start_time=%s, end_time=%s", self.start_time, self.end_time)
        region = self.manager.config.region

        cli = local_session(self.manager.session_factory).client("monitor.tencentcloudapi.com",
                                                                 "service",
                                                                 "2018-07-24",
                                                                 region)
        matched_resource_ids = []
        for batch in chunks(resources, self.resource_metadata.metrics_batch_size):
            params = self._get_request_params(batch)
            # - get metrics

            resp = cli.execute_query("GetMonitorData", params)
            data_points = jmespath.search("Response.DataPoints[]", resp)
            for point in data_points:
                # - do calc according to statistics
                values = point["Values"]
                if not values and self.missing_value is None:
                    raise PolicyExecutionError("there is no metrics, but not set missing-value")
                if not values:
                    metric_value = self.missing_value
                else:
                    metric_value = self.statistics(point["Values"])
                # - compare
                if self.op(metric_value, self.value):

                    # the response format: {"Dimensions":["Name": "InstanceId", "Value": "xxx"]}
                    matched_resource_ids.append(point["Dimensions"][0]["Value"])
                else:
                    log.debug("[metrics filter]drop resource=%s, metric_value=%s, want_value=%s",
                            point["Dimensions"][0]["Value"], metric_value, self.value)
        matched_resources = []
        if len(matched_resource_ids) > 0:
            for res in resources:
                if res[self.resource_metadata.id] in matched_resource_ids:
                    matched_resources.append(res)
        return matched_resources

    @classmethod
    def register_resources(cls, registry, resource_class: ResourceManager):
        """register_resources"""
        resource_class.filter_registry.register(cls.name, cls)


# finish to register metrics filter to resources
provider_resources.subscribe(MetricsFilter.register_resources)
