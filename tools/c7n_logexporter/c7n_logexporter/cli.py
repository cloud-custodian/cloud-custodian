import boto3
import click
from c7n.credentials import assumed_session
from c7n.utils import get_retry
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
from dateutil.tz import tzutc, tzlocal
from dateutil.parser import parse
import jsonschema
import logging
import time


log = logging.getLogger('c7n-log-exporter')

@click.group()
def cli():
    """c7n cloudwatch log group exporter"""


@cli.command()
@click.option('--group', required=True)
@click.option('--bucket', required=True)
@click.option('--prefix')
@click.option('--start', required=True)
@click.option('--end')
#@click.option('--period', type=float)
@click.option('--role')
@click.option('--task-name', default="c7n-log-exporter")
@click.option('--stream-prefix')
def export(group, bucket, prefix, start, end, role, task_name, stream_prefix):

    logging.basicConfig(level=logging.INFO)
    logging.getLogger('botocore').setLevel(logging.WARNING)

    start = parse(start)
    end = end and parse(end) or datetime.datetime.now()

    start = start.replace(tzinfo=tzlocal()).astimezone(tzutc())
    end = end.replace(tzinfo=tzlocal()).astimezone(tzutc())
    
    if role:
        session = assumed_session(role, task_name)
    else:
        session = boto3.Session()
    
    client = session.client('logs')
    retry = get_retry(('LimitExceededException',))

    if prefix:
        prefix = "%s/%s" % (prefix.rstrip('/'), bucket)
    else:
        prefix = bucket

    with ThreadPoolExecutor(max_workers=2) as w:
        futures = {}
        for d in range(abs((start-end).days)):
            date = start + datetime.timedelta(d)
            date = date.replace(minute=0, microsecond=0, hour=0)
            prefix += date.strftime("/%Y-%m-%d")

            params = {
                'taskName': "%s-%s" % (task_name, date.strftime("%Y-%m-%d")),
                'logGroupName': group,
                'fromTime': int(time.mktime(
                    date.replace(minute=0, microsecond=0, hour=0
                    ).timetuple()) * 1000),
                'to': int(time.mktime(
                    date.replace(minute=59, hour=23, microsecond=0
                    ).timetuple()) * 1000),
                'destination': bucket,
            }

            if stream_prefix:
                params['logStreamPrefix'] = stream_prefix
            if prefix:
                params['destinationPrefix'] = prefix

            futures[w.submit(retry, client.create_export_task, **params)] = params

        for f in as_completed(futures):
            result = f.result()
            p = futures[f]
            log.info("Log export group:%s day:%s bucket:%s prefix:%s task:%s",
                     group,
                     p['taskName'],
                     bucket,
                     p['destinationPrefix'],
                     result['taskId'])


if __name__ == '__main__':
    cli()


    
    
