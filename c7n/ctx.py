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
import time

from c7n.output import FSOutput, MetricsOutput, CloudWatchLogOutput


class ExecutionContext(object):
    """Policy Execution Context."""

    def __init__(self, session_factory, policy, options):
        self.policy = policy
        self.options = options
        self.session_factory = session_factory
        self.cloudwatch_logs = None
        self.start_time = None

        metrics_enabled = getattr(options, 'metrics_enabled', None)
        factory = MetricsOutput.select(metrics_enabled)
        self.metrics = factory(self)

        output_dir = getattr(options, 'output_dir', '')
        factory = FSOutput.select(output_dir)

        self.output_path = factory.join(output_dir, policy.name)
        self.output = factory(self)

        if options.log_group:
            self.cloudwatch_logs = CloudWatchLogOutput(self)

    @property
    def log_dir(self):
        return self.output.root_dir

    def __enter__(self):
        self.output.__enter__()
        if self.cloudwatch_logs:
            self.cloudwatch_logs.__enter__()
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type=None, exc_value=None, exc_traceback=None):
        self.metrics.flush()
        if self.cloudwatch_logs:
            self.cloudwatch_logs.__exit__(exc_type, exc_value, exc_traceback)
            self.cloudwatch_logs = None
        self.output.__exit__(exc_type, exc_value, exc_traceback)
