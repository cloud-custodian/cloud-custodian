# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
import isodate
import operator
from abc import ABCMeta, abstractmethod
from concurrent.futures import as_completed
from datetime import timedelta

from azure.mgmt.costmanagement.models import (QueryAggregation,
                                              QueryComparisonExpression,
                                              QueryDataset, QueryDefinition,
                                              QueryFilter, QueryGrouping,
                                              QueryTimePeriod, TimeframeType)
from c7n_azure.tags import TagHelper
from c7n_azure.utils import (IpRangeHelper, Math, ResourceIdParser,
                             StringUtils, ThreadHelper, now, utcnow, is_resource_group)
from dateutil.parser import parse
from azure.core.exceptions import HttpResponseError

from c7n_azure.provider import resources
from c7n.filters import Filter, FilterValidationError, ValueFilter
from c7n.filters.core import PolicyValidationError
from c7n.filters.related import RelatedResourceFilter
from c7n.filters.offhours import OffHour, OnHour, Time
from c7n.utils import chunks, get_annotation_prefix, type_schema

scalar_ops = {
    'eq': operator.eq,
    'equal': operator.eq,
    'ne': operator.ne,
    'not-equal': operator.ne,
    'gt': operator.gt,
    'greater-than': operator.gt,
    'ge': operator.ge,
    'gte': operator.ge,
    'le': operator.le,
    'lte': operator.le,
    'lt': operator.lt,
    'less-than': operator.lt
}


