# Copyright 2019 Karol Lassak
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

from datetime import datetime, timedelta

from c7n_aliyun.actions import MethodAction
from c7n_aliyun.filters.labels import LabelActionFilter
from dateutil import tz as tzutil

from c7n.filters import FilterValidationError
from c7n.filters.offhours import Time
from c7n.lookup import Lookup
from c7n.utils import type_schema


class BaseLabelAction(MethodAction):

    method_spec = {}
    method_perm = 'update'

    def get_labels_to_add(self, resource):
        return None

    def get_labels_to_delete(self, resource):
        return None

    def _merge_labels(self, current_labels, new_labels, remove_labels):
        result = dict(current_labels)
        if new_labels:
            result.update(new_labels)
        if remove_labels:
            result = {k: v for k, v in result.items() if k not in remove_labels}
        return result

    def get_operation_name(self, model, resource):
        return model.labels_op

    def get_resource_params(self, model, resource):
        current_labels = self._get_current_labels(resource)
        new_labels = self.get_labels_to_add(resource)
        remove_labels = self.get_labels_to_delete(resource)
        all_labels = self._merge_labels(current_labels, new_labels, remove_labels)

        return model.get_label_params(resource, all_labels)

    def _get_current_labels(self, resource):
        return resource.get('labels', {})

    @classmethod
    def register_resources(cls, registry, resource_class):
        if resource_class.resource_type.labels:
            resource_class.action_registry.register('set-labels', SetLabelsAction)
            resource_class.action_registry.register('mark-for-op', LabelDelayedAction)

            resource_class.filter_registry.register('marked-for-op', LabelActionFilter)



class SetLabelsAction(BaseLabelAction):

    schema = type_schema(
        'set-labels',
        labels={'type': 'object', "additionalProperties": Lookup.lookup_type({'type': 'string'})},
        remove={'type': 'array', 'items': {'type': 'string'}})

    def validate(self):
        if not self.data.get('labels') and not self.data.get('remove'):
            raise FilterValidationError("Must specify one of labels or remove")

    def get_labels_to_add(self, resource):
        return {k: Lookup.extract(v, resource) for k, v in self.data.get('labels').items()}

    def get_labels_to_delete(self, resource):
        return self.data.get('remove')


DEFAULT_TAG = "custodian_status"


class LabelDelayedAction(BaseLabelAction):

    schema = type_schema(
        'mark-for-op',
        label={'type': 'string'},
        msg={'type': 'string'},
        days={'type': 'integer', 'minimum': 0, 'exclusiveMinimum': False},
        hours={'type': 'integer', 'minimum': 0, 'exclusiveMinimum': False},
        tz={'type': 'string'},
        op={'type': 'string'}
    )

    default_template = 'resource_policy-{op}-{action_date}'

    def __init__(self, data=None, manager=None, log_dir=None):
        super(LabelDelayedAction, self).__init__(data, manager, log_dir)
        self.tz = tzutil.gettz(
            Time.TZ_ALIASES.get(self.data.get('tz', 'utc')))

        msg_tmpl = self.data.get('msg', self.default_template)

        op = self.data.get('op', 'stop')
        days = self.data.get('days', 0)
        hours = self.data.get('hours', 0)
        action_date = self.generate_timestamp(days, hours)

        self.label = self.data.get('label', DEFAULT_TAG)
        self.msg = msg_tmpl.format(
            op=op, action_date=action_date)

    def validate(self):
        op = self.data.get('op')
        if self.manager and op not in self.manager.action_registry.keys():
            raise FilterValidationError(
                "mark-for-op specifies invalid op:%s in %s" % (
                    op, self.manager.data))

        self.tz = tzutil.gettz(
            Time.TZ_ALIASES.get(self.data.get('tz', 'utc')))
        if not self.tz:
            raise FilterValidationError(
                "Invalid timezone specified %s in %s" % (
                    self.tz, self.manager.data))

    def generate_timestamp(self, days, hours):
        n = datetime.now(tz=self.tz)
        if days is None or hours is None:
            # maintains default value of days being 4 if nothing is provided
            days = 4
        action_date = (n + timedelta(days=days, hours=hours))
        if hours > 0:
            action_date_string = action_date.strftime('%Y_%m_%d__%H_%M')
        else:
            action_date_string = action_date.strftime('%Y_%m_%d__0_0')

        return action_date_string

    def get_labels_to_add(self, resource):
        return {self.label: self.msg}
