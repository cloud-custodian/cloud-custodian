# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import MagicMock, patch
import pytest

from c7n.config import Config, Bag
from c7n.utils import parse_url_config
from c7n import statsd


def test_statsd_output():

    ctx = Bag(
        policy=Bag({'name': 'abc', 'resource_type': 'aws.ec2'}),
        options=Config.empty(**{'account_id': '112233', 'region': 'us-east-2'}),
    )

    cfg = parse_url_config('statsd://localhost:3000?tag_format=librato')

    with patch('socket.socket'):
        output = statsd.StatsdMetrics(ctx, cfg)
        assert output.get_dimensions({}) == {
            'Account': '112233',
            'Region': 'us-east-2',
            'Resource': 'aws.ec2',
            'Policy': 'abc',
        }

        messages = []
        output.statsd._send = messages.append
        output.put_metric('ResourceCount', 100, 'Count')
        assert messages.pop() == "c7n.policy.ResourceCount:100|g"


def test_client():
    client = statsd.StatsdClient('localhost', '3000')
    results = []
    client._send = results.append

    client.gauge('resources', 10)
    assert results.pop() == 'c7n.policy.resources:10|g'

    client.histogram('execution_time', 122)
    assert results.pop() == 'c7n.policy.execution_time:122|ms'

    client.set('uuid', 33)
    assert results.pop() == 'c7n.policy.uuid:33|s'

    client.increment('rate', 11)
    assert results.pop() == 'c7n.policy.rate:11|c|@1.0'

    client.decrement('rate', 11)
    assert results.pop() == 'c7n.policy.rate:-11|c|@1.0'


@pytest.mark.parametrize(
    "tag_format,msg,output",
    [
        (
            statsd.TAG_DOGSTATSD,
            'c7n.policy.resources:10|g',
            'c7n.policy.resources:10|g|#Env:Dev,Region:us-east-1',
        ),
        (
            statsd.TAG_LIBRATO,
            'c7n.policy.resources:10|g',
            'c7n.policy.resources#Env:Dev,Region:us-east-1:10|g',
        ),
        (
            statsd.TAG_SIGNALFX,
            'c7n.policy.resources:10|g',
            'c7n.policy.resources[Env:Dev,Region:us-east-1]:10|g',
        ),
        (
            statsd.TAG_INFLUXDB,
            'c7n.policy.resources:10|g',
            'c7n.policy.resources,Env:Dev,Region:us-east-1:10|g',
        ),
    ],
    ids=[
        statsd.TAG_DOGSTATSD,
        statsd.TAG_LIBRATO,
        statsd.TAG_SIGNALFX,
        statsd.TAG_INFLUXDB,
    ],
)
def test_client_tag_format(tag_format, msg, output):
    client = statsd.StatsdClient('localhost', '3000')
    client.tag_format = tag_format
    client.set_tags({'Env': 'Dev', 'Region': 'us-east-1'})
    assert client.format_tags(msg) == output


def test_client_no_tags():
    client = statsd.StatsdClient('localhost', '3000')
    assert (
        client.format_tags("c7n.policy.resources:10|g") == "c7n.policy.resources:10|g"
    )


def test_client_send():
    client = statsd.StatsdClient('localhost', '3000')
    client.sock = sock = MagicMock()
    client.gauge('resources', 10)
    assert sock.send.call_args.args == (b'c7n.policy.resources:10|g',)


def test_client_connect_close():
    with patch('socket.socket'):
        client = statsd.StatsdClient('localhost', '3000')
        client.connect()
        client.close()