class MetricFilter(Filter):
    """

    Filters Azure resources based on live metrics from the Azure monitor

    Click `here
    <https://docs.microsoft.com/en-us/azure/monitoring-and-diagnostics/monitoring-supported-metrics/>`_
    for a full list of metrics supported by Azure resources.

    :example:

    Find all VMs with an average Percentage CPU greater than 75% over last 2 hours

    .. code-block:: yaml

        policies:
          - name: vm-percentage-cpu
            resource: azure.vm
            filters:
              - type: metric
                metric: Percentage CPU
                aggregation: average
                op: gt
                threshold: 75
                timeframe: 2

    :example:

    Find VMs with a maximum Percentage CPU at or below 10% over the last 24 hours (note the use of
    ``no_data_action: to_zero`` to treat missing metric values as zeroes)

    .. code-block:: yaml

        policies:
          - name: find-underused-vms
            description: Find VMs with maximum cpu <= 10% over the last 24 hours
            resource: azure.vm
            filters:
              - type: metric
                metric: Percentage CPU
                aggregation: maximum
                op: lte
                threshold: 10
                timeframe: 24
                no_data_action: to_zero

    :example:

    Find KeyVaults with more than 1000 API hits in the last hour

    .. code-block:: yaml

        policies:
          - name: keyvault-hits
            resource: azure.keyvault
            filters:
              - type: metric
                metric: ServiceApiHit
                aggregation: total
                op: gt
                threshold: 1000
                timeframe: 1

    :example:

    Find SQL servers with less than 10% average DTU consumption
    across all databases over last 24 hours

    .. code-block:: yaml

        policies:
          - name: dtu-consumption
            resource: azure.sqlserver
            filters:
              - type: metric
                metric: dtu_consumption_percent
                aggregation: average
                op: lt
                threshold: 10
                timeframe: 24
                filter:  "DatabaseResourceId eq '*'"

    """

    DEFAULT_TIMEFRAME = 24
    DEFAULT_INTERVAL = 'P1D'
    DEFAULT_AGGREGATION = 'average'

    aggregation_funcs = {
        'average': Math.mean,
        'total': Math.sum,
        'count': Math.sum,
        'minimum': Math.min,
        'maximum': Math.max
    }

    schema = {
        'type': 'object',
        'required': ['type', 'metric', 'op', 'threshold'],
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['metric']},
            'metric': {'type': 'string'},
            'op': {'enum': list(scalar_ops.keys())},
            'threshold': {'type': 'number'},
            'metric_namespace': {'type': 'string'},
            'timeframe': {'type': 'number'},
            'start-of-day': {'type': 'boolean'},
            'interval': {'enum': [
                'PT1M', 'PT5M', 'PT15M', 'PT30M', 'PT1H', 'PT6H', 'PT12H', 'P1D']},
            'aggregation': {'enum': ['total', 'average', 'count', 'minimum', 'maximum']},
            'no_data_action': {'enum': ['include', 'exclude', 'to_zero']},
            'filter': {'type': 'string'}
        }
    }
    schema_alias = True

    def __init__(self, data, manager=None):
        super(MetricFilter, self).__init__(data, manager)
        # Metric name as defined by Azure SDK
        self.metric = self.data.get('metric')
        # gt (>), ge  (>=), eq (==), le (<=), lt (<)
        self.op = scalar_ops[self.data.get('op')]
        # Value to compare metric value with self.op
        self.threshold = self.data.get('threshold')
        # Number of hours from current UTC time
        self.timeframe = float(self.data.get('timeframe', self.DEFAULT_TIMEFRAME))
        # Interval as defined by Azure SDK
        self.interval = isodate.parse_duration(self.data.get('interval', self.DEFAULT_INTERVAL))
        # Aggregation as defined by Azure SDK
        self.aggregation = self.data.get('aggregation', self.DEFAULT_AGGREGATION)
        # Aggregation function to be used locally
        self.func = self.aggregation_funcs[self.aggregation]
        # Used to reduce the set of metric data returned
        self.filter = self.data.get('filter', None)
        # Include or exclude resources if there is no metric data available
        self.no_data_action = self.data.get('no_data_action', 'exclude')
        # default to no namespace if not passed in
        self.metricnamespace = self.data.get("metric_namespace", None)
        # default to false if not passed in
        self.start_of_day = self.data.get('start-of-day', False)

    def process(self, resources, event=None):
        # Import utcnow function as it may have been overridden for testing purposes
        from c7n_azure.utils import utcnow

        # Get timespan
        end_time = utcnow()
        start_time = end_time - timedelta(hours=self.timeframe)

        if self.start_of_day:
            start_time = start_time.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            end_time = end_time.replace(
                hour=0, minute=0, second=0, microsecond=0
            ) - timedelta(seconds=1)

        self.timespan = "{}/{}".format(start_time, end_time)

        # Create Azure Monitor client
        self.client = self.manager.get_client('azure.mgmt.monitor.MonitorManagementClient')

        # Process each resource in a separate thread, returning all that pass filter
        with self.executor_factory(max_workers=3) as w:
            processed = list(w.map(self.process_resource, resources))
            return [item for item in processed if item is not None]

    def get_metric_data(self, resource):
        cached_metric_data = self._get_cached_metric_data(resource)
        if cached_metric_data:
            return cached_metric_data['measurement']
        try:
            metrics_data = self.client.metrics.list(
                self.get_resource_id(resource),
                timespan=self.timespan,
                interval=self.interval,
                metricnames=self.metric,
                aggregation=self.aggregation,
                metricnamespace=self.metricnamespace,
                filter=self.get_filter(resource)
            )
        except HttpResponseError:
            self.log.exception("Could not get metric: %s on %s" % (
                self.metric, resource['id']))
            return None

        if len(metrics_data.value) > 0 and len(metrics_data.value[0].timeseries) > 0:
            m = [getattr(item, self.aggregation)
                for item in metrics_data.value[0].timeseries[0].data]
        else:
            m = None

        if self.no_data_action == "to_zero":
            if m is None:
                m = [0]
            else:
                m = [0 if v is None else v for v in m]

        self._write_metric_to_resource(resource, metrics_data, m)

        return m

    def get_resource_id(self, resource):
        return resource['id']

    def get_filter(self, resource):
        return self.filter

    def _write_metric_to_resource(self, resource, metrics_data, m):
        resource_metrics = resource.setdefault(get_annotation_prefix('metrics'), {})
        resource_metrics[self._get_metrics_cache_key()] = {
            'metrics_data': metrics_data.as_dict(),
            'measurement': m,
        }

    def _get_metrics_cache_key(self):
        return "{}, {}, {}, {}, {}".format(
            self.metric,
            self.aggregation,
            self.timeframe,
            self.interval,
            self.filter,
        )

    def _get_cached_metric_data(self, resource):
        metrics = resource.get(get_annotation_prefix('metrics'))
        if not metrics:
            return None
        return metrics.get(self._get_metrics_cache_key())

    def passes_op_filter(self, resource):
        m_data = self.get_metric_data(resource)
        if m_data is None:
            return self.no_data_action == 'include'
        aggregate_value = self.func(m_data)
        return self.op(aggregate_value, self.threshold)

    def process_resource(self, resource):
        return resource if self.passes_op_filter(resource) else None


