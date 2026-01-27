# Copyright 2017 Manheim / Cox Automotive
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json
import requests
from logging import Logger
from mock import Mock, call, patch
import pytest

from c7n_mailer.splunk_delivery import SplunkHecDelivery

pbm = "c7n_mailer.splunk_delivery"
pb = "%s.SplunkHecDelivery" % pbm


class DeliveryTester:
    def setup_method(self, test_method):
        self.mock_sess = Mock()
        self.mock_logger = Mock(spec_set=Logger)
        self.config = {
            "splunk_index": "my_index_name",
            "splunk_url": "https://splunk.url/foo",
            "splunk_token": "stoken",
        }
        self.cls = SplunkHecDelivery(self.config, self.mock_sess, self.mock_logger)


class TestInit(DeliveryTester):
    def test_init(self):
        assert self.cls.logger == self.mock_logger
        assert self.cls.config == self.config
        assert self.cls.session == self.mock_sess


class TestGetSplunkPayloads(DeliveryTester):
    @patch(
        "%s.get_splunk_events" % pb, return_value=[{"account": "A", "resource": 1}, {"resource": 2}]
    )
    @patch("%s._splunk_indices_for_message" % pb, return_value=["indexA", "indexB"])
    def test_payloads(self, mock_gse, mock_sifm):
        msg = {"some": "message"}
        ts = 1557493290000
        result = self.cls.get_splunk_payloads(msg, ts)
        assert result == [
            {
                "time": ts,
                "host": "cloud-custodian",
                "source": "A-cloud-custodian",
                "sourcetype": "_json",
                "index": "indexA",
                "event": {"account": "A", "resource": 1},
            },
            {
                "time": ts,
                "host": "cloud-custodian",
                "source": "A-cloud-custodian",
                "sourcetype": "_json",
                "index": "indexB",
                "event": {"account": "A", "resource": 1},
            },
            {
                "time": ts,
                "host": "cloud-custodian",
                "source": "unknown-cloud-custodian",
                "sourcetype": "_json",
                "index": "indexA",
                "event": {"resource": 2},
            },
            {
                "time": ts,
                "host": "cloud-custodian",
                "source": "unknown-cloud-custodian",
                "sourcetype": "_json",
                "index": "indexB",
                "event": {"resource": 2},
            },
        ]
        assert mock_gse.mock_calls == [call(msg)]
        assert mock_sifm.mock_calls == [call(msg)]

    @patch(
        "%s.get_splunk_events" % pb, return_value=[{"account": "A", "resource": 1}, {"resource": 2}]
    )
    @patch("%s._splunk_indices_for_message" % pb, return_value=["indexA", "indexB"])
    def test_sourcetype(self, mock_gse, mock_sifm):
        self.config["splunk_hec_sourcetype"] = "custom-sourcetype"
        msg = {"some": "message"}
        ts = 1557493290000
        result = self.cls.get_splunk_payloads(msg, ts)
        assert result == [
            {
                "time": ts,
                "host": "cloud-custodian",
                "source": "A-cloud-custodian",
                "sourcetype": "custom-sourcetype",
                "index": "indexA",
                "event": {"account": "A", "resource": 1},
            },
            {
                "time": ts,
                "host": "cloud-custodian",
                "source": "A-cloud-custodian",
                "sourcetype": "custom-sourcetype",
                "index": "indexB",
                "event": {"account": "A", "resource": 1},
            },
            {
                "time": ts,
                "host": "cloud-custodian",
                "source": "unknown-cloud-custodian",
                "sourcetype": "custom-sourcetype",
                "index": "indexA",
                "event": {"resource": 2},
            },
            {
                "time": ts,
                "host": "cloud-custodian",
                "source": "unknown-cloud-custodian",
                "sourcetype": "custom-sourcetype",
                "index": "indexB",
                "event": {"resource": 2},
            },
        ]
        assert mock_gse.mock_calls == [call(msg)]
        assert mock_sifm.mock_calls == [call(msg)]


