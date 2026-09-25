# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.actions import BaseAction
from c7n.deprecated import DeprecatedResource
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.utils import type_schema


@resources.register('opswork-stack')
@DeprecatedResource(
    "OpsWorks Stacks is no longer an available AWS service",
    removed_after="2027-07-23", force_empty=True)
class OpsworkStack(QueryResourceManager):
    """OpsWorks Stack is no longer an available service. This resource
    soley exists for policy compatiblity.
    """

    class resource_type(TypeInfo):
        id = 'StackId'
        name = 'Name'
        arn = "Arn"
        cfn_type = 'AWS::OpsWorks::App'


@OpsworkStack.action_registry.register('delete')
class DeleteStack(BaseAction):
    """Deprecated action"""

    schema = type_schema('delete')
    permissions = ()

    def process(self, stacks):
        return


@OpsworkStack.action_registry.register('stop')
class StopStack(BaseAction):
    """Deprecated Action"""

    schema = type_schema('stop')
    permissions = ()

    def process(self, stacks):
        return


@resources.register('opswork-cm')
@DeprecatedResource(
    "OpsWorks CM is no longer an available AWS service",
    removed_after="2027-07-23", force_empty=True)
class OpsworksCM(QueryResourceManager):
    """OpsWorks CM is no longer an available service. This resource
    soley exists for policy compatiblity.
    """

    class resource_type(TypeInfo):
        name = id = 'ServerName'
        arn = "ServerArn"
        cfn_type = 'AWS::OpsWorksCM::Server'


@OpsworksCM.action_registry.register('delete')
class CMDelete(BaseAction):
    """Deprecated action"""

    schema = type_schema('delete')
    permissions = ()

    def process(self, servers):
        return
