# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n import query
from c7n.query import QueryResourceManager
from c7n.filters import CrossAccountAccessFilter, ValueFilter
from c7n.utils import local_session, type_schema


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

    def describe_bot_alias(self, bot_id, bot_alias_id):
        client = local_session(self.session_factory).client('lexv2-models')
        try:
            response = client.describe_bot_alias(botId=bot_id, botAliasId=bot_alias_id)
            return response
        except client.exceptions.ResourceNotFoundException:
            return None

    def list_bot_aliases(self, bot_id):
        client = local_session(self.session_factory).client('lexv2-models')
        aliases = []
        try:
            response = client.list_bot_aliases(botId=bot_id)
            aliases.extend(response['botAliasSummaries'])

            while 'nextToken' in response:
                response = client.list_bot_aliases(botId=bot_id, nextToken=response['nextToken'])
                aliases.extend(response['botAliasSummaries'])
            return aliases
        except client.exceptions.ResourceNotFoundException:
            return None


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


@LexV2Bot.filter_registry.register('conversationlogs')
class ContentFilter(ValueFilter):
    """Filters all LexV2 bots with conversationlogs enabled

    :example:

    .. code-block:: yaml

            policies:
              - name: lex-bot-conversationlogs
                resource: lexv2-bot
                filters:
                   - type: conversationlogs
                     key: conversationLogSettings.textLogSettings [?enabled == `true`]
                     value: not-null
    """


    schema = type_schema('conversationlogs', rinherit=ValueFilter.schema)
    schema_alias = False

    permissions = ('lex:describe_bot_alias',)
    policy_annotation = 'c7n:BotAlias'
    bot_annotation = "c7n:BotAlias"


def process(self, resources, event=None):
    client = local_session(self.manager.session_factory).client('lexv2-models')
    results = []
    for r in resources:
        if self.bot_annotation not in r:
            aliases = self.manager.retry(client.list_bot_aliases, botId=r['botId'])
            if 'botAliasSummaries' in aliases:
                for alias in aliases['botAliasSummaries']:
                    bot_alias_id = alias['botAliasId']
                    doc = self.manager.retry(client.describe_bot_alias, botId=r['botId'], botAliasId=bot_alias_id)
                    if doc:
                        doc.pop('ResponseMetadata', None)
                        r[self.bot_annotation] = doc
                        r['conversationLogSettings'] = doc.get('conversationLogSettings', {})
            else:
                continue
        if self.match(r[self.bot_annotation]):
            r[self.policy_annotation] = self.data.get('value')
            results.append(r)
    return results