class TestGetSplunkEvents(DeliveryTester):
    @patch("%s.get_aws_username_from_event" % pbm, return_value="uname")
    @patch("%s._prune_log_message" % pb, return_value={"event": "cleaned"})
    def test_simple(self, mock_prune, mock_getuser):
        def se_tags(res):
            if res["InstanceId"] == "i-123":
                return {"tag1": "val1"}
            return {}

        msg = {
            "account": "aname",
            "account_id": "aid",
            "region": "rname",
            "event": {"foo": "1", "source": "esrc", "detail-type": "etype"},
            "policy": {
                "resource": "ec2",
                "name": "pname",
                "actions": ["foo", {"type": "bar"}, {"type": "notify"}, "baz"],
            },
            "resources": [
                {
                    "InstanceId": "i-123",
                    "c7n:MatchedFilters": [1, 2],
                    "Tags": [{"Key": "tag1", "Value": "val1"}],
                },
                {"InstanceId": "i-456"},
                {"InstanceId": "i-789", "c7n.metrics": {"foo": "bar"}},
            ],
        }
        with patch("%s.tags_for_resource" % pb) as mock_tags:
            mock_tags.side_effect = se_tags
            res = self.cls.get_splunk_events(msg)
        assert res == [{"event": "cleaned"}, {"event": "cleaned"}, {"event": "cleaned"}]
        assert mock_tags.mock_calls == [
            call(msg["resources"][0]),
            call(msg["resources"][1]),
            call(msg["resources"][2]),
        ]
        assert mock_getuser.mock_calls == [call(self.cls.logger, msg["event"])]
        assert mock_prune.mock_calls == [
            call(
                {
                    "account": "aname",
                    "account_id": "aid",
                    "region": "rname",
                    "event": {"foo": "1", "source": "esrc", "detail-type": "etype"},
                    "policy": {
                        "resource": "ec2",
                        "name": "pname",
                        "actions": ["foo", {"type": "bar"}, {"type": "notify"}, "baz"],
                    },
                    "resource": {
                        "InstanceId": "i-123",
                        "c7n:MatchedFilters": [1, 2],
                        "tags": {"tag1": "val1"},
                    },
                    "event_triggering_user": "uname",
                }
            ),
            call(
                {
                    "account": "aname",
                    "account_id": "aid",
                    "region": "rname",
                    "event": {"foo": "1", "source": "esrc", "detail-type": "etype"},
                    "policy": {
                        "resource": "ec2",
                        "name": "pname",
                        "actions": ["foo", {"type": "bar"}, {"type": "notify"}, "baz"],
                    },
                    "resource": {"InstanceId": "i-456", "tags": {}},
                    "event_triggering_user": "uname",
                }
            ),
            call(
                {
                    "account": "aname",
                    "account_id": "aid",
                    "region": "rname",
                    "event": {"foo": "1", "source": "esrc", "detail-type": "etype"},
                    "policy": {
                        "resource": "ec2",
                        "name": "pname",
                        "actions": ["foo", {"type": "bar"}, {"type": "notify"}, "baz"],
                    },
                    "resource": {"InstanceId": "i-789", "c7n.metrics": {"foo": "bar"}, "tags": {}},
                    "event_triggering_user": "uname",
                }
            ),
        ]

    @patch("%s.get_aws_username_from_event" % pbm, return_value="uname")
    @patch("%s._prune_log_message" % pb, return_value={"event": "cleaned"})
    def test_splunk_actions_list(self, mock_prune, mock_getuser):
        self.config["splunk_actions_list"] = True

        def se_tags(res):
            if res["InstanceId"] == "i-123":
                return {"tag1": "val1"}
            return {}

        msg = {
            "account": "aname",
            "account_id": "aid",
            "region": "rname",
            "event": {"foo": "1", "source": "esrc", "detail-type": "etype"},
            "policy": {
                "resource": "ec2",
                "name": "pname",
                "actions": ["foo", {"type": "bar"}, {"type": "notify"}, "baz"],
            },
            "resources": [
                {"InstanceId": "i-123", "c7n:MatchedFilters": [1, 2]},
                {"InstanceId": "i-456"},
                {"InstanceId": "i-789", "c7n.metrics": {"foo": "bar"}},
            ],
        }
        with patch("%s.tags_for_resource" % pb) as mock_tags:
            mock_tags.side_effect = se_tags
            res = self.cls.get_splunk_events(msg)
        assert res == [{"event": "cleaned"}, {"event": "cleaned"}, {"event": "cleaned"}]
        assert mock_tags.mock_calls == [
            call(msg["resources"][0]),
            call(msg["resources"][1]),
            call(msg["resources"][2]),
        ]
        assert mock_getuser.mock_calls == [call(self.cls.logger, msg["event"])]
        assert mock_prune.mock_calls == [
            call(
                {
                    "account": "aname",
                    "account_id": "aid",
                    "region": "rname",
                    "event": {"foo": "1", "source": "esrc", "detail-type": "etype"},
                    "policy": {
                        "resource": "ec2",
                        "name": "pname",
                        "actions": ["foo", {"type": "bar"}, {"type": "notify"}, "baz"],
                    },
                    "resource": {
                        "InstanceId": "i-123",
                        "c7n:MatchedFilters": [1, 2],
                        "tags": {"tag1": "val1"},
                    },
                    "event_triggering_user": "uname",
                    "actions": ["foo", "bar", "notify", "baz"],
                }
            ),
            call(
                {
                    "account": "aname",
                    "account_id": "aid",
                    "region": "rname",
                    "event": {"foo": "1", "source": "esrc", "detail-type": "etype"},
                    "policy": {
                        "resource": "ec2",
                        "name": "pname",
                        "actions": ["foo", {"type": "bar"}, {"type": "notify"}, "baz"],
                    },
                    "resource": {"InstanceId": "i-456", "tags": {}},
                    "event_triggering_user": "uname",
                    "actions": ["foo", "bar", "notify", "baz"],
                }
            ),
            call(
                {
                    "account": "aname",
                    "account_id": "aid",
                    "region": "rname",
                    "event": {"foo": "1", "source": "esrc", "detail-type": "etype"},
                    "policy": {
                        "resource": "ec2",
                        "name": "pname",
                        "actions": ["foo", {"type": "bar"}, {"type": "notify"}, "baz"],
                    },
                    "resource": {"InstanceId": "i-789", "c7n.metrics": {"foo": "bar"}, "tags": {}},
                    "event_triggering_user": "uname",
                    "actions": ["foo", "bar", "notify", "baz"],
                }
            ),
        ]


