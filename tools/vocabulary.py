"""
Generate a yaml file showing full capability set of custodian
filters and actions by resource type.
"""

import c7n.resources

from c7n.manager import resources
from c7n.query import ResourceQuery
import yaml


def resources_by_service():
    services = {}
    for type_name, manager_type in resources.items():
        resource_type = getattr(manager_type, 'resource_type', None)
        if resource_type is None: # kms
            continue
        services.setdefault(
            ResourceQuery.resolve(resource_type).service, []).append(type_name)
    return services


def all_resources():
    return sorted(resources.keys())


def resource_vocabulary():
    vocabulary = {}
    for type_name, resource_type in resources.items():
        actions = []
        action_classes = set()
        for action_name, klass in reversed(
                resource_type.action_registry.items()):
            # Dedup aliases
            if klass in action_classes:
                continue
            actions.append(action_name)

        filters = []
        filter_classes = set()
        for filter_name, klass in reversed(
                resource_type.filter_registry.items()):
            # Dedup aliases
            if klass in filter_classes:
                continue
            filters.append(filter_name)

        vocabulary[type_name] = {
            'filters': filters, 'actions': actions}
    return vocabulary


def summary(vocabulary):
    print "resource count: %d" % len(vocabulary)
    action_count = filter_count = 0
    for rv in vocabulary.values():
        action_count += len(rv.get('actions', ()))
        filter_count += len(rv.get('filters', ()))
    print "actions count: %d" % action_count
    print "filter count: %d" % filter_count


def main():
    c7n.resources.load_resources()
    result = resource_vocabulary()
    #result = resources_by_service()
    #result = all_resources()
    print(yaml.safe_dump(result, default_flow_style=False))


if __name__ == '__main__':
    main()
