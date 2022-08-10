# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
from decimal import Decimal

import json


class Encoder(json.JSONEncoder):

    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        elif isinstance(o, datetime):
            return o.isoformat()
        return super(Encoder, self).default(o)
