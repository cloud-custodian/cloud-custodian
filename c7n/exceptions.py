# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

try:
    from botocore.exceptions import ClientError
except ImportError:
    class ClientError(Exception):
        """dummy boto api error"""


class CustodianError(Exception):
    """Custodian Exception Base Class
    """


class InvalidOutputConfig(CustodianError):
    """Invalid configuration for an output"""


class PolicySyntaxError(CustodianError):
    """Policy Syntax Error
    """


class PolicyYamlError(PolicySyntaxError):
    """Policy Yaml Structural Error
    """


class PolicyValidationError(PolicySyntaxError):
    """Policy Validation Error
    """


class DeprecationError(PolicySyntaxError):
    """Policy using deprecated syntax
    """


class PolicyExecutionError(CustodianError):
    """Error running a Policy.
    """


class ResourceLimitExceeded(PolicyExecutionError):
    """The policy would have affected more resources than its limit.
    """
    def __init__(self, msg, limit_type, limit, selection_count, population_count):
        msg = msg.format(
            limit=limit,
            selection_count=selection_count,
            population_count=population_count)
        super(ResourceLimitExceeded, self).__init__(msg)
        self.limit = limit
        self.limit_type = limit
        self.selection_count = selection_count
        self.population_count = population_count


class ResourceGroupTagError(ClientError):

    MSG_TEMPLATE = (
        'An error occurred tagging {err_count} resources when calling {operation_name} '
        'operation{retry_info}'
    )

    def __init__(self, metadata, errors, operation_name):
        retry_info = self._get_retry_info({"ResponseMetadata": metadata})
        msg = self.MSG_TEMPLATE.format(
            operation_name=operation_name,
            retry_info=retry_info,
            err_count=len(errors)
        )

        super(ClientError, self).__init__(msg)
        self.operation_name = operation_name
        self.errors = errors
        self.metadata = metadata
