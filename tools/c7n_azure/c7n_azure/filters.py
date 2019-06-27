# Copyright 2015-2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import operator
from abc import ABCMeta, abstractmethod
from concurrent.futures import as_completed
from datetime import timedelta

import six
from azure.mgmt.policyinsights import PolicyInsightsClient
from c7n_azure.tags import TagHelper
from c7n_azure.utils import IpRangeHelper
from c7n_azure.utils import Math
from c7n_azure.utils import ThreadHelper
from c7n_azure.utils import now
from dateutil import tz as tzutils
from dateutil.parser import parse

from c7n.filters import Filter, ValueFilter, FilterValidationError
from c7n.filters.core import PolicyValidationError
from c7n.filters.offhours import Time, OffHour, OnHour
from c7n.utils import chunks
from c7n.utils import type_schema

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

    :example: Find all VMs with an average Percentage CPU greater than 75% over last 2 hours

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

    """

    DEFAULT_TIMEFRAME = 24
    DEFAULT_INTERVAL = 'P1D'
    DEFAULT_AGGREGATION = 'average'

    aggregation_funcs = {
        'average': Math.mean,
        'total': Math.sum
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
            'timeframe': {'type': 'number'},
            'interval': {'enum': [
                'PT1M', 'PT5M', 'PT15M', 'PT30M', 'PT1H', 'PT6H', 'PT12H', 'P1D']},
            'aggregation': {'enum': ['total', 'average']},
            'no_data_action': {'enum': ['include', 'exclude']},
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
        self.interval = self.data.get('interval', self.DEFAULT_INTERVAL)
        # Aggregation as defined by Azure SDK
        self.aggregation = self.data.get('aggregation', self.DEFAULT_AGGREGATION)
        # Aggregation function to be used locally
        self.func = self.aggregation_funcs[self.aggregation]
        # Used to reduce the set of metric data returned
        self.filter = self.data.get('filter', None)
        # Include or exclude resources if there is no metric data available
        self.no_data_action = self.data.get('no_data_action', 'exclude')

    def process(self, resources, event=None):
        # Import utcnow function as it may have been overridden for testing purposes
        from c7n_azure.utils import utcnow

        # Get timespan
        end_time = utcnow()
        start_time = end_time - timedelta(hours=self.timeframe)
        self.timespan = "{}/{}".format(start_time, end_time)

        # Create Azure Monitor client
        self.client = self.manager.get_client('azure.mgmt.monitor.MonitorManagementClient')

        # Process each resource in a separate thread, returning all that pass filter
        with self.executor_factory(max_workers=3) as w:
            processed = list(w.map(self.process_resource, resources))
            return [item for item in processed if item is not None]

    def get_metric_data(self, resource):
        metrics_data = self.client.metrics.list(
            resource['id'],
            timespan=self.timespan,
            interval=self.interval,
            metricnames=self.metric,
            aggregation=self.aggregation,
            filter=self.filter
        )
        if len(metrics_data.value) > 0 and len(metrics_data.value[0].timeseries) > 0:
            m = [getattr(item, self.aggregation)
                 for item in metrics_data.value[0].timeseries[0].data]
        else:
            m = None
        return m

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
          actions:
            - type: stop

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

    def validate(self):
        op = self.data.get('op')
        if self.manager and op not in self.manager.action_registry.keys():
            raise PolicyValidationError(
                "Invalid marked-for-op op:%s in %s" % (op, self.manager.data))

        tz = tzutils.gettz(Time.TZ_ALIASES.get(self.data.get('tz', 'utc')))
        if not tz:
            raise PolicyValidationError(
                "Invalid timezone specified '%s' in %s" % (
                    self.data.get('tz'), self.manager.data))
        return self

    def process(self, resources, event=None):
        from c7n_azure.utils import now
        if self.current_date is None:
            self.current_date = now()
        self.tag = self.data.get('tag', DEFAULT_TAG)
        self.op = self.data.get('op', 'stop')
        self.skew = self.data.get('skew', 0)
        self.skew_hours = self.data.get('skew_hours', 0)
        self.tz = tzutils.gettz(Time.TZ_ALIASES.get(self.data.get('tz', 'utc')))
        return super(TagActionFilter, self).process(resources, event)

    def __call__(self, i):

        v = i.get('tags', {}).get(self.tag, None)

        if v is None:
            return False
        if ':' not in v or '@' not in v:
            return False

        msg, tgt = v.rsplit(':', 1)
        action, action_date_str = tgt.strip().split('@', 1)

        if action != self.op:
            return False

        try:
            action_date = parse(action_date_str)
        except Exception:
            self.log.warning("could not parse tag:%s value:%s on %s" % (
                self.tag, v, i['InstanceId']))

        if action_date.tzinfo:
            # if action_date is timezone aware, set to timezone provided
            action_date = action_date.astimezone(self.tz)
            self.current_date = now(tz=self.tz)

        return self.current_date >= (
            action_date - timedelta(days=self.skew, hours=self.skew_hours))


class DiagnosticSettingsFilter(ValueFilter):

    schema = type_schema('diagnostic-settings', rinherit=ValueFilter.schema)
    schema_alias = True

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
        client = PolicyInsightsClient(s.get_credentials())
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


@six.add_metaclass(ABCMeta)
class FirewallRulesFilter(Filter):
    """Filters resources by the firewall rules

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
    """

    schema = type_schema(
        'firewall-rules',
        **{
            'include': {'type': 'array', 'items': {'type': 'string'}},
            'equal': {'type': 'array', 'items': {'type': 'string'}}
        })
    schema_alias = True

    def __init__(self, data, manager=None):
        super(FirewallRulesFilter, self).__init__(data, manager)
        self.policy_include = None
        self.policy_equal = None

    @property
    @abstractmethod
    def log(self):
        raise NotImplementedError()

    def validate(self):
        self.policy_include = IpRangeHelper.parse_ip_ranges(self.data, 'include')
        self.policy_equal = IpRangeHelper.parse_ip_ranges(self.data, 'equal')

        has_include = self.policy_include is not None
        has_equal = self.policy_equal is not None

        if has_include and has_equal:
            raise FilterValidationError('Cannot have both include and equal.')

        if not has_include and not has_equal:
            raise FilterValidationError('Must have either include or equal.')

        return True

    def process(self, resources, event=None):
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
        :return: A set of netaddr.IPRange or netaddr.IPSet with rules defined for the resource.
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
        else:  # validated earlier, can never happen
            raise FilterValidationError("Internal error.")
