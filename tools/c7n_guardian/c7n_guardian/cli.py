# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import datetime
import logging
import operator

import boto3
from botocore.exceptions import ClientError
from concurrent.futures import as_completed
import click
from tabulate import tabulate

from c7n.credentials import SessionFactory
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
@click.option(
    '-r', '--region',
    default=['all'], help='Region to report on (default: all)',
    multiple=True)
def report(config, tags, accounts, master, debug, region):
    """report on guard duty enablement by account"""
    _, _, executor = guardian_init(
        config, debug, master, accounts, tags)

    regions = expand_regions(region)

    accounts_report = []
    with executor(max_workers=WORKER_COUNT) as w:
        futures = {}
        for region in regions:
            futures[w.submit(report_one_region,
                             config,
                             tags,
                             accounts,
                             master,
                             debug,
                             region)] = region

        for f in as_completed(futures):
            region = futures[f]

            if f.exception():
                log.error(f"{region}\tError processing:{f.exception()}")
                continue
            if f.result():
                accounts_report += f.result()

    accounts_report.sort(key=operator.itemgetter('updated'), reverse=True)
    print(tabulate(accounts_report, headers=('keys')))


def report_one_region(
    config,
    tags,
    accounts,
    master,
    debug,
    region,
):
    """report on guard duty enablement by account"""
    accounts_config, master_info, _ = guardian_init(
        config, debug, master, accounts, tags)

    master_session = get_session(
        master_info['role'],
        'c7n-guardian',
        master_info.get('profile'),
        region,
    )
    master_client = master_session.client('guardduty')
    detector_id = get_or_create_detector_id(master_client)
    if not detector_id:
        return []

    members = {}
    for page in master_client.get_paginator('list_members').paginate(DetectorId=detector_id):
        for member in page['Members']:
            members[member['AccountId']] = member

    accounts_report = []
    for a in accounts_config['accounts']:
        ar = dict(a)
        ar.pop('tags', None)
        ar.pop('role')
        ar.pop('regions', None)
        ar['region'] = region
        if a['account_id'] in members:
            m = members[a['account_id']]
            ar['status'] = m['RelationshipStatus']
            ar['member'] = True
            ar['joined'] = m['InvitedAt']
            ar['updated'] = m['UpdatedAt']
        else:
            ar['member'] = False
            ar['status'] = None
            ar['invited'] = None
            ar['updated'] = datetime.datetime.now().isoformat()
        accounts_report.append(ar)
    return accounts_report


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
    accounts_config, master_info, _ = guardian_init(
        config, debug, master, accounts, tags)

    if sum(map(int, (suspend, disable_detector, dissociate))) != 1:
        raise ValueError((
            "One and only of suspend, disable-detector, dissociate"
            " can be specified."))

    master_session = get_session(
        master_info['role'], 'c7n-guardian',
        master_info.get('profile'), region)
    master_client = master_session.client('guardduty')
    detector_id = get_or_create_detector_id(master_client)
    if not detector_id:
        # Couldn't get a detector in this region; perhaps region not opted-in
        return

    if suspend:
        unprocessed = master_client.stop_monitoring_members(
            DetectorId=detector_id,
            AccountIds=[a['account_id'] for a in accounts_config['accounts']]
        ).get('UnprocessedAccounts', ())

        if unprocessed:
            log.warning(f"""{region}\tFollowing accounts where
                        unprocessed\n{format_event(unprocessed)}""")
        log.info(f"""{region}\tStopped monitoring
                 {len(accounts_config['accounts'])} accounts in master""")
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
        if not detector_id:
            # Couldn't get a detector in this region; perhaps region not opted-in
            continue
        if disable_detector:
            member_client.update_detector(
                DetectorId=m_detector_id, Enable=False)
            log.info(f"{region}\tDisabled detector in account:{a['name']}")
        if dissociate:
            try:
                log.info(f"{region}\tDisassociated member account:%s", a['name'])
                result = member_client.disassociate_from_master_account(
                    DetectorId=m_detector_id)
                log.info(f"{region}\tResult %s", format_event(result))
            except ClientError as e:
                if e.response['Error']['Code'] == 'InvalidInputException':
                    continue
        if delete_detector:
            member_client.delete_detector(DetectorId=m_detector_id)
            log.info(f"{region}\tDeleted detector in account:{a['name']}")


