# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from botocore.exceptions import ClientError

from c7n.actions import BaseAction
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.utils import local_session, type_schema


@resources.register('ml-model')
class MLModel(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'machinelearning'
        enum_spec = ('describe_ml_models', 'Results', None)
        id = 'MLModelId'
        name = 'Name'
        date = 'CreatedAt'
        # need to specify request-mode dimension as well
        # dimension = 'MLModelId'
        arn_type = "mlmodel"
        permissions_enum = ('machinelearning:DescribeMLModels',)


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
