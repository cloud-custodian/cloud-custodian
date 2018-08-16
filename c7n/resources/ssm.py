# Copyright 2016-2017 Capital One Services, LLC
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


from c7n.query import QueryResourceManager
from c7n.manager import resources
from c7n.utils import get_retry, type_schema
from c7n.filters import Filter, FilterRegistry

filters = FilterRegistry('ssmparameter.filters')


@resources.register('ssm-parameter')
class SSMParameter(QueryResourceManager):

    class resource_type(object):
        service = 'ssm'
        enum_spec = ('describe_parameters', 'Parameters', None)
        name = "Name"
        id = "Name"
        filter_name = None
        dimension = None
        universal_taggable = True

    retry = staticmethod(get_retry(('Throttled',)))
    permissions = ('ssm:GetParameters',
                   'ssm:DescribeParameters')
    filter_registry = filters


@filters.register('is-not-secure-string')
class IsNotSecureString(Filter):
    """ Matches Parameters that are not of type SecureString

    :example:

    .. code-block:: yaml

            policies:
                - name: parameters-are-not-secure-string
                  resource: ssm-parameter
                  filters:
                    - type: is-not-secure-string
    """
    permissions = ("ssm:Describe",)
    schema = type_schema('is-not-secure-string')

    def process(self, resources, event=None):
        return [param for param in resources
                if not param['Type'] == 'SecureString']
