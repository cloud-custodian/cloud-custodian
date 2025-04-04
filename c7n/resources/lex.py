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
        enum_spec = ('list_bots', 'botSummaries', {'maxResults': 1000})
        arn_type = "bot"
        arn_service = "lex"
        id = "botId"
        name = "botName"
        cfn_type = config_type = "AWS::Lex::Bot"
        universal_taggable = object()
        permission_prefix = "lex"

    source_mapping = {"describe": query.DescribeWithResourceTags, "config": query.ConfigSource}


class LexV2BotAliasDescribe(query.ChildDescribeSource):
    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('lexv2-models')
        sts_client = local_session(self.manager.session_factory).client('sts')
        account_id = sts_client.get_caller_identity().get('Account')
        region = self.manager.session_factory.region
        for r in resources:
            botalias = client.describe_bot_alias(
                botId=r['c7n:parent-id'], botAliasId=r['botAliasId'])
            r.update(botalias)
            r['botArn'] = f'arn:aws:lex:{region}:{account_id}:bot/{r["c7n:parent-id"]}'
            r['botAliasArn'] = (
                f'arn:aws:lex:{region}:{account_id}:bot-alias/{r["c7n:parent-id"]}/{r["botAliasId"]}')
            tags_response = client.list_tags_for_resource(
                resourceArn=r['botAliasArn'])
            r['tags'] = tags_response.get('tags', {})
        return resources


@resources.register('lexv2-bot-alias')
class LexV2BotAlias(query.ChildResourceManager):
    class resource_type(query.TypeInfo):
        service = 'lexv2-models'
        parent_spec = ('lexv2-bot', 'botId', True)
        enum_spec = ('list_bot_aliases', 'botAliasSummaries', None)
        name = 'botAliasId'
        id = 'botAliasId'
        universal_taggable = object()
        arn = 'botAliasArn'
        arn_service = 'lex'
        cfn_type = config_type = "AWS::Lex::BotAlias"
        permissions_enum = ('lex:DescribeBotAlias',)

    source_mapping = {'describe-child': LexV2BotAliasDescribe, 'config': query.ConfigSource}


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
