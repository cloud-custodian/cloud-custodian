# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
import json
import pprint
import re
import time

import boto3
import click
import tabulate
import yaml

from c7n_sphere11.cli import BASE_URL
from c7n_sphere11.client import Client
from c7n.utils import local_session


@click.group()
def admin():
    """Sphere11, resource locks"""


@admin.command()
@click.option('--config')
def format_json(config):
    """format config for lambda exec
    """
    with open(config) as fh:
        print(json.dumps(yaml.safe_load(fh.read()), indent=2))


def render_metrics(header, values):
    if not values:
        return
    click.echo(
        "".join((
            " ",
            header.ljust(20),
            ("min:%0.1f" % min(values)).ljust(12),
            ("max:%0.1f" % max(values)).ljust(12),
            raster_metrics(values))))


def raster_metrics(data):
    BARS = u'▁▂▃▄▅▆▇█'
    incr = min(data)
    width = (max(data) - min(data)) / (len(BARS) - 1)
    bins = [i * width + incr for i in range(len(BARS))]
    indexes = [i for n in data
               for i, thres in enumerate(bins)
               if thres <= n < thres + width]
    return ''.join(BARS[i] for i in indexes)


@admin.command()
def check():
    """Sanity check api deployment
    """
    t = time.time()
    results = Client(BASE_URL).version()
    print("Endpoint", BASE_URL)
    print("Response Time %0.2f" % (time.time() - t))
    print("Headers")
    for k, v in results.headers.items():
        print(" %s: %s" % (k, v))
    print("Body")
    print(results.text)


@admin.command()
@click.option('--function', help='function name', required=True)
@click.option('--api', help='api name')
@click.option(
    '-s', '--start', help='relative time to start from', default="1h")
@click.option(
    '-p', '--period', help='metrics period', default="1m")
def metrics(function, api, start, period):
    """lambda/api/db metrics"""
    from c7n.mu import LambdaManager
    manager = LambdaManager(boto3.Session)
    start = parse_date(start)
    period = int(abs(parse_timedelta(period).total_seconds()))

    print("Lambda Metrics")
    metrics = manager.metrics(
        [{'FunctionName': function}],
        start=start, end=datetime.utcnow(),
        period=period)
    for k in ('Invocations', 'Throttles', 'Errors'):
        values = [n['Sum'] for n in metrics[0][k]]
        render_metrics(k, values)

    if not api:
        return

    print("Api Metrics")
    metrics = gateway_metrics(
        boto3.Session, api, "latest", start, datetime.utcnow(), period)
    for k, data in metrics.items():
        if "Count" in k:
            values = [n['Sum'] for n in data]
        else:
            values = [n['Average'] for n in data]
        render_metrics(k, values)

    print("Db Metrics")
    metrics = db_metrics(
        boto3.Session, "Sphere11.Dev.ResourceLocks",
        start, datetime.utcnow(), period)
    for k, data in metrics.items():
        values = [n['Average'] for n in data]
        render_metrics(k, values)


def db_metrics(session_factory, table_name, start, end, period):
    metrics = local_session(session_factory).client('cloudwatch')
    values = {}
    for m in (
            "ConsumedReadCapacityUnits",
            "ConsumedWriteCapacityUnits",
            "ThrottledRequests",
            "ReadThrottleEvents",
            "WriteThrottleEvents",
            "ReturnedItemCount",
            "SuccessfulRequestLatency"
            #  "ReturnedRecordsCount"
    ):
        values[m.replace('Capacity', '')] = metrics.get_metric_statistics(
            Namespace="AWS/DynamoDB",
            Dimensions=[
                {'Name': 'TableName', 'Value': table_name}
            ],
            Statistics=["Average"],
            StartTime=start,
            EndTime=end,
            Period=period,
            MetricName=m)['Datapoints']
    return values


def gateway_metrics(session_factory, gateway_id, stage_name, start, end, period):
    metrics = local_session(session_factory).client('cloudwatch')
    values = {}
    for m in ("4XXError", "5XError",
              "CacheHitCount", "CacheMissCount",
              "Count",
              "IntegrationLatency", "Latency"):
        values[m] = metrics.get_metric_statistics(
            Namespace="AWS/ApiGateway",
            Dimensions=[
                {'Name': 'ApiName', 'Value': gateway_id},
                {'Name': 'Stage', 'Value': stage_name},
            ],
            Statistics=["Average", "Sum"],
            StartTime=start,
            EndTime=end,
            Period=period,
            MetricName=m)['Datapoints']
    return values


def parse_timedelta(datetime_text, default=timedelta(seconds=60 * 5 * -1)):
    # from awslogs script
    ago_regexp = r'(\d+)\s?(m|minute|minutes|h|hour|hours|d|day|days|w|weeks|weeks)(?: ago)?'
    ago_match = re.match(ago_regexp, datetime_text)
    if ago_match:
        amount, unit = ago_match.groups()
        amount = int(amount)
        unit = {'m': 60, 'h': 3600, 'd': 86400, 'w': 604800}[unit[0]]
        delta = timedelta(seconds=unit * amount * -1)
    else:
        delta = -default
    return delta


def parse_date(datetime_text):
    return datetime.utcnow() + parse_timedelta(datetime_text)


@admin.command()
@click.option('--account-id', help='account id')
def records(account_id):
    """Fetch locks data
    """
    s = boto3.Session()
    table = s.resource('dynamodb').Table('Sphere11.Dev.ResourceLocks')
    results = table.scan()

    for r in results['Items']:
        if 'LockDate' in r:
            r['LockDate'] = datetime.fromtimestamp(r['LockDate'])
        if 'RevisionDate' in r:
            r['RevisionDate'] = datetime.fromtimestamp(r['RevisionDate'])

    print(tabulate.tabulate(
        results['Items'],
        headers="keys",
        tablefmt='fancy_grid'))


@admin.command()
@click.option('--function', help='function name', required=True)
def flush_pending(function):
    """Attempt to acquire any pending locks.
    """
    s = boto3.Session()
    client = s.client('lambda')
    results = client.invoke(
        FunctionName=function,
        Payload=json.dumps({'detail-type': 'Scheduled Event'})
    )
    content = results.pop('Payload').read()
    pprint.pprint(results)
    pprint.pprint(json.loads(content))


@admin.command()
def config_status():
    """ Check config status in an account.
    """
    s = boto3.Session()
    client = s.client('config')
    channels = client.describe_delivery_channel_status()[
        'DeliveryChannelsStatus']
    for c in channels:
        print(yaml.safe_dump({
            c['name']: dict(
                snapshot=str(
                    c['configSnapshotDeliveryInfo'].get('lastSuccessfulTime')),
                history=str(
                    c['configHistoryDeliveryInfo'].get('lastSuccessfulTime')),
                stream=str(
                    c['configStreamDeliveryInfo'].get('lastStatusChangeTime'))
            ),
        }, default_flow_style=False))


@admin.command()
@click.option('--account-id', required=True)
@click.option('--region', required=True)
def delta(account_id, region):
    print(Client(BASE_URL).delta(account_id, region).text)


@admin.command()
@click.option('--reload/--no-reload', default=True)
@click.option('--port', default=8080)
def local(reload, port):
    """run local app server, assumes into the account
    """
    import logging
    from bottle import run
    from app import controller, app
    from c7n.resources import load_resources
    load_resources()
    print("Loaded resources definitions")
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    if controller.db.provision():
        print("Table Created")
    run(app, reloader=reload, port=port)


if __name__ == '__main__':
    admin()
