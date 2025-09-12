# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import datetime
from c7n.filters.core import Filter
from c7n.utils import type_schema

"""
GC Filter to find resources based on time range
"""


class TimeRangeFilter(Filter):

    schema = type_schema('time-range',
                         value={'$ref': '#/definitions/filters_common/value'})

    datetime1_pattern = "%Y-%m-%dT%H:%M:%S.%fZ"
    datetime2_pattern = "%Y-%m-%dT%H:%M:%S"

    permissions = ()
    create_time_field_name = ''
    expire_time_field_name = ''

    def process(self, resources, event=None):
        filtered_resources = []
        value = self.data.get('value')

        for resource in resources:
            create_time_pattern = self.datetime1_pattern
            expired_time_pattern = self.datetime1_pattern
            expired_time = resource[self.expire_time_field_name]
            create_time = resource[self.create_time_field_name]
            if '.' not in expired_time and 'Z' in expired_time:
                expired_time_pattern = self.datetime2_pattern
                expired_time = expired_time[:-1]
            if '.' not in create_time and 'Z' in create_time:
                create_time_pattern = self.datetime2_pattern
                create_time = create_time[:-1]

            filtered_expired_time = datetime.datetime.strptime(
                expired_time, expired_time_pattern)
            filtered_start_time = datetime.datetime.strptime(
                create_time, create_time_pattern)
            result_time = filtered_expired_time - filtered_start_time
            if int(result_time.days) < value:
                filtered_resources.append(resource)

        return filtered_resources
