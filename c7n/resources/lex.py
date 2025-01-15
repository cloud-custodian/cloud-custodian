# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n import query
from c7n.query import QueryResourceManager
from c7n.filters import CrossAccountAccessFilter
from c7n.utils import local_session


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


@resources.register("lexv2-bot")
class LexV2Bot(QueryResourceManager):
    class resource_type(query.TypeInfo):
        service = "lexv2-models"
        enum_spec = ('list_bots', 'botSummaries', None)
        arn_type = "bot"
        arn_service = "lex"
        id = "botId"
        name = "botName"
        cfn_type = config_type = "AWS::Lex::Bot"
        universal_taggable = object()
        permission_prefix = "lex"

    source_mapping = {"describe": query.DescribeWithResourceTags, "config": query.ConfigSource}


@LexV2Bot.filter_registry.register('cross-account')
class LexV2BotCrossAccountAccessFilter(CrossAccountAccessFilter):
    """Filters all LexV2 bots with cross-account access

    :example:

    .. code-block:: yaml

            policies:
              - name: lex-bot-cross-account
                resource: lexv2-bot
                filters:
                  - type: cross-account
                    whitelist_from:
                      expr: "accounts.*.accountNumber"
                      url: accounts_url
    """
    permissions = ('lex:DescribeResourcePolicy',)
    policy_attribute = 'c7n:Policy'

    def get_resource_policy(self, r):
        client = local_session(self.manager.session_factory).client('lexv2-models')
        pol = None
        if self.policy_attribute in r:
            return r[self.policy_attribute]
        result = self.manager.retry(
            client.describe_resource_policy,
            resourceArn=self.manager.generate_arn(r['botId']),
            ignore_err_codes=('ResourceNotFoundException'))
        if result:
            pol = result.get('policy', None)
            r[self.policy_attribute] = pol
        return pol
