# Copyright 2015-2017 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

from botocore.exceptions import ClientError

from c7n.actions import BaseAction
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, type_schema


@resources.register('ml-model')
class MLModel(QueryResourceManager):

    class resource_type(object):
        service = 'machinelearning'
        enum_spec = ('describe_ml_models', 'Results', None)
        id = 'MLModelId'
        name = 'Name'
        date = 'CreatedAt'
        # need to specify request-mode dimension as well
        # dimension = 'MLModelId'
        dimension = None


@MLModel.action_registry.register('delete')
class DeleteMLModel(BaseAction):
    """Action to delete machine learning model

    It is recommended to use a filter to avoid unwanted deletion of models

    :example:

    .. code-block:: yaml

            policies:
              - name: ml-model-delete
                resource: ml-model
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ("machinelearning:DeleteMLModel",)

    def process(self, models):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_model, models))

    def process_model(self, model):
        client = local_session(
            self.manager.session_factory).client('machinelearning')
        try:
            client.delete_ml_model(MLModelId=model['MLModelId'])
        except ClientError as e:
            self.log.exception(
                "Exception deleting ML model:\n %s" % e)
