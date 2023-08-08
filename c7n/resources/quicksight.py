# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n import query


class DescribeQuicksight(query.DescribeSource):

    def resources(self, query):
        required = {
            "Namespace": "default",
            "AwsAccountId": self.manager.config.account_id
        }
        return super().resources(required)


@resources.register("quicksight-user")
class QuicksightUser(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "quicksight"
        enum_spec = ('list_users', 'UserList', None)
        arn_type = "user"
        arn = "Arn"
        id = "UserName"
        name = "UserName"

    source_mapping = {
        "describe": DescribeQuicksight,
    }


@resources.register("quicksight-group")
class QuicksightGroup(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "quicksight"
        enum_spec = ('list_groups', 'GroupList', None)
        arn_type = "group"
        arn = "Arn"
        id = "GroupName"
        name = "GroupName"

    source_mapping = {
        "describe": DescribeQuicksight,
    }
