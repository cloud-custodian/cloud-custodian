# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging
import time

import click
import requests
from c7n_azure.policy import AzureFunctionMode
from c7n.vendored.distutils.util import strtobool
from enum import Enum

from c7n.config import Config
from c7n.policy import load as policy_load, PolicyCollection

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('AzureFunctionsLC')


class DeploymentStatus(Enum):
    Active = 0
    Failed = 1
    Succeeded = 2
    NotFound = 3


def load_policies(config_files, config):
    policies = PolicyCollection([], config)
    for f in config_files:
        policies += policy_load(config, f)
    return policies


def wait_for_remote_builds(deployments):
    total = len(deployments)
    finished = 0

    while finished < total:
        for name, params in deployments.items():
            try:
                params['status'] = get_build_status(params['scm_uri'])
            except Exception:
                params['status'] = DeploymentStatus.Active

            if params['status'] == DeploymentStatus.Active:
                continue
            log.info("Remote build for %s finished with status %s.",
                     name, params['status'])
            finished += 1

        if finished < total:
            log.info("Waiting for all remote builds to finish... %i/%i finished.",
                     finished, total)
            time.sleep(30)


def get_build_status(scm_uri):
    is_deploying_uri = '%s/api/isdeploying' % scm_uri
    is_deploying = requests.get(is_deploying_uri).json()['value']

    if strtobool(is_deploying):
        return DeploymentStatus.Active

    # Get build status
    deployments_uri = '%s/deployments' % scm_uri
    r = requests.get(deployments_uri).json()
    if len(r) == 0:
        return DeploymentStatus.NotFound

    status = r[0]['status']
    if status == 3:
        return DeploymentStatus.Failed

    return DeploymentStatus.Succeeded


@click.command(help="Waits for Azure Functions deployment status for given policies")
@click.option("--config", "-c", required=True, multiple=True, help="List of config files")
def cli(**kwargs):
    policy_config = Config.empty()
    policies = PolicyCollection([
        p for p in load_policies(kwargs['config'], policy_config)
        if p.provider_name == 'azure'], policy_config)

    session = policies.policies[0].session_factory()
    web_client = session.client('azure.mgmt.web.WebSiteManagementClient')

    deployments = {}
    credentials_load_failed = 0
    not_functions_policy = 0
    for p in policies:
        if not p.is_lambda:
            not_functions_policy += 1
            continue
        try:
            params = AzureFunctionMode(p).get_function_app_params()
            creds = web_client.web_apps.begin_list_publishing_credentials(
                params.function_app_resource_group_name,
                params.function_app_name).result()
            deployments[p.name] = {'scm_uri': creds.scm_uri, 'status': None}
            log.info('Retrieved deployment credentials for %s policy', p.name)
        except Exception:
            log.error('Unable to retrieve deployment credentials for %s policy', p.name)
            credentials_load_failed += 1

    wait_for_remote_builds(deployments)

    success = 0
    fail = 0
    not_found = 0
    for name, params in deployments.items():
        if params['status'] != DeploymentStatus.Succeeded:
            log.info('%s: %s', name, params['status'])
            if params['status'] == DeploymentStatus.Failed:
                log.error('Build logs can be retrieved here: %s', params['scm_uri'])
                fail += 1
            else:
                not_found += 1
        else:
            success += 1

    log.info('Policies total: %i, unable to load credentials: %i, not Functions mode: %i',
             len(policies), credentials_load_failed, not_functions_policy)
    log.info('Status not found can happen if Linux Consumption function was deployed'
             'more than 2 hours ago.')
    log.info('Deployments complete. Success: %i, Fail: %i, Status not found: %i',
             success, fail, not_found)


if __name__ == "__main__":
    cli()