DEFAULT_TAG = "custodian_status"


class TagActionFilter(Filter):
    """Filter resources for tag specified future action

    Filters resources by a 'custodian_status' tag which specifies a future
    date for an action.

    The filter parses the tag values looking for an 'op@date'
    string. The date is parsed and compared to do today's date, the
    filter succeeds if today's date is gte to the target date.

    The optional 'skew' parameter provides for incrementing today's
    date a number of days into the future. An example use case might
    be sending a final notice email a few days before terminating an
    instance, or snapshotting a volume prior to deletion.

    The optional 'skew_hours' parameter provides for incrementing the current
    time a number of hours into the future.

    Optionally, the 'tz' parameter can get used to specify the timezone
    in which to interpret the clock (default value is 'utc')

    :example:

    .. code-block :: yaml

       policies:
        - name: vm-stop-marked
          resource: azure.vm
          filters:
            - type: marked-for-op
              # The default tag used is custodian_status
              # but that is configurable
              tag: custodian_status
              op: stop
              # Another optional tag is skew
              tz: utc


    """
    schema = type_schema(
        'marked-for-op',
        tag={'type': 'string'},
        tz={'type': 'string'},
        skew={'type': 'number', 'minimum': 0},
        skew_hours={'type': 'number', 'minimum': 0},
        op={'type': 'string'})
    schema_alias = True
    current_date = None
    log = logging.getLogger('custodian.azure.filters.TagActionFilter')

    def validate(self):
        op = self.data.get('op')
        if self.manager and op not in self.manager.action_registry.keys():
            raise PolicyValidationError(
                "Invalid marked-for-op op:%s in %s" % (op, self.manager.data))

        tz = Time.get_tz(self.data.get('tz', 'utc'))
        if not tz:
            raise PolicyValidationError(
                "Invalid timezone specified '%s' in %s" % (
                    self.data.get('tz'), self.manager.data))
        return self

    def process(self, resources, event=None):
        self.tag = self.data.get('tag', DEFAULT_TAG)
        self.op = self.data.get('op', 'stop')
        self.skew = self.data.get('skew', 0)
        self.skew_hours = self.data.get('skew_hours', 0)
        self.tz = Time.get_tz(self.data.get('tz', 'utc'))
        return super(TagActionFilter, self).process(resources, event)

    def __call__(self, i):
        v = i.get('tags', {}).get(self.tag, None)

        if v is None:
            return False
        if ':' not in v or '@' not in v:
            return False

        _, tgt = v.rsplit(':', 1)
        action, action_date_str = tgt.strip().split('@', 1)

        if action != self.op:
            return False

        try:
            action_date = parse(action_date_str)
        except Exception:
            self.log.error("could not parse tag:%s value:%s on %s" % (
                self.tag, v, i['InstanceId']))
            return False

        # current_date must match timezones with the parsed date string
        if action_date.tzinfo:
            action_date = action_date.astimezone(self.tz)
            current_date = now(tz=self.tz)
        else:
            current_date = now()

        return current_date >= (
            action_date - timedelta(days=self.skew, hours=self.skew_hours))


