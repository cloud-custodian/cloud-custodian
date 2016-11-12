# Copyright 2016 Capital One Services, LLC
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
import logging

from c7n.resources import load_resources

log = logging.getLogger('custodian.metrics')


def metrics(start, end, period, policies):

    load_resources()

    data = {}
    for p in policies:
        log.info('Getting %s metrics', p)
        data[p.name] = p.get_metrics(start, end, period)

    return data
