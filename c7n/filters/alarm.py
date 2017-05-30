from c7n.utils import type_schema
from .core import ValueFilter


class AlarmFilter(ValueFilter):
    """Filter a resource on the basis of whether it has alarms.

    Example, to find all asg with alarms that are not in an okay state.

    .. yaml

      policies:
        name: alarms-fired
        resource: asg
        filters:
         - type: alarm
           key: StateValue
           value: ok
           value_type: normalize
           op: not-equal
    """

    schema = type_schema('alarm', rinherit=ValueFilter.schema)

    def process(self, resources, event=None):
        model = self.manager.get_model()
        resource_alarms = self.get_alarms_by_resource(resources)
        results = []
        for r in resources:
            alarms = resource_alarms.get(r[model.id], ())
            matched = []
            for a in alarms:
                if self.match(a):
                    matched.append(a)
            if matched:
                r['c7n-alarms'] = matched
                results.append(r)
        return results

    def get_alarms_by_resource(self, resources):
        from c7n.resources.cw import Alarm as AlarmResource
        model = self.manager.get_model()
        alarms = AlarmResource(self.manager.ctx, {}).resources()
        resource_alarms = {r[model.dimension]: [] for r in resources}
        for a in alarms:
            for d in a.get('Dimensions', ()):
                if d['Name'] != model.dimension:
                    continue
                if d['Value'] in resource_alarms:
                    resource_alarms[d['Value']].append(a)
                    break
        return resource_alarms
