"""
Generate a yaml file showing full capability set of custodian
filters and actions by resource type.
"""
import argparse

import yaml

import c7n.resources

from c7n.manager import resources
from c7n.query import ResourceQuery


def setup_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('--summary', action="store_true")
    return parser


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

    common_actions = set(['notify', 'invoke-lambda'])
    common_filters = set(['value', 'and', 'or', 'event'])

    for rv in vocabulary.values():
        action_count += len(
            set(rv.get('actions', ())).difference(common_actions))
        filter_count += len(
            set(rv.get('filters', ())).difference(common_filters))
    print "unique actions: %d" % action_count
    print "common actions: %d" % len(common_actions)
    print "unique filters: %d" % filter_count
    print "common filtesr: %s" % len(common_filters)


def main():
    parser = setup_parser()
    options = parser.parse_args()

    c7n.resources.load_resources()
    result = resource_vocabulary()
    if options.summary:
        summary(result)
    else:
        print(yaml.safe_dump(result, default_flow_style=False))


if __name__ == '__main__':
    main()
