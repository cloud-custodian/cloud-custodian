# Copyright 2017 Capital One Services, LLC
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

import datetime
import logging
import operator

import boto3
from botocore.exceptions import ClientError
from concurrent.futures import as_completed
import click
from tabulate import tabulate

from c7n.credentials import assumed_session, SessionFactory
from c7n.utils import format_event, chunks

from c7n_org.cli import init, filter_accounts, CONFIG_SCHEMA, WORKER_COUNT

log = logging.getLogger('c7n-guardian')


# make email required in org schema
CONFIG_SCHEMA['definitions']['account']['properties']['email'] = {'type': 'string'}
for el in CONFIG_SCHEMA['definitions']['account']['anyOf']:
    el['required'].append('email')


@click.group()
def cli():
    """Automate Guard Duty Setup."""


@cli.command()
@click.option('-c', '--config',
              required=True, help="Accounts config file", type=click.Path())
@click.option('-t', '--tags', multiple=True, default=None)
@click.option('-a', '--accounts', multiple=True, default=None)
@click.option('--master', help='Master account id or name')
@click.option('--debug', help='Run single-threaded', is_flag=True)
@click.option('--region', default='us-east-1')
def report(config, tags, accounts, master, debug, region):
    """report on guard duty enablement by account"""
    accounts_config, master_info, executor = guardian_init(
        config, debug, master, accounts, tags)

    session = get_session(
        master_info.get('role'), 'c7n-guardian',
        master_info.get('profile'),
        region)

    client = session.client('guardduty')
    detector_id = get_or_create_detector_id(client)

    members = {m['AccountId']: m for m in
               client.list_members(DetectorId=detector_id).get('Members')}

    accounts_report = []
    for a in accounts_config['accounts']:
        ar = dict(a)
        accounts_report.append(ar)
        ar.pop('tags', None)
        ar.pop('role')
        ar.pop('regions', None)
        if a['account_id'] not in members:
            ar['member'] = False
            ar['status'] = None
            ar['invited'] = None
            ar['updated'] = datetime.datetime.now().isoformat()
            continue
        m = members[a['account_id']]
        ar['status'] = m['RelationshipStatus']
        ar['member'] = True
        ar['joined'] = m['InvitedAt']
        ar['updated'] = m['UpdatedAt']

    accounts_report.sort(key=operator.itemgetter('updated'), reverse=True)
    print(tabulate(accounts_report, headers=('keys')))


@cli.command()
@click.option('-c', '--config',
              required=True, help="Accounts config file", type=click.Path())
@click.option('-t', '--tags', multiple=True, default=None)
@click.option('-a', '--accounts', multiple=True, default=None)
@click.option('--master', help='Master account id or name')
@click.option('--debug', help='Run single-threaded', is_flag=True)
@click.option('--suspend', help='Suspend monitoring in master', is_flag=True)
@click.option('--disable-detector', help='Disable detector in member account',
              is_flag=True)
@click.option('--delete-detector', help='Disable detector in member account',
              is_flag=True)
@click.option('--dissociate', help='Disassociate member account',
              is_flag=True)
