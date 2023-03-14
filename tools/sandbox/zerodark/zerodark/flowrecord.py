# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#  Copyright 2015 Observable Networks
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#
# Changes from upstream (KapilT)
#
# - lazy load on datetime parse
# - handle exported log record format

from datetime import datetime


ACCEPT = 'ACCEPT'
REJECT = 'REJECT'
SKIPDATA = 'SKIPDATA'
NODATA = 'NODATA'


class FlowRecord:
    """
    Given a VPC Flow Logs event dictionary, returns a Python object whose
    attributes match the field names in the event record. Integers are stored
    as Python int objects; timestamps are stored as Python datetime objects.
    """
    __slots__ = [
        'version',
        'account_id',
        'interface_id',
        'srcaddr',
        'dstaddr',
        'srcport',
        'dstport',
        'protocol',
        'packets',
        'bytes',
        'start',
        'end',
        'action',
        'log_status',
        '_start_date',
        '_end_date'
    ]

    def __init__(self, line=None, EPOCH_32_MAX=2147483647, fields=None):
        if fields is None:
            fields = line.split()
        # if cwl export pop date
        if len(fields) == 15:
            fields.pop(0)

        self.version = int(fields[0])
        self.account_id = fields[1]
        self.interface_id = fields[2]

        start = int(fields[10])
        if start > EPOCH_32_MAX:
            start /= 1000

        end = int(fields[11])
        if end > EPOCH_32_MAX:
            end /= 1000

        self.start = start
        self.end = end
        self._start_date = None
        self._end_date = None

        self.log_status = fields[13]
        if self.log_status in (NODATA, SKIPDATA):
            self.srcaddr = None
            self.dstaddr = None
            self.srcport = None
            self.dstport = None
            self.protocol = None
            self.packets = None
            self.bytes = None
            self.action = None
        else:
            self.srcaddr = fields[3]
            self.dstaddr = fields[4]
            self.srcport = fields[5] != '-' and int(fields[5]) or 0
            self.dstport = fields[5] != '-' and int(fields[6]) or 0
            self.protocol = int(fields[7])
            self.packets = int(fields[8])
            self.bytes = int(fields[9])
            self.action = fields[12]

    @property
    def start_date(self):
        if self._start_date is None:
            self._start_date = datetime.utcfromtimestamp(self.start)
        return self._start_date

    @property
    def end_date(self):
        if self._end_date is None:
            self._end_date = datetime.utcfromtimestamp(self.end)
        return self._end_date

    def __eq__(self, other):
        try:
            return all(
                getattr(self, x) == getattr(other, x) for x in self.__slots__[:-2]
            )
        except AttributeError:
            return False

    def __hash__(self):
        return hash(tuple(getattr(self, x) for x in self.__slots__[:-2]))

    def __str__(self):
        ret = ['{}: {}'.format(x, getattr(self, x)) for x in self.__slots__[:-2]]
        return ', '.join(ret)

    def to_dict(self):
        return {x: getattr(self, x) for x in self.__slots__[:-2]}

    def to_message(self):
        ret = []
        for attr in self.__slots__[:-2]:
            ret.append(getattr(self, attr))
        return ' '.join(ret)

    @classmethod
    def from_message(cls, message):
        return cls({'message': message})
