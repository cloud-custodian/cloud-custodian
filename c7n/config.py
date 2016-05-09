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


class Config(object):

    schema = {
        'type': 'object',
        'properties': {
            'assume_role': {'type': 'string'},
            'config': {'type': 'string'},
            'debug': {'type': 'boolean'},
            'cache_period': {'type': 'number'},
            'dryrun': {'type': 'boolean'},
            'log_group': {'type': 'string'},
            'metrics_enabled': {'type': 'boolean'},
            'output_dir': {'type': 'string'},
            'policy_names': {'type': 'array', 'items': {'type': 'string'}},
            'profile': {'type': 'string'},
            'verbose': {'type': 'boolean'},
        }
    }

    policies = None
    
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def from_cli(self, options):
        self.__dict__.update(dict(
            verbose=options.verbose,
            config=options.config,
            assume_role=options.assume_role,
            profile=options.profile,
            policy_names=options.policies,
            log_group=options.log_group,
            cache_period=options.cache_period,
            metrics_enabled=getattr(options, 'metrics_enabled', None),
            output_dir=options.output_dir,
            debug=options.debug,
            dryrun=getattr(options, 'dryrun', None)))
