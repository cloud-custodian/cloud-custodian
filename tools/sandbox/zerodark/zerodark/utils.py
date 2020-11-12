# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Utility functions
"""
from datetime import datetime
from dateutil.parser import parse as date_parse
from dateutil.tz import tzutc
from dateutil import tz as tzutils

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
    mytz = tz and tzutils.gettz(tz) or tzutc()
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