class TestPruneLogMessage(DeliveryTester):
    def test_no_paths(self):
        msg = {"foo": "bar", "resource": {"c7n.metrics": []}}
        assert self.cls._prune_log_message(msg) == msg

    def test_no_values(self):
        msg = {
            "foo": "123",
            "bar": ["A", "B", "C"],
            "baz": {"blam": {"one": 1, "two": 2, "three": 3, "four": 4}, "blarg": {"quux": False}},
        }
        self.config["splunk_remove_paths"] = ["/no/value/here", "/bad", "/not/a/path"]
        expected = {
            "foo": "123",
            "bar": ["A", "B", "C"],
            "baz": {"blam": {"one": 1, "two": 2, "three": 3, "four": 4}, "blarg": {"quux": False}},
        }
        assert self.cls._prune_log_message(msg) == expected

    def test_remove_some(self):
        msg = {
            "foo": "123",
            "bar": ["A", "B", "C"],
            "baz": {"blam": {"one": 1, "two": 2, "three": 3, "four": 4}, "blarg": {"quux": False}},
            "resource": {"r1": "r2", "c7n.metrics": ["a", "b"]},
        }
        self.config["splunk_remove_paths"] = [
            "/bar/1",
            "/baz/blarg",
            "/baz/blam/one",
            "/baz/blam/two",
            "/not/a/path",
            "/resource/c7n.metrics",
        ]
        expected = {
            "foo": "123",
            "bar": ["A", "C"],
            "baz": {"blam": {"three": 3, "four": 4}},
            "resource": {"r1": "r2"},
        }
        assert self.cls._prune_log_message(msg) == expected


