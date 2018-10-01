
import json

from mock import Mock

from c7n.config import Bag
from c7n.resources import aws

from .common import BaseTest


class AWSUtilsTest(BaseTest):
    pass


class OutputS3Test(BaseTest):
    pass


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


class OutputLogTest(BaseTest):

    def test_log_handler(self):
        pass


class OutputCloudWatchMetricsTest(BaseTest):
    pass
