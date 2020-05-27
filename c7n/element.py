# Copyright 2020 Cloud Custodian Authors.
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

import jmespath


class Element:
    """Parent base class for filters and actions.
    """

    def filter_resources(self, resources, key_expr, allowed_values=(), exclude=()):
        # many filters implementing a resource state transition only allow
        # a given set of starting states, this method will filter resources
        # and issue a warning log, as implicit filtering in filters means
        # our policy metrics are off, and they should be added as policy
        # filters.
        resource_count = len(resources)
        match, nomatch = split_resources(
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
        return split_resources(resources, key_expr, allowed_values, exclude)


def split_resources(resources, key_expr, allowed_values=(), exclude=()):
    search_expr = jmespath.compile(key_expr)
    matched = []
    nomatch = []

    if not isinstance(allowed_values, (list, tuple)):
        allowed_values = (allowed_values,)
    if not isinstance(exclude, (list, tuple)):
        exclude = (exclude,)

    # do each resource individually so resources that do not match
    # the expression can be compared.  jmespath will drop any nulls.
    for r in resources:
        try:
            value = search_expr.search(r)
        except jmespath.exceptions.JMESPathTypeError:
            # in cases like:
            #   jmespath.exceptions.JMESPathTypeError: In function length(),
            #   invalid type for value: None, expected one of:
            #   ['string', 'array', 'object'], received: "null"
            # just assign a value of None as the query is invalid for this resource
            value = None

        # support a list of results, any of which can match
        if not isinstance(value, (list, tuple)):
            value = [value]

        match = True
        if allowed_values:
            match = False
            for i in allowed_values:
                if i in value:
                    match = True
                    break
        if exclude:
            for i in exclude:
                if i in value:
                    match = False
                    break

        if match:
            matched.append(r)
        else:
            nomatch.append(r)

    return matched, nomatch