@click.option('--region')
def disable(config, tags, accounts, master, debug,
            suspend, disable_detector, delete_detector, dissociate, region):
    """suspend guard duty in the given accounts."""
    accounts_config, master_info, executor = guardian_init(
        config, debug, master, accounts, tags)

    if sum(map(int, (suspend, disable_detector, dissociate))) != 1:
        raise ValueError((
            "One and only of suspend, disable-detector, dissociate"
            "can be specified."))

    master_session = get_session(
        master_info['role'], 'c7n-guardian',
        master_info.get('profile'), region)
    master_client = master_session.client('guardduty')
    detector_id = get_or_create_detector_id(master_client)

    if suspend:
        unprocessed = master_client.stop_monitoring_members(
            DetectorId=detector_id,
            AccountIds=[a['account_id'] for a in accounts_config['accounts']]
        ).get('UnprocessedAccounts', ())

        if unprocessed:
            log.warning(
                "Following accounts where unprocessed\n %s",
                format_event(unprocessed))
        log.info("Stopped monitoring %d accounts in master",
                 len(accounts_config['accounts']))
        return

    if dissociate:
        master_client.disassociate_members(
            DetectorId=detector_id,
            AccountIds=[a['account_id'] for a in accounts_config['accounts']])

    # Seems like there's a couple of ways to disable an account
    # delete the detector (member), disable the detector (master or member),
    # or disassociate members, or from member disassociate from master.
    for a in accounts_config['accounts']:
        member_session = get_session(
            a['role'], 'c7n-guardian',
            a.get('profile'), region)

        member_client = member_session.client('guardduty')
        m_detector_id = get_or_create_detector_id(member_client)
        if disable_detector:
            member_client.update_detector(
                DetectorId=m_detector_id, Enable=False)
            log.info("Disabled detector in account:%s", a['name'])
        if dissociate:
            try:
                log.info("Disassociated member account:%s", a['name'])
                result = member_client.disassociate_from_master_account(
                    DetectorId=m_detector_id)
                log.info("Result %s", format_event(result))
            except ClientError as e:
                if e.response['Error']['Code'] == 'InvalidInputException':
                    continue
        if delete_detector:
            member_client.delete_detector(DetectorId=m_detector_id)
            log.info("Deleted detector in account:%s", a['name'])


def get_session(role, session_name, profile, region):
    if role:
        return assumed_session(role, session_name, region=region)
    else:
        return SessionFactory(region, profile)()


def expand_regions(regions, partition='aws'):
    if 'all' in regions:
        regions = boto3.Session().get_available_regions('ec2')
    return regions


@cli.command()
@click.option('-c', '--config',
              required=True, help="Accounts config file", type=click.Path())
@click.option('--master', help='Master account id or name')
@click.option('-a', '--accounts', multiple=True, default=None)
@click.option('-t', '--tags', multiple=True, default=None)
@click.option('--debug', help='Run single-threaded', is_flag=True)
@click.option('--message', help='Welcome Message for member accounts')
@click.option(
    '-r', '--region',
    default=['all'], help='Region to enable (default: all)',
    multiple=True)
def enable(config, master, tags, accounts, debug, message, region):
    """enable guard duty on a set of accounts"""
    accounts_config, master_info, executor = guardian_init(
        config, debug, master, accounts, tags)
    regions = expand_regions(region)
    for r in regions:
        log.info("Processing Region:%s", r)
        enable_region(master_info, accounts_config, executor, message, r)


