# Copyright 2019 Manheim / Cox Automotive
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json
from time import sleep
from urllib.parse import urlparse
from random import uniform
import requests
from jsonpointer import resolve_pointer, JsonPointerException
from jsonpatch import JsonPatch
from copy import deepcopy
from .utils import get_aws_username_from_event


class SplunkHecDelivery:
    """
    Delivery class to send c7n message from SQS to Splunk HTTP Event Collector
    """

    def __init__(self, config, session, logger):
        """
        Initialize SplunkHecDelivery HEC sender.

        :param config: sqs_splunk_lambda configuration
        :type config: dict
        :param session: boto3 AWS Session
        :param logger: Logger object to write to
        """
        self.config = config
        self.logger = logger
        self.session = session

    def get_splunk_payloads(self, msg, msg_timestamp):
        """
        Given a raw c7n message dict, generate a list of payloads to send to the
        Splunk HEC.

        :param msg: c7n notification message
        :type msg: dict
        :param msg_timestamp: int timestamp (milliseconds) when message was sent
          to SQS, for use as event timestamp in Splunk.
        :type msg_timestamp: int
        :return: list of Splunk payload dicts
        :rtype: list
        """
        payloads = []
        events = self.get_splunk_events(msg)
        indices = self._splunk_indices_for_message(msg)
        sourcetype = self.config.get("splunk_hec_sourcetype", "_json")
        for event in events:
            for index in indices:
                payloads.append(
                    {
                        "time": msg_timestamp,
                        "host": "cloud-custodian",
                        "source": "%s-cloud-custodian" % event.get("account", "unknown"),
                        "sourcetype": sourcetype,
                        "index": index,
                        "event": event,
                    }
                )
        return payloads

    def get_splunk_events(self, msg):
        """
        Given a raw c7n message dict, generate a list of per-resource event
        dictionaries to send to Splunk as events.

        :param msg: c7n notification message
        :type msg: dict
        :return: list of Splunk HEC Event dicts
        :rtype: list
        """
        # if an event is present, add it to the log
        if msg.get("event", None) is not None:
            # add user to the log message, at the top level...
            user = get_aws_username_from_event(self.logger, msg["event"])
            if user is not None:
                msg["event_triggering_user"] = user
        # get a copy of the message with no resources
        base_log = dict(msg)
        base_log.pop("resources")
        base_log = deepcopy(base_log)
        # if configured, build and add actions list
        if self.config.get("splunk_actions_list", False):
            base_log["actions"] = []
            for a in msg["policy"]["actions"]:
                if isinstance(a, type({})):
                    base_log["actions"].append(a["type"])
                else:
                    base_log["actions"].append(a)
        # generate a separate Splunk message for each resource
        logs = []
        for res in msg["resources"]:
            x = dict(base_log)
            x["resource"] = dict(res)
            # ensure there's one "tags" element, and it's a dict
            tmp = self.tags_for_resource(res)
            if "Tags" in x["resource"]:
                del x["resource"]["Tags"]
            x["resource"]["tags"] = tmp
            logs.append(self._prune_log_message(x))
        return logs

    def _prune_log_message(self, msg):
        """
        If the "splunk_remove_paths" config item is not set or empty, return
        ``msg`` unaltered. Otherwise, for each RFC6901 JSON Pointer in
        "splunk_remove_paths" that points to an element present in ``msg``,
        remove that element. Return the result.

        :param msg: Splunk-ready message
        :type msg: dict
        :return: msg dict with all ``splunk_remove_paths`` elements removed
        :rtype: dict
        """
        paths = self.config.get("splunk_remove_paths", [])
        if not paths:
            return msg
        patches = []
        for path in paths:
            try:
                resolve_pointer(msg, path)
                patches.append({"op": "remove", "path": path})
            except JsonPointerException:
                pass
        if not patches:
            return msg
        msg = JsonPatch(patches).apply(msg)
        return msg

    def deliver_splunk_messages(self, payloads):
        """
        Deliver log messages to Splunk,

        :param payloads: list of payload dicts to send to Splunk
        :type payloads: list
        """
        failed = 0
        for payload in payloads:
            if not self._try_send(payload):
                failed += 1
        if failed != 0:
            raise RuntimeError(
                "ERROR: {failed} of {count} Splunk HEC messages "
                "failed to deliver.".format(failed=failed, count=len(payloads))
            )

    def _try_send(self, payload):
        """
        Retry sending payload to splunk via ``_send_splunk`` up to
        ``config["splunk_max_attempts"]`` times, sleeping a random amount
        of time between 1 and 4 seconds between each try.

        :param payload: the payload dict to send to Splunk as event data.
        :type payload: dict
        :return: True if sent successfully, False otherwise
        :rtype: bool
        """
        max_attempts = self.config.get("splunk_max_attempts", 4)
        maxlen = self.config.get("splunk_hec_max_length", None)
        p = json.dumps(payload)
        if maxlen is not None and len(p) > maxlen:
            # This is in place for Splunk installations that are configured
            # with a short maximum message length (i.e. 10,000 characters).
            self.logger.error(
                "ERROR: Sending %d characters to Splunk HEC; line length "
                "limit is %d characters. Data will be truncated: %s",
                len(p),
                maxlen,
                p,
            )
        for i in range(0, max_attempts):
            try:
                self._send_splunk(p)
                if maxlen is not None and len(p) > maxlen:
                    # never retry if we're over configured max length
                    return False
                return True  # if no exception, just return
            except Exception:
                sleep_sec = uniform(1, 4)  # random float 1 to 4
                self.logger.warning(
                    "Caught exception sending to Splunk; " "retry in %s seconds", sleep_sec
                )
                sleep(sleep_sec)
        self.logger.error("ERROR - Could not POST to Splunk after %d tries.", max_attempts)
        return False

    def _send_splunk(self, payload):
        """
        Perform the actual data send to Splunk HEC for one log entry

        :param payload: the JSON-encoded payload to send to Splunk as
          event data
        :type payload: str
        """
        url = self.config["splunk_hec_url"]
        self.logger.debug("Send to Splunk (%s): %s", url, payload)
        try:
            r = requests.post(  # nosec
                url,
                headers={"Authorization": "Splunk %s" % self.config["splunk_hec_token"]},
                data=payload,
            )
        except Exception:
            self.logger.error(
                "Exception during Splunk POST to %s of %s", url, payload, exc_info=True
            )
            raise
        self.logger.debug(
            "Splunk POST got response code %s HEADERS=%s BODY: %s", r.status_code, r.headers, r.text
        )
        if r.status_code not in [200, 201, 202]:
            self.logger.error(
                "Splunk POST returned non-20x response: %s HEADERS=%s BODY: %s",
                r.status_code,
                r.headers,
                r.text,
            )
            raise RuntimeError("POST returned %s" % r.status_code)
        try:
            j = r.json()
        except Exception:
            j = {"text": r.text}
        if j["text"].lower() != "success":
            self.logger.error("Splunk POST returned non-success response: %s", j)
            raise RuntimeError("POST returned non-success response: %s" % j)

    def tags_for_resource(self, res):
        """
        Return the tags for a given resource, or an empty dict if they
        can't be found.

        :param res: c7n resource info
        :type res: dict
        :return: dict of tags
        """
        try:
            return {x["Key"]: x["Value"] for x in res.get("Tags", [])}
        except Exception:
            self.logger.warning("Exception building tags dict; Tags=%s", res.get("Tags", None))
            return {}

    @staticmethod
    def _splunk_indices_for_message(msg):
        """
        Given a message body from c7n, return a list of splunk indices to send
        notifications to.

        :param msg: c7n notification message
        :type msg: dict
        :return: list of string Splunk index names
        :rtype: list
        """
        indices = set()
        if msg and msg.get("action", False) and msg["action"].get("to", False):
            for to in msg["action"].get("to", []):
                if not to.startswith("splunkhec://"):
                    continue
                parsed = urlparse(to)
                indices.add(parsed.netloc)
        return sorted(list(indices))
