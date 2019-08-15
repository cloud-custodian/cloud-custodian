# Copyright 2019 Microsoft Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import logging
import os
import tempfile

import click
import yaml

logger = logging.getLogger("c7n_azure.container-host.deploy")


class Deployment(object):

    def __init__(self, ctx, default_environment=None):
        logging.basicConfig(level=logging.INFO, format='%(message)s')

        self.dry_run = ctx.parent.params.get('dry_run')

        self.deployment_name = ctx.parent.params.get('deployment_name')
        self.deployment_namespace = ctx.parent.params.get('deployment_namespace')

        self.image_repository = ctx.parent.params.get('image_repository')
        self.image_tag = ctx.parent.params.get('image_tag')
        self.image_pull_policy = ctx.parent.params.get('image_pull_policy')

        self.default_environment = default_environment
        self.subscription_hosts = []

    def run(self):
        values = self.build_values_dict()
        values_file_path = Deployment.write_values_to_file(values)

        logger.info("Created values file at {}\n".format(values_file_path))
        values_yaml = yaml.dump(values)
        logger.info(values_yaml)

        helm_command = Deployment.build_helm_command(
            self.deployment_name, values_file_path, namespace=self.deployment_namespace,
            dry_run=self.dry_run)

        logger.info("Deploying with helm")
        logger.info(helm_command)
        os.system(helm_command)

    def build_values_dict(self):
        values = {}

        # custom image fields
        self._set_image_field(values, 'repository', self.image_repository)
        self._set_image_field(values, 'tag', self.image_tag)
        self._set_image_field(values, 'pullPolicy', self.image_pull_policy)

        # default environment variables for each host
        if self.default_environment:
            values['defaultEnvironment'] = self.default_environment

        # A list of configurations for individual hosts
        values['subscriptionHosts'] = self.subscription_hosts
        return values

    def _set_image_field(self, values, key, value):
        if value:
            values.setdefault('image', {})[key] = value

    def add_subscription_host(self, name='', environment={}):
        self.subscription_hosts.append({
            'name': name,
            'environment': environment,
        })

    @staticmethod
    def write_values_to_file(values):
        values_file_path = tempfile.mktemp(suffix='.yaml')
        with open(values_file_path, 'w') as values_file:
            yaml.dump(values, stream=values_file)
        return values_file_path

    @staticmethod
    def build_helm_command(deployment_name, values_file_path, namespace=None, dry_run=False):
        command = 'helm upgrade --install --debug'
        if dry_run:
            command += ' --dry-run'
        if namespace:
            command += ' --namespace {}'.format(namespace)
        command += ' --values {}'.format(values_file_path)
        chart_path = os.path.join(os.path.dirname(__file__), 'chart')
        command += ' {} {}'.format(deployment_name, chart_path)
        return command


class SubscriptionDeployment(Deployment):

    def __init__(self, ctx, name='', env=[]):
        super(SubscriptionDeployment, self).__init__(ctx)
        self.name = name
        self.environment = {e[0]: e[1] for e in env}

        self.run()

    def build_values_dict(self):
        self.add_subscription_host(self.name, self.environment)
        return super(SubscriptionDeployment, self).build_values_dict()


class ManagementGroupDeployment(Deployment):

    def __init__(self, ctx):
        super(ManagementGroupDeployment, self).__init__()
        raise NotImplementedError()


@click.group()
@click.option('--deployment-name', '-d', default='cloud-custodian')
@click.option('--deployment-namespace', '-s', default='cloud-custodian')
@click.option('--image-repository')
@click.option('--image-tag')
@click.option('--image-pull-policy')
@click.option('--dry-run/--no-dry-run', default=False)
def cli(deployment_name, deployment_namespace, image_repository='', image_tag='',
        image_pull_policy='', dry_run=False):
    pass


@cli.command('subscription')
@click.option('--name', '-n', required=True)
@click.option('--env', '-e', type=click.Tuple([str, str]), multiple=True)
@click.pass_context
class SubscriptionDeploymentCommand(SubscriptionDeployment):
    pass


@cli.command('management_group')
@click.pass_context
class ManagementGroupDeploymentCommand(ManagementGroupDeployment):
    pass


if __name__ == '__main__':
    cli()