class TestDeliverSplunkMessages(DeliveryTester):
    def test_handle_success(self):
        msg = [{"foo": "bar"}, {"baz": "blam"}]
        with patch("%s._try_send" % pb, autospec=True) as mock_send:
            mock_send.return_value = True
            self.cls.deliver_splunk_messages(msg)
        assert mock_send.mock_calls == [
            call(self.cls, {"foo": "bar"}),
            call(self.cls, {"baz": "blam"}),
        ]

    def test_handle_failure(self):
        msg = [{"foo": "bar"}, {"baz": "blam"}]
        with patch("%s._try_send" % pb, autospec=True) as mock_send:
            mock_send.side_effect = [True, False]
            with pytest.raises(RuntimeError):
                self.cls.deliver_splunk_messages(msg)
        assert mock_send.mock_calls == [
            call(self.cls, {"foo": "bar"}),
            call(self.cls, {"baz": "blam"}),
        ]


class TestTrySend(DeliveryTester):
    def test_success(self):
        self.config["splunk_max_attempts"] = 3
        self.config["splunk_hex_max_length"] = None
        with patch("%s.sleep" % pbm) as mock_sleep:
            with patch("%s.uniform" % pbm) as mock_uniform:
                with patch("%s._send_splunk" % pb) as mock_send:
                    mock_uniform.return_value = 1.2
                    res = self.cls._try_send({"foo": "bar"})
        assert res is True
        assert mock_sleep.mock_calls == []
        assert mock_uniform.mock_calls == []
        assert mock_send.mock_calls == [call('{"foo": "bar"}')]
        assert self.mock_logger.mock_calls == []

    def test_payload_too_long(self):
        self.config["splunk_max_attempts"] = 3
        self.config["splunk_hec_max_length"] = 3000
        p = {}
        for i in range(1, 2000):
            p["%d" % i] = i
        j = json.dumps(p)
        with patch("%s.sleep" % pbm) as mock_sleep:
            with patch("%s.uniform" % pbm) as mock_uniform:
                with patch("%s._send_splunk" % pb) as mock_send:
                    mock_uniform.return_value = 1.2
                    self.cls._try_send(p)
        assert mock_sleep.mock_calls == []
        assert mock_uniform.mock_calls == []
        assert mock_send.mock_calls == [call(j)]
        assert self.mock_logger.mock_calls == [
            call.error(
                "ERROR: Sending %d characters to Splunk HEC; line length "
                "limit is %d characters. Data will be truncated: %s",
                25772,
                3000,
                j,
            )
        ]

    def test_fail_once(self):
        self.config["splunk_max_attempts"] = 3
        self.config["splunk_hex_max_length"] = None
        with patch("%s.sleep" % pbm) as mock_sleep:
            with patch("%s.uniform" % pbm) as mock_uniform:
                with patch("%s._send_splunk" % pb) as mock_send:
                    mock_uniform.return_value = 1.2
                    mock_send.side_effect = [
                        # raise an Exception first time, succeed second
                        RuntimeError("foo"),
                        None,
                    ]
                    res = self.cls._try_send({"foo": "bar"})
        assert res is True
        assert mock_sleep.mock_calls == [call(1.2)]
        assert mock_uniform.mock_calls == [call(1, 4)]
        assert mock_send.mock_calls == [call('{"foo": "bar"}'), call('{"foo": "bar"}')]
        assert self.mock_logger.mock_calls == [
            call.warning("Caught exception sending to Splunk; retry in %s seconds", 1.2)
        ]

    def test_fail_always(self):
        self.config["splunk_max_attempts"] = 3
        self.config["splunk_hex_max_length"] = None
        with patch("%s.sleep" % pbm) as mock_sleep:
            with patch("%s.uniform" % pbm) as mock_uniform:
                with patch("%s._send_splunk" % pb) as mock_send:
                    mock_uniform.return_value = 1.2
                    mock_send.side_effect = RuntimeError("foo")
                    res = self.cls._try_send({"foo": "bar"})
        assert res is False
        assert mock_sleep.mock_calls == [call(1.2), call(1.2), call(1.2)]
        assert mock_uniform.mock_calls == [call(1, 4), call(1, 4), call(1, 4)]
        assert mock_send.mock_calls == [
            call('{"foo": "bar"}'),
            call('{"foo": "bar"}'),
            call('{"foo": "bar"}'),
        ]
        assert self.mock_logger.mock_calls == [
            call.warning("Caught exception sending to Splunk; retry in %s seconds", 1.2),
            call.warning("Caught exception sending to Splunk; retry in %s seconds", 1.2),
            call.warning("Caught exception sending to Splunk; retry in %s seconds", 1.2),
            call.error("ERROR - Could not POST to Splunk after %d tries.", 3),
        ]