class DiagnosticSettingsFilter(ValueFilter):
    """The diagnostic settings filter is implicitly just the ValueFilter
    on the diagnostic settings for an azure resource.

    :example:

    Find Load Balancers that have logs for both LoadBalancerProbeHealthStatus category and
    LoadBalancerAlertEvent category enabled.
    The use of value_type: swap is important for these examples because it swaps the value
    and the evaluated key so that it evaluates the value provided is in the logs.

    .. code-block:: yaml

        policies:
          - name: find-load-balancers-with-logs-enabled
            resource: azure.loadbalancer
            filters:
              - type: diagnostic-settings
                key: logs[?category == 'LoadBalancerProbeHealthStatus'][].enabled
                value: True
                op: in
                value_type: swap
              - type: diagnostic-settings
                key: logs[?category == 'LoadBalancerAlertEvent'][].enabled
                value: True
                op: in
                value_type: swap

    :example:

    Find KeyVaults that have logs enabled for the AuditEvent category.

    .. code-block:: yaml

        policies:
          - name: find-keyvaults-with-logs-enabled
            resource: azure.keyvault
            filters:
              - type: diagnostic-settings
                key: logs[?category == 'AuditEvent'][].enabled
                value: True
                op: in
                value_type: swap
    """

    schema = type_schema('diagnostic-settings', rinherit=ValueFilter.schema)
    schema_alias = True
    log = logging.getLogger('custodian.azure.filters.DiagnosticSettingsFilter')

    def process(self, resources, event=None):
        futures = []
        results = []
        # Process each resource in a separate thread, returning all that pass filter
        with self.executor_factory(max_workers=3) as w:
            for resource_set in chunks(resources, 20):
                futures.append(w.submit(self.process_resource_set, resource_set))

            for f in as_completed(futures):
                if f.exception():
                    self.log.warning(
                        "Diagnostic settings filter error: %s" % f.exception())
                    continue
                else:
                    results.extend(f.result())

            return results

    def process_resource_set(self, resources):
        #: :type: azure.mgmt.monitor.MonitorManagementClient
        client = self.manager.get_client('azure.mgmt.monitor.MonitorManagementClient')
        matched = []
        for resource in resources:
            settings = client.diagnostic_settings.list(resource['id'])
            settings = [s.as_dict() for s in settings.value]
            # put an empty item in when no diag settings, so the absent operator can function
            if not settings:
                settings = [{}]
            filtered_settings = super(DiagnosticSettingsFilter, self).process(settings, event=None)

            if filtered_settings:
                matched.append(resource)

        return matched


class PolicyCompliantFilter(Filter):
    """Filter resources based on Azure Policy compliance status

    Filter resources by their current Azure Policy compliance status.

    You can specify if you want to filter compliant or non-compliant resources.

    You can provide a list of Azure Policy definitions display names or names to limit
    amount of non-compliant resources. By default it returns a list of all non-compliant
    resources.

    .. code-block :: yaml

       policies:
        - name: non-compliant-vms
          resource: azure.vm
          filters:
            - type: policy-compliant
              compliant: false
              definitions:
                - "Definition display name 1"
                - "Definition display name 2"

    """
    schema = type_schema('policy-compliant', required=['type', 'compliant'],
                         compliant={'type': 'boolean'},
                         definitions={'type': 'array'})
    schema_alias = True

    def __init__(self, data, manager=None):
        super(PolicyCompliantFilter, self).__init__(data, manager)
        self.compliant = self.data['compliant']
        self.definitions = self.data.get('definitions')

    def process(self, resources, event=None):
        s = self.manager.get_session()
        definition_ids = None

        # Translate definitions display names into ids
        if self.definitions:
            policyClient = s.client("azure.mgmt.resource.policy.PolicyClient")
            definitions = [d for d in policyClient.policy_definitions.list()]
            definition_ids = [d.id.lower() for d in definitions
                              if d.display_name in self.definitions or
                              d.name in self.definitions]

        # Find non-compliant resources
        client = s.client('azure.mgmt.policyinsights.PolicyInsightsClient')
        query = client.policy_states.list_query_results_for_subscription(
            policy_states_resource='latest', subscription_id=s.subscription_id).value
        non_compliant = [f.resource_id.lower() for f in query
                         if not definition_ids or f.policy_definition_id.lower() in definition_ids]

        if self.compliant:
            return [r for r in resources if r['id'].lower() not in non_compliant]
        else:
            return [r for r in resources if r['id'].lower() in non_compliant]


class AzureOffHour(OffHour):

    # Override get_tag_value because Azure stores tags differently from AWS
    def get_tag_value(self, i):
        tag_value = TagHelper.get_tag_value(resource=i,
                                            tag=self.tag_key,
                                            utf_8=True)

        if tag_value is not False:
            tag_value = tag_value.lower().strip("'\"")
        return tag_value


class AzureOnHour(OnHour):

    # Override get_tag_value because Azure stores tags differently from AWS
    def get_tag_value(self, i):
        tag_value = TagHelper.get_tag_value(resource=i,
                                            tag=self.tag_key,
                                            utf_8=True)

        if tag_value is not False:
            tag_value = tag_value.lower().strip("'\"")
        return tag_value


