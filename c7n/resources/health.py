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
from cStringIO import StringIO
import csv
import datetime
from datetime import timedelta
from dateutil.parser import parse
from dateutil.tz import tzutc
import time
from botocore.exceptions import ClientError

from c7n.actions import BaseAction, ActionRegistry
from c7n.filters import ValueFilter, Filter, OPERATORS, FilterRegistry
from c7n.manager import resources
from c7n.query import ResourceManager
from c7n.utils import local_session, type_schema


filters = FilterRegistry('aws.health.actions')
actions = ActionRegistry('aws.health.filters')


def get_health_events(session_factory):
    session = local_session(session_factory)
    client = session.client('health')
    events = client.describe_events().get(
        'events', ('',))
    return events


@resources.register('health')
class HealthEvents(ResourceManager):

    filter_registry = filters
    action_registry = actions

    class resource_type(object):
        service = 'health'

    def get_model(self):
        return self.resource_type

    def resources(self):
        return self.filter_resources([get_health_events(self.session_factory)])

    def get_resources(self, resource_ids):
        return [get_health_events(self.session_factory)]
