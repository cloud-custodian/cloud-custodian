# Copyright 2015-2018 Capital One Services, LLC
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
import os
import logging

log = logging.getLogger('custodian.config')


class Bag(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self[k] = v


class Config(Bag):

    def copy(self, **kw):
        d = {}
        d.update(self)
        d.update(**kw)
        return Config(d)

    @classmethod
    def empty(cls, **kw):
        d = {}
        d.update({
            'region': os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'),
            'regions': (),
            'cache': '',
            'profile': None,
            'account_id': None,
            'assume_role': None,
            'external_id': None,
            'log_group': None,
            'tracer': 'default',
            'metrics_enabled': False,
            'metrics': None,
            'output_dir': '',
            'cache_period': 0,
            'dryrun': False,
            'authorization_file': None})
        d.update(kw)
        return cls(d)