class FirewallRulesFilter(Filter, metaclass=ABCMeta):
    """Filters resources by the firewall rules

    Rules can be specified as x.x.x.x-y.y.y.y or x.x.x.x or x.x.x.x/y.

    With the exception of **equal** all modes reference total IP space and ignore
    specific notation.

    **include**: True if all IP space listed is included in firewall.

    **any**: True if any overlap in IP space exists.

    **only**: True if firewall IP space only includes IPs from provided space
    (firewall is subset of provided space).

    **equal**: the list of IP ranges or CIDR that firewall rules must match exactly.

    **IMPORTANT**: this filter ignores all bypass rules. If you want to ensure your resource is
    not available for other Azure Cloud services or from the Portal, please use ``firewall-bypass``
    filter.

    :example:

    .. code-block:: yaml

            policies:
                - name: servers-with-firewall
                  resource: azure.sqlserver
                  filters:
                      - type: firewall-rules
                        include:
                            - '131.107.160.2-131.107.160.3'
                            - 10.20.20.0/24

    :example:

    For SQL Server and Postresql Server, Azure represents the service bypass as firewall rule
    allowing traffic from "0.0.0.0" (this allows traffic from all other azure services). By
    default the firewall filter for these resources ignores this rule during evaluation. To
    include it in the evaluation set the "include-azure-services" flag to true. For example,
    to find all Postgresql Servers where traffic is allowed from all Azure services:

    .. code-block:: yaml

        policies:
          - name: postgres-servers-open-from-azure
            resource: azure.sqlserver
            filters:
              - type: firewall-rules
                include-azure-services: true
                equal:
                  - '0.0.0.0'

    """

    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['firewall-rules']},
            'include': {'type': 'array', 'items': {'type': 'string'}},
            'any': {'type': 'array', 'items': {'type': 'string'}},
            'only': {'type': 'array', 'items': {'type': 'string'}},
            'equal': {'type': 'array', 'items': {'type': 'string'}},
            'include-azure-services': {'type': 'boolean'}
        },
        'oneOf': [
            {"required": ["type", "include"]},
            {"required": ["type", "any"]},
            {"required": ["type", "only"]},
            {"required": ["type", "equal"]}
        ]
    }

    schema_alias = True
    log = logging.getLogger('custodian.azure.filters.FirewallRulesFilter')

    def __init__(self, data, manager=None):
        super(FirewallRulesFilter, self).__init__(data, manager)
        self.policy_include = None
        self.policy_equal = None
        self.policy_any = None
        self.policy_only = None
        self.client = None

    def process(self, resources, event=None):
        self.policy_include = IpRangeHelper.parse_ip_ranges(self.data, 'include')
        self.policy_equal = IpRangeHelper.parse_ip_ranges(self.data, 'equal')
        self.policy_any = IpRangeHelper.parse_ip_ranges(self.data, 'any')
        self.policy_only = IpRangeHelper.parse_ip_ranges(self.data, 'only')

        self.client = self.manager.get_client()

        result, _ = ThreadHelper.execute_in_parallel(
            resources=resources,
            event=event,
            execution_method=self._check_resources,
            executor_factory=self.executor_factory,
            log=self.log
        )

        return result

    def _check_resources(self, resources, event):
        return [r for r in resources if self._check_resource(r)]

    @abstractmethod
    def _query_rules(self, resource):
        """
        Queries firewall rules for a resource. Override in concrete classes.
        :param resource:
        :return: A set of netaddr.IPSet with rules defined for the resource.
        """
        raise NotImplementedError()

    def _check_resource(self, resource):
        resource_rules = self._query_rules(resource)
        ok = self._check_rules(resource_rules)
        return ok

    def _check_rules(self, resource_rules):
        if self.policy_equal is not None:
            return self.policy_equal == resource_rules

        elif self.policy_include is not None:
            return self.policy_include.issubset(resource_rules)

        elif self.policy_any is not None:
            return not self.policy_any.isdisjoint(resource_rules)

        elif self.policy_only is not None:
            return resource_rules.issubset(self.policy_only)
        else:  # validated earlier, can never happen
            raise FilterValidationError("Internal error.")


