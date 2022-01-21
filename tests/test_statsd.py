import pytest

from c7n import statsd


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
