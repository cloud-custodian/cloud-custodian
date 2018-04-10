# Copyright 2017-2018 Capital One Services, LLC
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
"""Utility functions
"""
from datetime import datetime
from dateutil.parser import parse as date_parse
from dateutil.tz import tzutc
from dateutil import zoneinfo

import functools
import humanize


def row_factory(cursor, row):
    """Returns a sqlite row factory that returns a dictionary"""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


human_size = functools.partial(humanize.naturalsize, gnu=True)


def get_dates(start, end, tz):
    mytz = tz and zoneinfo.gettz(tz) or tzutc()
    start = date_parse(start).replace(tzinfo=mytz)
    if end:
        end = date_parse(end).replace(tzinfo=mytz)
    else:
        end = datetime.now().replace(tzinfo=mytz)
    if tz:
        start = start.astimezone(tzutc())
        if end:
            end = end.astimezone(tzutc())
    if start > end:
        start, end = end, start
    return start, end
