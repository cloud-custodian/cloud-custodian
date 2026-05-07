from c7n.filters import ListItemFilter
from c7n.utils import local_session
from c7n.utils import type_schema


class BedrockModelInvocationLoggingFilter(ListItemFilter):
    """Filter for account to look at bedrock model invocation logging configuration
    The schema to supply to the attrs follows the schema here:
    https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock/client/get_model_invocation_logging_configuration.html

    :example:

    .. code-block:: yaml

            policies:
              - name: bedrock-model-invocation-logging-configuration
                resource: account
                filters:
                  - type: bedrock-model-invocation-logging
                    attrs:
                      - imageDataDeliveryEnabled: True
    """
    schema = type_schema(
        'bedrock-model-invocation-logging',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )
    permissions = ('bedrock:GetModelInvocationLoggingConfiguration',)
    annotation_key = 'c7n:BedrockModelInvocationLogging'

    def __init__(self, data, manager=None):
        super().__init__(data, manager)
        self._config_cache = None
        self._config_is_cached = False

    def get_item_values(self, resource):
        if not self._config_is_cached:
            client = local_session(self.manager.session_factory).client('bedrock')
            self._config_cache = (
                client.get_model_invocation_logging_configuration().get('loggingConfig')
            )
            self._config_is_cached = True

        if self._config_cache is None:
            return []

        resource[self.annotation_key] = self._config_cache
        return [self._config_cache]
