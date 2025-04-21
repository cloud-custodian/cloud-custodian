# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n import query
from c7n.query import QueryResourceManager
from c7n.filters import CrossAccountAccessFilter
from c7n.utils import local_session, type_schema
from c7n.tags import TagActionFilter, universal_augment
from c7n.actions import BaseAction


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
        for r in resources:
            botalias = client.describe_bot_alias(
                botId=r['c7n:parent-id'], botAliasId=r['botAliasId'])
            r.update(botalias)
        return universal_augment(self.manager, resources)


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
        cfn_type = 'AWS::Lex::BotAlias'
        permission_prefix = "lex"
    source_mapping = {'describe-child': LexV2BotAliasDescribe, 'config': query.ConfigSource}

    def get_arns(self, resources):
        arns = []
        for r in resources:
            arns.append(self.generate_arn(f"bot-alias/{r['c7n:parent-id']}/{r['botAliasId']}"))
        return arns


LexV2BotAlias.action_registry.register('mark-for-op')


@LexV2BotAlias.filter_registry.register('marked-for-op')
class MarkedForOpFilter(TagActionFilter):
    """
    Filter LexV2 bot aliases marked for a specific operation.

    :example:

    .. code-block:: yaml

            policies:
              - name: delete-marked-lex-bot-alias
                resource: lexv2-bot-alias
                filters:
                  - type: marked-for-op
                    tag: custodian_cleanup
                    op: delete
    """
    schema = type_schema('marked-for-op', rinherit=TagActionFilter.schema)
    permissions = ('lex:ListTagsForResource',)


@LexV2BotAlias.action_registry.register('delete')
class DeleteLexV2BotAlias(BaseAction):
    """
    Deletes LexV2 bot aliases.

    :example:

    .. code-block:: yaml

            policies:
              - name: delete-lex-bot-alias
                resource: lexv2-bot-alias
                actions:
                  - type: delete
    """
    schema = type_schema('delete')
    permissions = ('lex:DeleteBotAlias',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('lexv2-models')
        for r in resources:
            client.delete_bot_alias(
                botAliasId=r['botAliasId'],
                botId=r['c7n:parent-id']
            )


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


@LexV2BotAlias.filter_registry.register('cross-account')
class LexV2BotAliasCrossAccountAccessFilter(CrossAccountAccessFilter):
    """Filters all LexV2 bot aliases with cross-account access

    :example:

    .. code-block:: yaml

            policies:
              - name: lex-bot-alias-cross-account
                resource: lexv2-bot-alias
                filters:
                  - type: cross-account
                    whitelist_from:
                      expr: "accounts.*.accountNumber"
                      url: accounts_url
    """
    permissions = ('lex:DescribeResourcePolicy',)
    policy_attribute = 'c7n:Policy'
