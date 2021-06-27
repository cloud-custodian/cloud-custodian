# Copyright 2020 Cloud Custodian Authors.
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.executor import ThreadPoolExecutor
from c7n.utils import split_by_expression


class Element:
    """Parent base class for filters and actions.
    """

    permissions = ()
    metrics = ()

    executor_factory = ThreadPoolExecutor

    schema = {'type': 'object'}
    # schema aliases get hoisted into a jsonschema definition
    # location, and then referenced inline.
    schema_alias = None

    def get_permissions(self):
        return self.permissions

    def validate(self):
        """Validate the current element's configuration.

        Should raise a validation error if there are any configuration issues.

        This method will always be called prior to element execution/process() method
        being called and thus can act as a point of lazy initialization.
        """

    def filter_resources(self, resources, key_expr, allowed_values=(), exclude=()):
        # many filters implementing a resource state transition only allow
        # a given set of starting states, this method will filter resources
        # and issue a warning log, as implicit filtering in filters means
        # our policy metrics are off, and they should be added as policy
        # filters.
        resource_count = len(resources)
        match, nomatch = self.split_resources(
            resources, key_expr, allowed_values=allowed_values, exclude=exclude
        )
        if resource_count != len(match):
            msg = "%s implicitly filtered %d of %d resources key:%s" % (
                self.type,
                len(match),
                resource_count,
                key_expr,
            )
            if allowed_values:
                msg += " on %s" % (
                    ', '.join(['no value' if v is None else v for v in allowed_values])
                )
            if exclude:
                msg += " excluding %s" % (
                    ', '.join(['no value' if v is None else v for v in exclude])
                )
            self.log.warning(msg)
        return match

    def split_resources(self, resources, key_expr, allowed_values=(), exclude=()):
        return split_by_expression(resources, key_expr, allowed_values, exclude)