def get_session(role, session_name, profile, region):
    if role:
        sts_client = boto3.client('sts')
        sts_response = sts_client.assume_role(RoleArn=role, RoleSessionName=session_name)
        assumed_session = boto3.session.Session(
            aws_access_key_id=sts_response['Credentials']['AccessKeyId'],
            aws_secret_access_key=sts_response['Credentials']['SecretAccessKey'],
            aws_session_token=sts_response['Credentials']['SessionToken'],
            region_name=region,
        )
        return assumed_session
    else:
        # No role, just use current session
        return SessionFactory(region, profile)()


def expand_regions(regions, partition='aws'):
    if 'all' in regions:
        regions = boto3.Session().get_available_regions('guardduty')
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
@click.option(
    '--enable-email-notification',
    help='Email account owners when inviting',
    is_flag=True)
def enable(config, master, tags, accounts, debug, message, region, enable_email_notification):
    """enable guard duty on a set of accounts"""
    accounts_config, master_info, executor = guardian_init(
        config, debug, master, accounts, tags)
    regions = expand_regions(region)

    with executor(max_workers=WORKER_COUNT) as w:
        futures = []
        for region in regions:
            futures.append(w.submit(enable_region, master_info, accounts_config,
                                    executor, message, region,
                                    enable_email_notification))

        for f in as_completed(futures):
            if f.exception():
                log.error(f"{region}\tError processing: {f.exception()}")
                continue
            if f.result():
                log.info(f"{region}\t{len(f.result())} active member accounts")


def enable_region(
        master_info,
        accounts_config,
        executor,
        message,
        region,
        enable_email_notification):

    master_session = get_session(
        master_info.get('role'), 'c7n-guardian',
        master_info.get('profile'),
        region=region)

    master_client = master_session.client('guardduty')
    detector_id = get_or_create_detector_id(master_client)
    if not detector_id:
        # Couldn't get a detector in this region; perhaps region not opted-in
        log.info(f"""{region}\tCouldn't get or create GuardDuty detector with role
                 {master_info.get('role')} - Perhaps the region isn't enabled?""")
        return

    # The list gd_members contains active GuardDuty Member Accounts
    # If the account is in the specified account list (.yml) and not in gd_members,
    # we'll ensure it's emabled
    results = master_client.get_paginator(
        'list_members').paginate(DetectorId=detector_id, OnlyAssociated="True")
    gd_members = results.build_full_result().get('Members', ())
    gd_member_ids = {m['AccountId'] for m in gd_members}

    # Build this the ugly way to ensure we break if there's an unexpected RelationshipStatus;
    # rather break than silently pass
    active_ids = []
    invited_ids = []
    suspended_ids = []
    resigned_ids = []
    removed_ids = []
    for m in gd_members:
        if m['RelationshipStatus'] == 'Enabled':
            active_ids.append(m['AccountId'])
        elif m['RelationshipStatus'] in ['Invited']:
            invited_ids.append(m['AccountId'])
        elif m['RelationshipStatus'] == 'Disabled':
            suspended_ids.append(m['AccountId'])
        elif m['RelationshipStatus'] == 'Removed':
            # The GD detector has been entirely removed - re-invite & accept
            removed_ids.append(m['AccountId'])
        elif m['RelationshipStatus'] == 'Resigned':
            # If member is Resigned = member has switched off the master (GD still enabled though)
            # We should not re-invite, but should re-accept
            resigned_ids.append(m['AccountId'])
        else:
            raise Exception(f'''GuardDuty member account {m["AccountId"]} had
                            unknown RelationshipStatus
                            "{m["RelationshipStatus"]}" - bailing''')
    # Filter by accounts under consideration per config and cli flags
    suspended_ids = {a['account_id'] for a in accounts_config['accounts']
        if a['account_id'] in suspended_ids}

    if suspended_ids:
        unprocessed = master_client.start_monitoring_members(
            DetectorId=detector_id,
            AccountIds=list(suspended_ids)).get('UnprocessedAccounts')
        if unprocessed:
            log.warning(f"""{region}\tUnprocessed accounts on re-start monitoring
                        {format_event(unprocessed)}""")
        log.info("{region}\tRestarted monitoring on {len(suspended_ids)} accounts")

    accounts_not_members = [{'AccountId': account['account_id'], 'Email': account['email']}
               for account in accounts_config['accounts']
               if account['account_id'] not in gd_member_ids]

    if not accounts_not_members:
        if not suspended_ids and not invited_ids and not resigned_ids and not removed_ids:
            log.info(f"{region}\tAll accounts already enabled")
            return list(active_ids)

    if (len(accounts_not_members) + len(gd_member_ids)) > 1000:
        raise ValueError(f"""{region}\tGuard Duty only supports 1000 member
                         accounts per master account""")

    log.info(f"{region}\tEnrolling {len(accounts_not_members)} accounts in guard duty")

    unprocessed = []
    for account_set in chunks(accounts_not_members, 25):
        new_members = master_client.create_members(DetectorId=detector_id,
                                                   AccountDetails=account_set)
        unprocessed.extend(new_members.get('UnprocessedAccounts', []))
        # If the account was already a member, ignore
        unprocessed = list(filter(lambda x: x['Result'].find('already a membe') == -1, unprocessed))
    if unprocessed:
        log.warning(f"""{region}\tAccounts were unprocessed - member create
                    {format_event(unprocessed)}""")

    log.info(f"{region}\tInviting {len(accounts_not_members)} member accounts")
    unprocessed = []
    for account_set in chunks(
        [m for m in accounts_not_members if m['AccountId'] not in invited_ids + resigned_ids],
        25
    ):
        params = {
            'AccountIds': [m['AccountId'] for m in account_set],
            'DetectorId': detector_id,
            'DisableEmailNotification': not enable_email_notification,
        }
        if message:
            params['Message'] = message
        unprocessed.extend(master_client.invite_members(
            **params).get('UnprocessedAccounts', []))
    if unprocessed:
        log.warning(f"""{region}\tAccounts were unprocessed invite-members
                    {format_event(unprocessed)}""")

    accounts_not_members = [{'AccountId': account['account_id'], 'Email': account['email']}
               for account in accounts_config['accounts']
               if account['account_id'] not in active_ids]

    log.info(f"{region}\tAccepting {len(accounts_not_members)} invitations in members")

    with executor(max_workers=WORKER_COUNT) as w:
        futures = {}
        for a in accounts_config['accounts']:
            if a == master_info:
                continue
            if a['account_id'] in active_ids:
                continue
            futures[w.submit(enable_account, a, master_info['account_id'], region)] = a

        for f in as_completed(futures):
            a = futures[f]
            if f.exception():
                log.error(f"{region}\tError processing account:{a['name']} error:{f.exception()}")
                continue
            if f.result():
                log.info(f"{region}\tEnabled guard duty on account:{a['name']}")
    return accounts_not_members