class TestSendSplunk(DeliveryTester):
    def test_send(self):
        self.config["splunk_hec_url"] = "https://splunk.url/foo"
        self.config["splunk_hec_token"] = "stoken"
        m_resp = Mock(spec_set=requests.models.Response)
        type(m_resp).status_code = 200
        type(m_resp).text = '{"text": "Success"}'
        type(m_resp).headers = {"H1": "V1"}
        m_resp.json.return_value = {"text": "Success"}
        with patch("%s.requests" % pbm, autospec=True) as mock_req:
            mock_req.post.return_value = m_resp
            self.cls._send_splunk('{"foo": "bar"}')
        assert mock_req.mock_calls == [
            call.post(
                "https://splunk.url/foo",
                headers={"Authorization": "Splunk stoken"},
                data='{"foo": "bar"}',
            ),
            call.post().json(),
        ]
        assert self.mock_logger.mock_calls == [
            call.debug("Send to Splunk (%s): %s", "https://splunk.url/foo", '{"foo": "bar"}'),
            call.debug(
                "Splunk POST got response code %s HEADERS=%s BODY: %s",
                200,
                {"H1": "V1"},
                '{"text": "Success"}',
            ),
        ]

    def test_send_exception(self):
        self.config["splunk_hec_url"] = "https://splunk.url/foo"
        self.config["splunk_hec_token"] = "stoken"

        def se_post(*args, **kwargs):
            raise Exception("foo")

        with patch("%s.requests" % pbm, autospec=True) as mock_req:
            mock_req.post.side_effect = se_post
            with pytest.raises(Exception):
                self.cls._send_splunk('{"foo": "bar"}')
        assert mock_req.mock_calls == [
            call.post(
                "https://splunk.url/foo",
                headers={"Authorization": "Splunk stoken"},
                data='{"foo": "bar"}',
            )
        ]
        assert self.mock_logger.mock_calls == [
            call.debug("Send to Splunk (%s): %s", "https://splunk.url/foo", '{"foo": "bar"}'),
            call.error(
                "Exception during Splunk POST to %s of %s",
                "https://splunk.url/foo",
                '{"foo": "bar"}',
                exc_info=True,
            ),
        ]

    def test_send_bad_status(self):
        self.config["splunk_hec_url"] = "https://splunk.url/foo"
        self.config["splunk_hec_token"] = "stoken"
        m_resp = Mock(spec_set=requests.models.Response)
        type(m_resp).status_code = 403
        type(m_resp).text = '{"text": "Success"}'
        type(m_resp).headers = {"H1": "V1"}
        m_resp.json.return_value = {"text": "Success"}
        with patch("%s.requests" % pbm, autospec=True) as mock_req:
            mock_req.post.return_value = m_resp
            with pytest.raises(RuntimeError):
                self.cls._send_splunk('{"foo": "bar"}')
        assert mock_req.mock_calls == [
            call.post(
                "https://splunk.url/foo",
                headers={"Authorization": "Splunk stoken"},
                data='{"foo": "bar"}',
            )
        ]
        assert self.mock_logger.mock_calls == [
            call.debug("Send to Splunk (%s): %s", "https://splunk.url/foo", '{"foo": "bar"}'),
            call.debug(
                "Splunk POST got response code %s HEADERS=%s BODY: %s",
                403,
                {"H1": "V1"},
                '{"text": "Success"}',
            ),
            call.error(
                "Splunk POST returned non-20x response: %s HEADERS=%s BODY: %s",
                403,
                {"H1": "V1"},
                '{"text": "Success"}',
            ),
        ]

    def test_send_non_success(self):
        self.config["splunk_hec_url"] = "https://splunk.url/foo"
        self.config["splunk_hec_token"] = "stoken"
        m_resp = Mock(spec_set=requests.models.Response)
        type(m_resp).status_code = 200
        type(m_resp).text = '{"text": "Failure"}'
        type(m_resp).headers = {"H1": "V1"}
        m_resp.json.return_value = {"text": "Failure"}
        with patch("%s.requests" % pbm, autospec=True) as mock_req:
            mock_req.post.return_value = m_resp
            with pytest.raises(RuntimeError):
                self.cls._send_splunk('{"foo": "bar"}')
        assert mock_req.mock_calls == [
            call.post(
                "https://splunk.url/foo",
                headers={"Authorization": "Splunk stoken"},
                data='{"foo": "bar"}',
            ),
            call.post().json(),
        ]
        assert self.mock_logger.mock_calls == [
            call.debug("Send to Splunk (%s): %s", "https://splunk.url/foo", '{"foo": "bar"}'),
            call.debug(
                "Splunk POST got response code %s HEADERS=%s BODY: %s",
                200,
                {"H1": "V1"},
                '{"text": "Failure"}',
            ),
            call.error("Splunk POST returned non-success response: %s", {"text": "Failure"}),
        ]

    def test_send_non_success_no_json(self):
        self.config["splunk_hec_url"] = "https://splunk.url/foo"
        self.config["splunk_hec_token"] = "stoken"

        def se_exc(*args, **kwargs):
            raise Exception("foo")

        m_resp = Mock(spec_set=requests.models.Response)
        type(m_resp).status_code = 200
        type(m_resp).text = '{"text": "Failure"}'
        type(m_resp).headers = {"H1": "V1"}
        m_resp.json.side_effect = se_exc
        with patch("%s.requests" % pbm, autospec=True) as mock_req:
            mock_req.post.return_value = m_resp
            with pytest.raises(RuntimeError):
                self.cls._send_splunk('{"foo": "bar"}')
        assert mock_req.mock_calls == [
            call.post(
                "https://splunk.url/foo",
                headers={"Authorization": "Splunk stoken"},
                data='{"foo": "bar"}',
            ),
            call.post().json(),
        ]
        assert self.mock_logger.mock_calls == [
            call.debug("Send to Splunk (%s): %s", "https://splunk.url/foo", '{"foo": "bar"}'),
            call.debug(
                "Splunk POST got response code %s HEADERS=%s BODY: %s",
                200,
                {"H1": "V1"},
                '{"text": "Failure"}',
            ),
            call.error(
                "Splunk POST returned non-success response: %s", {"text": '{"text": "Failure"}'}
            ),
        ]


class TestTagsForResource(DeliveryTester):
    def test_empty_resource(self):
        assert self.cls.tags_for_resource({}) == {}

    def test_tags_none(self):
        assert self.cls.tags_for_resource({"Tags": None}) == {}

    def test_tags_list(self):
        assert self.cls.tags_for_resource(
            {"Tags": [{"Key": "foo", "Value": "bar"}, {"Key": "one", "Value": "two"}]}
        ) == {"foo": "bar", "one": "two"}


class TestSplunkIndicesForMessage(DeliveryTester):
    def test_no_message(self):
        assert self.cls._splunk_indices_for_message(None) == []

    def test_no_action(self):
        assert self.cls._splunk_indices_for_message({"foo": "bar"}) == []

    def test_action_no_to(self):
        assert self.cls._splunk_indices_for_message({"action": {"foo": "bar"}}) == []

    def test_simple(self):
        msg = {
            "action": {
                "to": {
                    "foo",
                    "splunkhec://bar",
                    "baz@example.com",
                    "splunkhec://blam",
                    "slack://quux",
                }
            }
        }
        expected = ["bar", "blam"]
        res = self.cls._splunk_indices_for_message(msg)
        assert res == expected
