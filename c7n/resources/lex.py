# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n import query


@resources.register("lex-bot")
class LexBot(query.QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "lex-models"
        enum_spec = ('get_bots', 'bots', None)
        arn_type = "bot"
        arn_service = "lex"
        id = "name"
        name = "name"
        cfn_type = config_type = "AWS::Lex::Bot"
        universal_taggable = object()
        permission_prefix = "lex"
        permissions_augment = ("lex:ListTagsForResource",)

    source_mapping = {"describe": query.DescribeWithResourceTags, "config": query.ConfigSource}