def enable_account(account, master_account_id, region):
    member_session = get_session(
        account.get('role'), 'c7n-guardian',
        profile=account.get('profile'),
        region=region)
    member_client = member_session.client('guardduty')
    m_detector_id = get_or_create_detector_id(member_client)
    if not m_detector_id:
        # Couldn't get a detector in this region; perhaps region not opted-in
        log.info(f"""{region}\tCouldn't get or create GuardDuty detector with role
                 {account.get('role')} - Perhaps the region isn't enabled?""")
        return
    all_invitations = member_client.list_invitations().get('Invitations', [])
    invitations = [
        i for i in all_invitations
        if i['AccountId'] == master_account_id]
    invitations.sort(key=operator.itemgetter('InvitedAt'))
    if not invitations:
        log.warning(f"""{region}\tNo guard duty invitation found Account
                    Name:{account['name']} ID: {account['account_id']} Detector
                    ID:{m_detector_id}""")
        return

    member_client.accept_invitation(
        DetectorId=m_detector_id,
        InvitationId=invitations[-1]['InvitationId'],
        MasterId=master_account_id)
    return True


def get_or_create_detector_id(client):
    try:
        detectors = client.list_detectors().get('DetectorIds')
    except ClientError as e:
        # Occurs if the region is unavailable / not opted-in
        # Regions available:        https://docs.aws.amazon.com/general/latest/gr/guardduty.html
        # Regions requiring opt-in:
        # https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-regions-availability-zones.html#concepts-available-regions
        if e.response['Error']['Code'] == 'UnrecognizedClientException':
            return None

    if detectors:
        return detectors[0]
    else:
        return client.create_detector(Enable=True).get('DetectorId')


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
    accounts_config, _, executor = init(
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