class FirewallBypassFilter(Filter, metaclass=ABCMeta):
    """Filters resources by the firewall bypass rules
    """

    @staticmethod
    def schema(values):
        return type_schema(
            'firewall-bypass',
            required=['mode', 'list'],
            **{
                'mode': {'enum': ['include', 'equal', 'any', 'only']},
                'list': {'type': 'array', 'items': {'enum': values}}
            })

    log = logging.getLogger('custodian.azure.filters.FirewallRulesFilter')

    def __init__(self, data, manager=None):
        super(FirewallBypassFilter, self).__init__(data, manager)
        self.mode = self.data['mode']
        self.list = set(self.data['list'])
        self.client = None

    def process(self, resources, event=None):
        self.client = self.manager.get_client()

        result, _ = ThreadHelper.execute_in_parallel(
            resources=resources,
            event=event,
            execution_method=self._check_resources,
            executor_factory=self.executor_factory,
            log=self.log
        )

        return result

    def _check_resources(self, resources, event):
        return [r for r in resources if self._check_resource(r)]

    @abstractmethod
    def _query_bypass(self, resource):
        """
        Queries firewall rules for a resource. Override in concrete classes.
        :param resource:
        :return: A set of netaddr.IPSet with rules defined for the resource.
        """
        raise NotImplementedError()

    def _check_resource(self, resource):
        bypass_set = set(self._query_bypass(resource))
        ok = self._check_bypass(bypass_set)
        return ok

    def _check_bypass(self, bypass_set):
        if self.mode == 'equal':
            return self.list == bypass_set

        elif self.mode == 'include':
            return self.list.issubset(bypass_set)

        elif self.mode == 'any':
            return not self.list.isdisjoint(bypass_set)

        elif self.mode == 'only':
            return bypass_set.issubset(self.list)
        else:  # validated earlier, can never happen
            raise FilterValidationError("Internal error.")


class ResourceLockFilter(Filter):
    """
    Filter locked resources.
    Lock can be of 2 types: ReadOnly and CanNotDelete. To filter any lock, use "Any" type.
    Lock type is optional, by default any lock will be applied to the filter.
    To get unlocked resources, use "Absent" type.

    :example:

    Get all keyvaults with ReadOnly lock:

    .. code-block :: yaml

       policies:
        - name: locked-keyvaults
          resource: azure.keyvault
          filters:
            - type: resource-lock
              lock-type: ReadOnly

    :example:

    Get all locked sqldatabases (any type of lock):

    .. code-block :: yaml

       policies:
        - name: locked-sqldatabases
          resource: azure.sqldatabase
          filters:
            - type: resource-lock

    :example:

    Get all unlocked resource groups:

    .. code-block :: yaml

       policies:
        - name: unlock-rgs
          resource: azure.resourcegroup
          filters:
            - type: resource-lock
              lock-type: Absent

    """

    schema = type_schema(
        'resource-lock', required=['type'],
        **{
            'lock-type': {'enum': ['ReadOnly', 'CanNotDelete', 'Any', 'Absent']},
        })

    schema_alias = True
    log = logging.getLogger('custodian.azure.filters.ResourceLockFilter')

    def __init__(self, data, manager=None):
        super(ResourceLockFilter, self).__init__(data, manager)
        self.lock_type = self.data.get('lock-type', 'Any')

    def process(self, resources, event=None):
        resources, exceptions = ThreadHelper.execute_in_parallel(
            resources=resources,
            event=event,
            execution_method=self._process_resource_set,
            executor_factory=self.executor_factory,
            log=self.log
        )
        if exceptions:
            raise exceptions[0]
        return resources

    def _process_resource_set(self, resources, event=None):
        client = self.manager.get_client('azure.mgmt.resource.locks.ManagementLockClient')
        result = []
        for resource in resources:
            if is_resource_group(resource):
                locks = [r.serialize(True) for r in
                         client.management_locks.list_at_resource_group_level(
                    resource['name'])]
            else:
                locks = [r.serialize(True) for r in client.management_locks.list_at_resource_level(
                    resource['resourceGroup'],
                    ResourceIdParser.get_namespace(resource['id']),
                    ResourceIdParser.get_resource_name(resource.get('c7n:parent-id')) or '',
                    ResourceIdParser.get_resource_type(resource['id']),
                    resource['name'])]

            if StringUtils.equal('Absent', self.lock_type) and not locks:
                result.append(resource)
            else:
                for lock in locks:
                    if StringUtils.equal('Any', self.lock_type) or \
                            StringUtils.equal(lock['properties']['level'], self.lock_type):
                        result.append(resource)
                        break

        return result


