# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
from enum import Enum
import pytz


DEFAULT_TAG = "maid_status"


class PageMethod(Enum):
    """
    Paging type enumeration, Enum.Name pagination parameters
    """
    Offset = 0
    PaginationToken = 1
    Page = 2


def isoformat_datetime_str(date_str: str,
                       date_str_format="%Y-%m-%d %H:%M:%S",
                       timezone_from=pytz.timezone("Asia/Shanghai"),
                       timezone_to=pytz.utc):
    """
    standardize the date string, using isoformat including timezone info
    example: '2022-09-28T15:28:28+00:00'
    """
    dt = timezone_from.localize(datetime.strptime(date_str, date_str_format))
    return dt.astimezone(timezone_to).isoformat()


def convert_date_str(date_str: str,
                 date_str_format="%Y-%m-%d %H:%M:%S",
                 timezone_from=pytz.timezone("Asia/Shanghai"),
                 timezone_to=pytz.utc):
    """
    standardize the date string, using isoformat including timezone info
    example: '2022-09-28'
    """
    dt = timezone_from.localize(datetime.strptime(date_str, date_str_format))
    return dt.astimezone(timezone_to).strftime("%Y-%m-%d")
