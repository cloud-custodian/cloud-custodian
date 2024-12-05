# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import gzip
import inspect
import json
import os
import re
import threading
from pathlib import Path

from vcr import config

import requests_stubs
from c7n.testing import C7N_FUNCTIONAL, CustodianTestCore
from c7n.utils import reset_session_cache
from c7n_oci.session import SessionFactory
from oci_common import (
    replace_ocid,
    replace_email,
    replace_namespace,
    sanitize_response_body,
)

FILTERED_HEADERS = [
    "authorization",
    "opc-request-id",
    "opc-client-info",
    "opc-request-id",
    "x-content-sha256accept-encoding",
    "client-request-id",
    "opc-client-retriesretry-after",
    "strict-transport-security",
    "opc-client-infoserver",
    "user-Agent",
    "accept-language",
    "connection",
    "expires",
    "content-location",
    "access-control-allow-credentials",
    "access-control-allow-methods",
    "access-control-allow-origin",
    "access-control-expose-headers",
    "content-length",
    "date",
    "x-api-id",
    "etag",
    "pragma",
    "x-content-type-options",
]


class OCIFlightRecorder(CustodianTestCore):
    cassette_dir = Path(__file__).parent.parent / "tests" / "cassettes"
    cassette_name = None
    cassette = None
    multi_requests_map = {}
    multi_requests_history = {}
    running_req_count = {}
    recording = False

    def cleanUp(self):
        threading.local().http = None
        return reset_session_cache()

    def record_flight_data(self, test_class, test_case):
        self.recording = True

        if not os.path.exists(self.cassette_dir):
            os.makedirs(self.cassette_dir)

        self.myvcr = config.VCR(
            custom_patches=self._get_mock_triples(),
            record_mode="all",
            before_record_request=self._request_callback,
            before_record_response=self._response_callback,
        )
        self.myvcr.register_matcher("oci-matcher", self._oci_matcher)
        self.myvcr.match_on = ["oci-matcher", "method"]
        cassette = self._get_cassette_name(test_class, test_case)
        if os.path.exists(cassette):
            os.remove(cassette)
        cm = self.myvcr.use_cassette(cassette)
        cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        return SessionFactory()

    def replay_flight_data(self, test_class, test_case):
        self.myvcr = config.VCR(
            custom_patches=self._get_mock_triples(),
            record_mode="once",
            before_record_request=self._request_callback,
            before_record_response=self._response_callback,
        )
        self.myvcr.register_matcher("oci-matcher", self._oci_matcher)
        self.myvcr.match_on = ["oci-matcher", "method"]
        cm = self.myvcr.use_cassette(
            self._get_cassette_name(test_class, test_case), allow_playback_repeats=True
        )
        self.cassette = None
        self.cassette_name = self._get_cassette_name(test_class, test_case)
        cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        return SessionFactory()

    def _extract_caller(self):
        caller = inspect.currentframe().f_back.f_back
        return (caller.f_locals["self"].__class__.__name__, caller.f_code.co_name)

    def oci_session_factory(self, test_class=None, test_case=None):
        if not test_class or not test_case:
            test_class, test_case = self._extract_caller()
        if not C7N_FUNCTIONAL and self._cassette_file_exists(test_class, test_case):
            return self.replay_flight_data(test_class, test_case)
        else:
            return self.record_flight_data(test_class, test_case)

    def _cassette_file_exists(self, test_class, test_case):
        return os.path.isfile(self._get_cassette_name(test_class, test_case))

    def addCleanup(self, func, *args, **kw):
        pass

    def _get_cassette_name(self, test_class, test_case):
        return f"{self.cassette_dir}/{test_class}.{test_case}.yml"

    def _get_mock_triples(self):
        import oci.base_client as ocibase
        import oci._vendor.urllib3.connectionpool as conn

        mock_triples = (
            (ocibase, "OCIConnectionPool", requests_stubs.VCROCIConnectionPool),
            (
                ocibase.OCIConnectionPool,
                "ConnectionCls",
                requests_stubs.VCROCIConnection,
            ),
            (conn.HTTPConnectionPool, "ConnectionCls", requests_stubs.VCRHTTPConnection),
            (conn.HTTPSConnectionPool, "ConnectionCls", requests_stubs.VCRHTTPSConnection),
        )
        return mock_triples

    def _request_callback(self, request):
        """Modify requests before saving"""
        request.uri = self._replace_ocid_in_uri(request.uri)
        request.uri = self._replace_namespace_in_uri(request.uri)
        if request.body:
            request.body = b"mock_body"

        request.headers = None
        return request

    def _replace_ocid_in_uri(self, uri):
        parts = uri.split("/")
        for index, part in enumerate(parts):
            if "?" in part:
                query_params = part.split("&")
                for i, param in enumerate(query_params):
                    query_params[i] = re.sub(r"\.oc1\..*$", ".oc1..<unique_ID>", param)
                parts[index] = "&".join(query_params)
            elif part.startswith("ocid1."):
                parts[index] = re.sub(r"\.oc1\..*$", ".oc1..<unique_ID>", part)
        return "/".join(parts)

    def _replace_namespace_in_uri(self, uri):
        return re.sub(r"/n/[^/]*/", r"/n/<namepsace>/", uri)

    def _response_callback(self, response):
        if not C7N_FUNCTIONAL:
            if "data" in response["body"]:
                body = json.dumps(response["body"]["data"])
                if response["headers"].get("content-encoding", (None,))[0] == "gzip":
                    response["body"]["string"] = gzip.compress(body.encode("utf-8"))
                    response["headers"]["content-length"] = [str(len(response["body"]["string"]))]
                else:
                    response["body"]["string"] = body.encode("utf-8")
                    response["headers"]["content-length"] = [str(len(body))]

            return response

        response["headers"] = {
            k.lower(): v
            for (k, v) in response["headers"].items()
            if k.lower() not in FILTERED_HEADERS
        }

        content_type = response["headers"].get("content-type", (None,))[0]
        if not content_type or "application/json" not in content_type:
            return response

        if response["headers"].get("content-encoding", (None,))[0] == "gzip":
            body = str(gzip.decompress(response["body"].pop("string")), "utf-8")
        else:
            body = response["body"].pop("string").decode("utf-8")

        body = replace_ocid(body)
        body = replace_email(body)
        body = replace_namespace(body)
        json_data = json.loads(body)
        sanitize_response_body(json_data)
        response["body"]["data"] = json_data
        return response

    def _populate_request_uris(self):
        multi_requests_map = {}
        tmp_requests_map = {}
        for t in self.cassette.data:
            (r, _) = t
            k = f"{r.method}_{r.uri}"
            tmp_requests_map[k] = tmp_requests_map.get(k, 0) + 1
        for k, v in tmp_requests_map.items():
            if v > 1:
                multi_requests_map[k] = v
        self.multi_requests_map = multi_requests_map

    def _check_repeated_requests(self, req):
        """
        This method is to handle the case where the same request may be recorded in the cassette multiple times.
        For e.g. request to get a zone, once recorded as part of filter and another time when being fetched after policy execution to validate
        The first request will contain the resource as is whereas the second call will return updated resource with tags etc.
        The multi_requests_map is populated at the start of the test with the loaded cassette, only containing requests that occur more than once
        The multi_requests_history tracks how many times a repeated request has been fetched from the cassette
        When a repeated request is fetched for the first time in the execution of a test it is initialized to 1 and True is returned
        When the repeated request is queried again and the multi_requests_history already has a record of that request, running_req_count is initialized to 1
        The running_req_count is incremented on each call until it passes the multi_requests_history in value, indicating that the required records have been skipped
        """  # noqa
        if req in self.multi_requests_map:
            if self.multi_requests_history.get(req, 0) > 0:
                self.running_req_count[req] = self.running_req_count.get(req, 0) + 1
                if self.running_req_count.get(req) > self.multi_requests_history.get(req):
                    self.running_req_count = {}
                    self.multi_requests_history[req] = self.multi_requests_history.get(req) + 1
                    if self.multi_requests_history.get(req) == self.multi_requests_map.get(req, 0):
                        self.multi_requests_history[req] = 0
                    return True
                else:
                    return False
            else:
                self.multi_requests_history[req] = 1
        return True

    def _oci_matcher(self, r1, r2):
        if not C7N_FUNCTIONAL:
            if self.cassette is None:
                with self.myvcr.use_cassette(path=self.cassette_name) as cassette:
                    self.cassette = cassette
                    self._populate_request_uris()
        r1_path = self._replace_ocid_in_uri(r1.path)
        r2_path = self._replace_ocid_in_uri(r2.path)
        if r1_path == r2_path:
            abt_to_return = self._check_repeated_requests(f"{r1.method}_{r1.uri}")
            return abt_to_return
        return False