class CostFilter(ValueFilter):
    """
    Filter resources by the cost consumed over a timeframe.

    Total cost for the resource includes costs for all of it child resources if billed
    separately (e.g. SQL Server and SQL Server Databases). Warning message is logged if we detect
    different currencies.

    Timeframe options:

      - Number of days before today

      - All days in current calendar period until today:

        - ``WeekToDate``
        - ``MonthToDate``

      - All days in the previous calendar period:

        - ``TheLastMonth``
        - ``TheLastBillingMonth``

    :examples:

    SQL servers that were cost more than 2000 in the last month.

    .. code-block:: yaml

            policies:
                - name: expensive-sql-servers-last-month
                  resource: azure.sqlserver
                  filters:
                  - type: cost
                    timeframe: TheLastMonth
                    op: gt
                    value: 2000

    SQL servers that were cost more than 2000 in the last 30 days not including today.

    .. code-block:: yaml

            policies:
                - name: expensive-sql-servers
                  resource: azure.sqlserver
                  filters:
                  - type: cost
                    timeframe: 30
                    op: gt
                    value: 2000
    """

    preset_timeframes = [i.value for i in TimeframeType if i.value != 'Custom']

    schema = type_schema('cost',
        rinherit=ValueFilter.schema,
        required=['timeframe'],
        key=None,
        **{
            'timeframe': {
                'oneOf': [
                    {'enum': preset_timeframes},
                    {"type": "number", "minimum": 1}
                ]
            }
        })

    schema_alias = True
    log = logging.getLogger('custodian.azure.filters.CostFilter')

    def __init__(self, data, manager=None):
        data['key'] = 'PreTaxCost'  # can also be Currency, but now only PreTaxCost is supported
        super(CostFilter, self).__init__(data, manager)
        self.cached_costs = None

    def __call__(self, i):
        if not self.cached_costs:
            self.cached_costs = self._query_costs()

        id = i['id'].lower() + "/"

        costs = [k.copy() for k in self.cached_costs if (k['ResourceId'] + '/').startswith(id)]

        if not costs:
            return False

        if any(c['Currency'] != costs[0]['Currency'] for c in costs):
            self.log.warning('Detected different currencies for the resource {0}. Costs array: {1}'
                             .format(i['id'], costs))

        total_cost = {
            'PreTaxCost': sum(c['PreTaxCost'] for c in costs),
            'Currency': costs[0]['Currency']
        }
        i[get_annotation_prefix('cost')] = total_cost
        result = super(CostFilter, self).__call__(total_cost)
        return result

    def fix_wrap_rest_response(self, data):
        """
        Azure REST API doesn't match the documentation and the python SDK fails to deserialize
        the response.
        This is a temporal workaround that converts the response into the correct form.
        :param data: partially deserialized response that doesn't match the the spec.
        :return: partially deserialized response that does match the the spec.
        """
        type = data.get('type', None)
        if type != 'Microsoft.CostManagement/query':
            return data
        data['value'] = [data]
        data['nextLink'] = data['properties']['nextLink']
        return data

    def _query_costs(self):
        manager = self.manager
        is_resource_group = manager.type == 'resourcegroup'

        client = manager.get_client('azure.mgmt.costmanagement.CostManagementClient')

        aggregation = {'totalCost': QueryAggregation(name='PreTaxCost', function='Sum')}

        grouping = [QueryGrouping(type='Dimension',
                                  name='ResourceGroupName' if is_resource_group else 'ResourceId')]

        query_filter = None
        if not is_resource_group:
            query_filter = QueryFilter(
                dimension=QueryComparisonExpression(name='ResourceType',
                                                    operator='In',
                                                    values=[manager.resource_type.resource_type]))
            if 'dimension' in query_filter._attribute_map:
                query_filter._attribute_map['dimension']['key'] = 'dimensions'

        dataset = QueryDataset(grouping=grouping, aggregation=aggregation, filter=query_filter)

        timeframe = self.data['timeframe']
        time_period = None

        if timeframe not in CostFilter.preset_timeframes:
            end_time = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            start_time = end_time - timedelta(days=timeframe)
            timeframe = 'Custom'
            time_period = QueryTimePeriod(from_property=start_time, to=end_time)

        definition = QueryDefinition(type='ActualCost',
                                     timeframe=timeframe,
                                     time_period=time_period,
                                     dataset=dataset)

        subscription_id = manager.get_session().get_subscription_id()

        scope = '/subscriptions/' + subscription_id

        query = client.query.usage(scope, definition)

        if hasattr(query, '_derserializer'):
            original = query._derserializer._deserialize
            query._derserializer._deserialize = lambda target, data: \
                original(target, self.fix_wrap_rest_response(data))

        result_list = [{query.columns[i].name: v for i, v in enumerate(row)}
                       for row in query.rows]

        for r in result_list:
            if 'ResourceGroupName' in r:
                r['ResourceId'] = scope + '/resourcegroups/' + r.pop('ResourceGroupName')
            r['ResourceId'] = r['ResourceId'].lower()

        return result_list


