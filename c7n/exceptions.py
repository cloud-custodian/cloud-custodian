# Copyright 2018 Capital One Services, LLC
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

try:
    from botocore.exceptions import ClientError
except ImportError:
    class ClientError(Exception):
        """dummy boto api error"""


class CustodianError(Exception):
    """Custodian Exception Base Class
    """


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
