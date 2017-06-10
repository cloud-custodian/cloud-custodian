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
"""Data Pipeline
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from botocore.exceptions import ClientError

from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import chunks, local_session, get_retry


@resources.register('datapipeline')
class DataPipeline(QueryResourceManager):

    retry = staticmethod(get_retry(('Throttled',)))

    class resource_type(object):
        service = 'datapipeline'
        type = 'dataPipeline'
        id = 'id'
        name = 'name'
        date = None
        dimension = 'name'
        enum_spec = ('list_pipelines', 'pipelineIdList', None)

    def augment(self, resources):
        filter(None, _datapipeline_info(
            resources, self.session_factory, self.executor_factory,
            self.retry))
        return resources


def _datapipeline_info(pipes, session_factory, executor_factory, retry):

    def process_tags(pipe_set):
        client = local_session(session_factory).client('datapipeline')
        pipe_map = {pipe['id']: pipe for pipe in pipe_set}

        while True:
            try:
                results = retry(
                    client.describe_pipelines,
                    pipelineIds=pipe_map.keys())
                break
            except ClientError as e:
                if e.response['Error']['Code'] != 'PipelineNotFound':
                    raise
                msg = e.response['Error']['Message']
                _, lb_name = msg.strip().rsplit(' ', 1)
                pipe_map.pop(lb_name)
                if not pipe_map:
                    results = {'TagDescriptions': []}
                    break
                continue
        for pipe_desc in results['pipelineDescriptionList']:
            pipe = pipe_map[pipe_desc['pipelineId']]
            pipe['tags'] = pipe_desc['tags']
            for field in pipe_desc['fields']:
                key = field['key']
                if not key.startswith('@'):
                    continue
                pipe[key[1:]] = field['stringValue']

    with executor_factory(max_workers=2) as w:
        return list(w.map(process_tags, chunks(pipes, 20)))
