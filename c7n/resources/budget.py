from c7n.policy import LambdaMode
from c7n.utils import type_schema
from c7n.mu import SNSSubscription

from .aws import shape_validate


class BudgetMode(LambdaMode):

    permissions = (
        'budgets:CreateBudget',
        'budgets:DescribeBudget',
        'budgets:UpdateBudget',
        'sns:CreateTopic',
        'sns:Subscribe',
        'sns:DeleteTopic',
    )

    schema = type_schema(
        'budget',
        budget={'type': 'object'},
        trigger={
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'ComparisonOperator': {
                    'enum': ['GREATER_THAN', 'LESS_THAN', 'EQUAL_TO']
                },
                'Threshold': {'type': 'number'},
                'ThresholdType': {'enum': ['PERCENTAGE', 'ABSOLUTE_VALUE']},
                'NotificationState': {'enum': ['OK', 'ALARM']},
            },
        },
    )

    supported_resources = ['account']

    def validate(self):
        if self.policy.resource_type not in self.supported_resources:
            raise PolicyValidationError(
                "budget-mode not supported with resource %s"
                % (self.policy.resource_type)
            )
        super().validate()
        shape_validate(self.get_budget_config(), 'budgets', 'Budget')

    def get_budget_config(self):
        budget_config = self.data.get('budget')
        budget_config['BudgetName'] = self.policy.name
        return budget_config

    def provision(self):
        func = super().provision()
        budget = BudgetSubscription(
            self.manager.session_factory, self.get_budget_config(), self.data['trigger']
        )
        budget.add(func)
        return func


class BudgetSubscription:
    def __init__(self, session_factory, account_id, budget_config, notify_config):
        self.session_factory = session_factory
        self.budget_config = budget_config
        self.notify_config = notify_config
        self.account_id = account_id

    def add(self, func):
        topic = self.provision_topic(func)
        self.provision_budget(func, topic)

    def remove(self, func):
        self.deprovision_budget(func)
        self.deprovision_topic(func)

    def provision_topic(self, func):
        sns = local_session(self.manager.session_factory).client('sns')
        result = sns.create_topic(func.name)
        topic_arn = result['TopicArn']
        subscription = SNSSubscription(self.session_factory, [topic_arn])
        subscription.add(func)
        return topic_arn

    def deprovision_topic(self, func):
        sns = local_session(self.manager.session_factory).client('sns')
        sns.remove_topic(func.name)

    def deprovision_budget(self, func):
        budgets = local_session(self.manager.session_factory).client('budgets')
        budgets.delete_budget(AccountId=self.account_id, BudgetName=func.name)

    def provision_budget(self, func, topic_arn):
        budgets = local_session(self.manager.session_factory).client('budgets')
        params = {
            'AccountId': self.account_id,
            'Budget': self.budget_config,
            'NotificationsWithSubscribers': {
                'Notification': self.data['trigger'],
                'Subscribers': {'SubscriptionType': 'SNS', 'Address': topic_arn},
            },
        }

        try:
            return budgets.create_budget(**params)
        except budgets.exceptions.DuplicateRecordException:
            pass

        # extant budget, check config and subscribers
        budget_name = params['Budget']['BudgetName']

        if self.delta_budget(budgets, params):
            params['NewBudget'] = params.pop('Budget')
            subscribers = params.pop('NotificationsWithSubscribers')
            budgets.update_budget(**params)

        self.ensure_subscriber(budgets, topic_arn)

    def delta_budget(self, client, budget_name, budget_config):
        current = client.describe_budget(
            AccountId=self.account_id, BudgetName=BudgetName
        ).get('Budget')
        for k, v in budget_config.items():
            if current.get(k) != v:
                return True

    def ensure_subscriber(self, client, budget_name, topic_arn):
        # notifications don't have an identity, so we need to map them
        # back to subscribers
        notifications = budgets.describe_notifications_for_budget(
            AccountId=self.account_id, BudgetName=budget_name
        )

        for n in notifications:
            budgets.describe_subscribers_for_notification()
