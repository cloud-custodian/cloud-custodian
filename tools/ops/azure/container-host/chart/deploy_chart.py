# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


import abc
import logging
import os
import re
import tempfile

import click
import yaml

from c7n.resources import load_resources
from c7n.utils import local_session
from c7n_azure.constants import ENV_CONTAINER_QUEUE_NAME, ENV_SUB_ID
from c7n_azure.session import Session

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("c7n_azure.container-host.deploy")

MANAGEMENT_GROUP_TYPE = '/providers/Microsoft.Management/managementGroups'
SUBSCRIPTION_TYPE = '/subscriptions'


class Deployment:

    def __init__(self, ctx):
        self.dry_run = ctx.parent.params.get('dry_run')
        self.deployment_name = ctx.parent.params.get('deployment_name')
        self.deployment_namespace = ctx.parent.params.get('deployment_namespace')
        self.helm_values_file = ctx.parent.params.get('helm_values_file')
        self.helm_set_values = ctx.parent.params.get('helm_set', [])

        self.subscription_hosts = []

        load_resources()
        self.session = local_session(Session)

    @abc.abstractmethod
    def prepare_subscription_hosts(self):
        raise NotImplementedError()

    def run(self):
        self.prepare_subscription_hosts()

        with open(self.helm_values_file, 'r') as values_file:
            values = yaml.load(values_file)
        sub_hosts = values.setdefault('subscriptionHosts', [])
        sub_hosts += self.subscription_hosts
        values_file_path = Deployment.write_values_to_file(values)

        logger.info("Created values file at {}\n".format(values_file_path))
        values_yaml = yaml.dump(values)
        logger.info(values_yaml)

        # Currently deploy the helm chart through a system command, this assumes helm is installed
        # and configured with the target cluster.
        logger.info("Deploying with helm")
        helm_command = self.build_helm_command(values_file_path)
        logger.info(helm_command)
        exit_status = os.system(helm_command)

        os.remove(values_file_path)
        if exit_status:
            exit(exit_status)

    def add_subscription_host(self, name, environment={}, secret_environment={}):

        self.subscription_hosts.append({
            'name': name,
            'environment': environment,
            'secretEnvironment': secret_environment,
        })

    def build_helm_command(self, values_file_path):
        command = 'helm upgrade --install --debug'
        if self.dry_run:
            command += ' --dry-run'
        if self.deployment_namespace:
            command += ' --namespace {}'.format(self.deployment_namespace)
        command += '\\\n\t --values {}'.format(values_file_path)
        for helm_set_value in self.helm_set_values:
            command += '\\\n\t --set {}'.format(helm_set_value)
        chart_path = os.path.dirname(__file__) or os.getcwd()
        command += '\\\n\t {} {}'.format(self.deployment_name, chart_path)
        return command

    @staticmethod
    def sub_name_to_deployment_name(sub_name):
        # Deployment names must use only lower case alpha numeric characters, -, _, and .
        # They must also start/end with an alpha numeric character
        return re.sub(r'[^A-Za-z0-9-\._]+', '-', sub_name).strip('-_.').lower()

    @staticmethod
    def write_values_to_file(values):
        _, values_file_path = tempfile.mkstemp(suffix='.yaml')
        with open(values_file_path, 'w') as values_file:
            yaml.dump(values, stream=values_file)
        return values_file_path


class SubscriptionDeployment(Deployment):

    def __init__(self, ctx, subscription_id=None):
        super(SubscriptionDeployment, self).__init__(ctx)
        self.subscription_id = subscription_id
        self.run()

    def prepare_subscription_hosts(self):
        client = self.session.client('azure.mgmt.subscription.SubscriptionClient')
        subscription = client.subscriptions.get(self.subscription_id)
        self.add_subscription_host(
            Deployment.sub_name_to_deployment_name(subscription.display_name),
            {
                ENV_SUB_ID: self.subscription_id,
                ENV_CONTAINER_QUEUE_NAME: 'c7n-{}'.format(self.subscription_id[-4:])
            }
        )


class ManagementGroupDeployment(Deployment):

    def __init__(self, ctx, management_group_id=None):
        super(ManagementGroupDeployment, self).__init__(ctx)
        self.management_group_id = management_group_id
        self.run()

    def prepare_subscription_hosts(self):
        self._add_subscription_hosts()

    def _add_subscription_hosts(self):
        client = self.session.client('azure.mgmt.managementgroups.ManagementGroupsAPI')
        info = client.management_groups.get(
            self.management_group_id, expand='children', recurse=True)
        self._add_subscription_hosts_from_info(info)

    def _add_subscription_hosts_from_info(self, info):
        if info.type == SUBSCRIPTION_TYPE:
            sub_id = info.name  # The 'name' field of child info is the subscription id
            self.add_subscription_host(
                Deployment.sub_name_to_deployment_name(info.display_name),
                {
                    ENV_SUB_ID: sub_id,
                    ENV_CONTAINER_QUEUE_NAME: 'c7n-{}'.format(info.name[-4:])
                },
            )
        elif info.type == MANAGEMENT_GROUP_TYPE and info.children:
            for child in info.children:
                self._add_subscription_hosts_from_info(child)


@click.group()
@click.option('--deployment-name', '-d', default='cloud-custodian')
@click.option('--deployment-namespace', '-n', default='cloud-custodian')
@click.option('--helm-values-file', '-v', required=True)
@click.option('--helm-set', '-s', multiple=True)
@click.option('--dry-run/--no-dry-run', default=False)
def cli(deployment_name, deployment_namespace, helm_values_file=None, helm_set=None, dry_run=False):
    pass


@cli.command('subscription')
@click.option('--subscription-id', '-i', required=True)
@click.pass_context
class SubscriptionDeploymentCommand(SubscriptionDeployment):
    pass


@cli.command('management_group')
@click.option('--management-group-id', '-i', required=True)
@click.pass_context
class ManagementGroupDeploymentCommand(ManagementGroupDeployment):
    pass


if __name__ == '__main__':
    cli()
