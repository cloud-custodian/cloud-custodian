"""
Generate a yaml file showing full capability set of custodian
filters and actions by resource type.
"""

import c7n.resources

from c7n.manager import resources

import yaml


def main():
    c7n.resources.load_resources()

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

    print(yaml.safe_dump(vocabulary, default_flow_style=False))


if __name__ == '__main__':
    main()
