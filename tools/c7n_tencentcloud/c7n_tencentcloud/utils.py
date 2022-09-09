# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from enum import Enum


DEFAULT_TAG = "maid_status"


class PageMethod(Enum):
    """
    Paging type enumeration, Enum.Name pagination parameters
    """
    Offset = 0
    PaginationToken = 1