class ParentFilter(Filter):
    """
    Meta filter that allows you to filter child resources by applying filters to their
    parent resources.

    You can use any filter supported by corresponding parent resource type.

    :examples:

    Find Azure KeyVault Keys from Key Vaults with ``owner:ProjectA`` tag.

    .. code-block:: yaml

        policies:
          - name: kv-keys-from-tagged-keyvaults
            resource: azure.keyvault-key
            filters:
              - type: parent
                filter:
                  type: value
                  key: tags.owner
                  value: ProjectA
    """

    schema = type_schema(
        'parent', filter={'type': 'object'}, required=['type'])
    schema_alias = True

    def __init__(self, data, manager=None):
        super(ParentFilter, self).__init__(data, manager)
        self.parent_manager = self.manager.get_parent_manager()
        self.parent_filter = self.parent_manager.filter_registry.factory(
            self.data['filter'],
            self.parent_manager)

    def process(self, resources, event=None):
        parent_resources = self.parent_filter.process(self.parent_manager.resources())
        parent_resources_ids = [p['id'] for p in parent_resources]
        parent_key = self.manager.resource_type.parent_key
        return [r for r in resources if r[parent_key] in parent_resources_ids]


class AzureAdvisorFilter(RelatedResourceFilter):
    """
    Filter resources by Azure Advisor Recommendations

    Select all categories with 'all'

    :example:

    .. code-block:: yaml

        policies:
          - name: disks-with-cost-recommendations
            resource: azure.disk
            filters:
              - type: advisor-recommendation
                category: Cost
                key: '[].properties.recommendationTypeId'
                op: contains
                value: '48eda464-1485-4dcf-a674-d0905df5054a'
    """

    RelatedResource = "c7n_azure.resources.advisor.AdvisorRecommendation"
    RelatedIdsExpression = "id"
    AnnotationKey = "AdvisorRecommendation"

    schema = type_schema(
        "advisor-recommendation",
        category={'type': 'string'},
        rinherit=RelatedResourceFilter.schema,
        required=['category']
    )

    def _add_annotations(self, related_ids, resource):
        resource[f"c7n:{self.AnnotationKey}"] = self._recommendation_map[
            resource['id'].lower()
        ]

    def get_related(self, resources):
        """
        get_related works a little bit differently here compared to other
        related resource filters namely due to the fact that the parent
        resource (e.g. disk) doesn't have an attribute pointing to a
        advisor recommendation. thus, we need to fetch all recommendations
        first, then map the recommendations to resource ids
        """

        resource_manager = self.get_resource_manager()
        category = self.data.get("category")

        if category == 'all':
            query = None
        else:
            query = {'filter': f"Category eq '{category}'"}

        related = resource_manager.resources(query=[query])
        self._recommendation_map = {}

        for r in related:
            self._recommendation_map.setdefault(
                r["properties"]["resourceMetadata"]["resourceId"].lower(), []
            ).append(r)
        return self._recommendation_map

    def get_related_ids(self, resource):
        # normalize to lower case
        return [i.lower() for i in super().get_related_ids(resource)]

    @classmethod
    def register_resource(cls, registry, resource_class):
        resource_class.filter_registry.register("advisor-recommendation", cls)


resources.subscribe(AzureAdvisorFilter.register_resource)