def enable_region(master_info, accounts_config, executor, message, region):
    master_session = get_session(
        master_info.get('role'), 'c7n-guardian',
        master_info.get('profile'),
        region=region)

    master_client = master_session.client('guardduty')
    detector_id = get_or_create_detector_id(master_client)

    results = master_client.get_paginator(
        'list_members').paginate(DetectorId=detector_id)
    extant_members = results.build_full_result().get('Members', ())
    extant_ids = {m['AccountId'] for m in extant_members}

    # Find extant members not currently enabled
    suspended_ids = {m['AccountId'] for m in extant_members
                     if m['RelationshipStatus'] == 'Disabled'}
    # Filter by accounts under consideration per config and cli flags
    suspended_ids = {a['account_id'] for a in accounts_config['accounts']
                     if a['account_id'] in suspended_ids}
    if suspended_ids:
        unprocessed = master_client.start_monitoring_members(
            DetectorId=detector_id,
            AccountIds=list(suspended_ids)).get('UnprocessedAccounts')
        if unprocessed:
            log.warning(
                "Region: %s Unprocessed accounts on re-start monitoring %s",
                region, format_event(unprocessed))
        log.info("Region: %s Restarted monitoring on %d accounts",
                 region, len(suspended_ids))

    members = [{'AccountId': account['account_id'], 'Email': account['email']}
               for account in accounts_config['accounts']
               if account['account_id'] not in extant_ids]

    if not members:
        if not suspended_ids:
            log.info("Region:%s All accounts already enabled", region)
        return

    if (len(members) + len(extant_ids)) > 1000:
        raise ValueError(
            ("Region:%s Guard Duty only supports "
             "1000 member accounts per master account") % (region))

    log.info(
        "Region:%s Enrolling %d accounts in guard duty", region, len(members))
    unprocessed = []
    for account_set in chunks(members, 25):
        unprocessed.extend(master_client.create_members(
            DetectorId=detector_id,
            AccountDetails=account_set).get('UnprocessedAccounts', []))
    if unprocessed:
        log.warning(
            "Region:%s accounts where unprocessed - member create\n %s",
            region, format_event(unprocessed))

    log.info("Region:%s Inviting %d member accounts", region, len(members))
    unprocessed = []
    for account_set in chunks(members, 25):
        params = {'AccountIds': [m['AccountId'] for m in account_set],
                  'DetectorId': detector_id}
        if message:
            params['Message'] = message
        unprocessed.extend(master_client.invite_members(
            **params).get('UnprocessedAccounts', []))
    if unprocessed:
        log.warning(
            "Region:%s accounts where unprocessed invite-members\n %s",
            region, format_event(unprocessed))

    log.info("Region:%s Accepting invitations in members", region)
    with executor(max_workers=WORKER_COUNT) as w:
        futures = {}
        for a in accounts_config['accounts']:
            if a == master_info:
                continue
            if a['account_id'] in extant_ids:
                continue
            futures[w.submit(enable_account, a, master_info['account_id'], region)] = a

        for f in as_completed(futures):
            a = futures[f]
            if f.exception():
                log.error("Region:% sError processing account:%s error:%s",
                          region, a['name'], f.exception())
                continue
            if f.result():
                log.info('Region:%s Enabled guard duty on account:%s',
                         region, a['name'])


def enable_account(account, master_account_id, region):
    member_session = get_session(
        account.get('role'), 'c7n-guardian',
        profile=account.get('profile'),
        region=region)
    member_client = member_session.client('guardduty')
    m_detector_id = get_or_create_detector_id(member_client)
    all_invitations = member_client.list_invitations().get('Invitations', [])
    invitations = [
        i for i in all_invitations
        if i['AccountId'] == master_account_id]
    invitations.sort(key=operator.itemgetter('InvitedAt'))
    if not invitations:
        log.warning(
            "Region:%s No guard duty invitation found account:%s id:%s aid:%s",
            region, account['name'], m_detector_id, account['account_id'])
        return

    member_client.accept_invitation(
        DetectorId=m_detector_id,
        InvitationId=invitations[-1]['InvitationId'],
        MasterId=master_account_id)
    return True


def get_or_create_detector_id(client):
    detectors = client.list_detectors().get('DetectorIds')
    if detectors:
        return detectors[0]
    else:
        return client.create_detector().get('DetectorId')


def get_master_info(accounts_config, master):
    master_info = None
    for a in accounts_config['accounts']:
        if a['name'] == master:
            master_info = a
            break
        if a['account_id'] == master:
            master_info = a
            break

    if master_info is None:
        raise ValueError("Master account: %s not found in accounts config" % (
            master))
    return master_info


def guardian_init(config, debug, master, accounts, tags):
    accounts_config, custodian_config, executor = init(
        config, None, debug, False, None, None, None, None)
    master_info = get_master_info(accounts_config, master)
    filter_accounts(accounts_config, tags, accounts, not_accounts=[master_info['name']])
    return accounts_config, master_info, executor

# AccountSet
#
#  get master invitation
#  get detectors
#  delete detector
#  disassociate from master
