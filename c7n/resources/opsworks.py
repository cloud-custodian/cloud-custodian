# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from botocore.exceptions import ClientError

from c7n.actions import BaseAction
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource
from c7n.utils import local_session, type_schema
from c7n import utils


class DescribeRemoved(DescribeSource):
    def resources(self, query):
        return []

    def get_resources(self, resource_ids):
        return []


@resources.register('opswork-stack')
class OpsworkStack(QueryResourceManager):
    """OpsWorks Stack is no longer an available service. This resource
    soley exists for policy compatiblity.
    """

    class resource_type(TypeInfo):
        service = 'account'
        id = 'StackId'
        name = 'Name'
        arn = "Arn"
        cfn_type = 'AWS::OpsWorks::App'

    source_mapping = {'describe': DescribeRemoved}


@OpsworkStack.action_registry.register('delete')
class DeleteStack(BaseAction):
    """Deprecated action"""

    schema = type_schema('delete')
    permissions = (
        "opsworks:DescribeApps",
        "opsworks:DescribeLayers",
        "opsworks:DescribeInstances",
        "opsworks:DeleteStack",
        "opsworks:DeleteApp",
        "opsworks:DeleteLayer",
        "opsworks:DeleteInstance",
    )

    def process(self, stacks):
        return []


@OpsworkStack.action_registry.register('stop')
class StopStack(BaseAction):
    """Deprecated Action"""

    schema = type_schema('stop')
    permissions = ("opsworks:StopStack",)

    def process(self, stacks):
        return []


@resources.register('opswork-cm')
class OpsworksCM(QueryResourceManager):
    """OpsWorks CM is no longer an available service. This resource
    soley exists for policy compatiblity.
    """

    class resource_type(TypeInfo):
        service = "account"
        name = id = 'ServerName'
        arn = "ServerArn"
        cfn_type = 'AWS::OpsWorksCM::Server'

    source_mapping = {'describe': DescribeRemoved}


@OpsworksCM.action_registry.register('delete')
class CMDelete(BaseAction):
    """Deprecated action"""

    schema = type_schema('delete')
    permissions = ("opsworks-cm:DeleteServer",)

    def process(self, servers):
        return []
