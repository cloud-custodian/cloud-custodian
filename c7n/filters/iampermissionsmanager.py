from itertools import chain
import re


def cache_permissions(decorated):
    cache = {}

    def wrapped(self, *args):
        if args in cache:
            return cache[args]
        else:
            value = decorated(self, *args)
            cache[args] = value
            return value

    return wrapped


class IamPermissionsManager(object):

    class Statement(object):
        def __init__(self, source, action, statement):
            self.source = source
            self.statement = statement
            self.action = action
            self.resource = statement['Resource']
            self.effect = statement['Effect']

            expression = "\A%s\Z" % re.escape(action).replace("\\*", ".*")
            self.re = re.compile(expression)

        def matches(self, action):
            return self.re.match(action) is not None

        def action(self, action):
            if self.matches(action):
                return self.effect
            else:
                return None

        def serializable(self):
            return {'source': self.source, 'action': self.action, 'statement': self.statement}

    class StatementList(object):

        def __init__(self, statements):
            self.statements = list(statements)

        @classmethod
        def load(cls, serialized):
            def make_statement(item):
                return IamPermissionsManager.Statement(item['source'],
                    item['action'], item['statement'])
            statements = map(make_statement, serialized)
            return cls(statements)

        def serialize(self):
            return self.serializeList(self.statements)

        def for_action(self, action):
            matching = [statement for statement in self.statements if statement.matches(action)]
            actions = set(s.effect for s in matching)

            if 'Deny' in actions:
                return ('Deny', self.serializeList(matching))
            elif any(actions):
                return ('Allow', self.serializeList(matching))
            else:
                return ('Unknown', [])

        def serializeList(self, list):
            return [s.serializable() for s in list]

    def __init__(self, client):
        self.client = client
        self.cache = {}

    @cache_permissions
    def for_user(self, user):
        return IamPermissionsManager.StatementList(self.policy_documents_for_user(user))

    @cache_permissions
    def for_group(self, group):
        return IamPermissionsManager.StatementList(self.policy_documents_for_group(group))

    @cache_permissions
    def for_role(self, role):
        return IamPermissionsManager.StatementList(self.policy_documents_for_role(role))

    @cache_permissions
    def for_role_arn(self, role_arn):
        if not role_arn:
            return IamPermissionsManager.StatementList([])
        name = role_arn.split(":role/")[1]
        if not name:
            return IamPermissionsManager.StatementList([])
        else:
            return self.for_role(name)

    @cache_permissions
    def for_instance_profile(self, instance_profile):
        if not instance_profile:
            return IamPermissionsManager.StatementList([])
        profile = self.client.get_instance_profile(InstanceProfileName=instance_profile)['InstanceProfile']
        arns = [role['Arn'] for role in profile['Roles']]
        combined = chain.from_iterable(self.for_role_arn(arn).serialize() for arn in arns)
        return IamPermissionsManager.StatementList.load(combined)

    @cache_permissions
    def policy_documents_for_user(self, user):
        user_policies = self.all_for('list_user_policies', 'PolicyNames', UserName=user)
        expanded_user_policies = chain.from_iterable(
            self.policy_documents_for_user_policy(name, user) for name in user_policies)
        attached_policies = self.all_attached_policies_for('list_attached_user_policies',
            UserName=user)
        user_groups = self.all_for('list_groups_for_user', 'Groups', UserName=user)
        group_policies = chain.from_iterable(
            self.policy_documents_for_group(group['GroupName']) for group in user_groups)

        return chain.from_iterable(
            [expanded_user_policies, attached_policies, group_policies])

    @cache_permissions
    def policy_documents_for_group(self, group):
        attached_policies = self.all_attached_policies_for('list_attached_group_policies',
            GroupName=group)
        inline_policies = self.all_for('list_group_policies', 'PolicyNames', GroupName=group)
        expanded_inline_policies = chain.from_iterable(
            self.policy_documents_for_group_policy(name, group) for name in inline_policies)
        return chain.from_iterable([expanded_inline_policies, attached_policies])

    @cache_permissions
    def policy_documents_for_role(self, role):
        attached_policies = self.all_attached_policies_for('list_attached_role_policies',
            RoleName=role)
        inline_policies = self.all_for('list_role_policies', 'PolicyNames', RoleName=role)
        expanded_inline_policies = chain.from_iterable(
            self.policy_documents_for_role_policy(name, role) for name in inline_policies)
        return chain.from_iterable([expanded_inline_policies, attached_policies])

    def all_attached_policies_for(self, list_method, **args):
        attached_policies = self.all_for(list_method, 'AttachedPolicies',
            **args)
        expanded_attached_policies = chain.from_iterable(
            self.policy_documents_for_policy(policy['PolicyArn']) for policy in attached_policies)
        return expanded_attached_policies

    @cache_permissions
    def policy_documents_for_policy(self, policy_arn):
        policy = self.client.get_policy(PolicyArn=policy_arn)['Policy']
        version = self.client.get_policy_version(PolicyArn=policy_arn,
            VersionId=policy['DefaultVersionId'])
        source = {'type': 'policy', 'arn': policy_arn}
        return self.normalise_document(version['PolicyVersion']['Document'], source)

    @cache_permissions
    def policy_documents_for_user_policy(self, policy_name, user_name):
        policy = self.client.get_user_policy(UserName=user_name, PolicyName=policy_name)
        source = {'type': 'user_policy', 'user_name': user_name, 'policy_name': policy_name}
        return self.normalise_document(policy['PolicyDocument'], source)

    @cache_permissions
    def policy_documents_for_group_policy(self, policy_name, group_name):
        policy = self.client.get_group_policy(GroupName=group_name, PolicyName=policy_name)
        source = {'type': 'group_policy', 'group_name': group_name, 'policy_name': policy_name}
        return self.normalise_document(policy['PolicyDocument'], source)

    @cache_permissions
    def policy_documents_for_role_policy(self, policy_name, role_name):
        policy = self.client.get_role_policy(RoleName=role_name, PolicyName=policy_name)
        source = {'type': 'role_policy', 'role_name': role_name, 'policy_name': policy_name}
        return self.normalise_document(policy['PolicyDocument'], source)

    def normalise_document(self, document, source):
        out = []
        statements = document.get('Statements', None)
        if statements is None:
            statements = document['Statement']
        if isinstance(statements, dict):
            statements = [statements]
        for statement in statements:
            actions = statement['Action']
            if not type(actions) is list:
                actions = list(actions)
            for action in actions:
                parsed = IamPermissionsManager.Statement(source, action, statement)
                out.append(parsed)
        return out

    def all_for(self, operation, key, **args):
        paginator = self.client.get_paginator(operation)
        iterator = paginator.paginate(**args)
        return chain.from_iterable(page[key] for page in iterator)
