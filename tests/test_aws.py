
import json

from mock import Mock

from c7n.config import Bag
from c7n.resources import aws
from c7n import output

from .common import BaseTest


class TraceDoc(Bag):

    def serialize(self):
        return json.dumps(dict(self))


class OutputXrayTracerTest(BaseTest):

    def test_emitter(self):
        emitter = aws.XrayEmitter()
        emitter.client = m = Mock()
        doc = TraceDoc({'good': 'morning'})
        emitter.send_entity(doc)
        emitter.flush()
        m.put_trace_segments.assert_called_with(
            TraceSegmentDocuments=[doc.serialize()])


class UtilTest(BaseTest):

    def test_default_account_id_assume(self):
        config = Bag(assume_role='arn:aws:iam::644160558196:role/custodian-mu')
        aws._default_account_id(config)
        self.assertEqual(config.account_id, '644160558196')


class TracerTest(BaseTest):

    def test_tracer(self):
        session_factory = self.replay_flight_data('output-xray-trace')
        policy = Bag(name='test', resource_type='ec2')
        ctx = Bag(
            policy=policy,
            session_factory=session_factory,
            options=Bag(account_id='644160558196'))
        ctx.get_metadata = lambda *args: {}
        config = Bag()
        tracer = aws.XrayTracer(ctx, config)

        with tracer:
            try:
                with tracer.subsegment('testing') as w:
                    raise ValueError()
            except ValueError:
                pass
            self.assertNotEqual(w.cause, {})


class OutputMetricsTest(BaseTest):

    def test_metrics(self):
        session_factory = self.replay_flight_data('output-aws-metrics')
        policy = Bag(name='test', resource_type='ec2')
        ctx = Bag(session_factory=session_factory, policy=policy)
        sink = output.metrics_outputs.select('aws', ctx)
        self.assertTrue(isinstance(sink, aws.MetricsOutput))
        sink.put_metric('ResourceCount', 101, 'Count')
        sink.flush()
