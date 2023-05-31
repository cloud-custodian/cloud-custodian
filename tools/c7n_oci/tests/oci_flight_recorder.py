import functools
import os
import threading
from pathlib import Path
import re
import json
import gzip

import requests_stubs
from c7n_oci.session import Session
from vcr import config

from c7n.testing import C7N_FUNCTIONAL, CustodianTestCore
from c7n.utils import reset_session_cache
from oci_common import replace_ocid, replace_email

FILTERED_HEADERS = ['authorization',
                        'opc-request-id',
                        'opc-client-info',
                        'opc-request-id',
                        'x-content-sha256'
                        'accept-encoding',
                        'client-request-id',
                        'opc-client-retries'
                        'retry-after',
                        'strict-transport-security',
                        'opc-client-info'
                        'server',
                        'user-Agent',
                        'accept-language',
                        'connection',
                        'expires',
                        'content-location']

class OCIFlightRecorder(CustodianTestCore):
    cassette_dir = Path(__file__).parent.parent / 'tests' / 'cassettes'

    def cleanUp(self):
        threading.local().http = None
        return reset_session_cache()

    def record_flight_data(self, test_class, test_case):
        self.recording = True

        if not os.path.exists(self.cassette_dir):
            os.makedirs(self.cassette_dir)

        self.myvcr = config.VCR(custom_patches=self._get_mock_triples(), record_mode='all', before_record_request=self._request_callback,
            before_record_response=self._response_callback)
        self.myvcr.register_matcher('oci-matcher', self._oci_matcher)
        self.myvcr.match_on = ['oci-matcher', 'method']
        cassette = self._get_cassette_name(test_class, test_case)
        if os.path.exists(cassette):
            os.remove(cassette)
        cm = self.myvcr.use_cassette(cassette)
        cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        return functools.partial(Session)

    def replay_flight_data(self, test_class, test_case):
        self.myvcr = config.VCR(custom_patches=self._get_mock_triples(), record_mode='once', before_record_request=self._request_callback,
            before_record_response=self._response_callback)
        self.myvcr.register_matcher('oci-matcher', self._oci_matcher)
        self.myvcr.match_on = ['oci-matcher', 'method']
        cm = self.myvcr.use_cassette(self._get_cassette_name(test_class, test_case)
        , allow_playback_repeats=True
        )
        cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        return functools.partial(Session)

    def oci_session_factory(self, test_class, test_case):
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
        mock_triples = (
            (ocibase, "OCIConnectionPool", requests_stubs.VCROCIConnectionPool),
            (ocibase.OCIConnectionPool, "ConnectionCls", requests_stubs.VCROCIConnection)
        )
        return mock_triples
    
    def _request_callback(self, request):
        """Modify requests before saving"""
        request.uri = self._replace_ocid_in_uri(request.uri)
        if request.body:
            request.body = b'mock_body'

        request.headers = None
        return request

    def _replace_ocid_in_uri(self, uri):
        parts = uri.split('/')
        for index, part in enumerate(parts):
            if '?' in part:
                query_params = part.split('&')
                for i, param in enumerate(query_params):
                    query_params[i] = re.sub(r'\.oc1\..*$', '.oc1..<unique_ID>', param)
                parts[index] = "&".join(query_params)
            elif part.startswith('ocid1.'):
                parts[index] = re.sub(r'\.oc1\..*$', '.oc1..<unique_ID>', part)
        return "/".join(parts)
    
    def _response_callback(self, response):
        if not C7N_FUNCTIONAL:
            if 'data' in response['body']:
                body = json.dumps(response['body']['data'])
                if response['headers'].get('content-encoding', (None,))[0] == "gzip":
                    response['body']['string'] = gzip.compress(body.encode('utf-8'))
                    response['headers']['content-length'] = [str(len(response['body']['string']))]
                else:
                    response['body']['string'] = body.encode('utf-8')
                    response['headers']['content-length'] = [str(len(body))]

            return response

        response['headers'] = {k.lower(): v for (k, v) in
                               response['headers'].items()
                               if k.lower() not in FILTERED_HEADERS}

        content_type = response['headers'].get('content-type', (None,))[0]
        if not content_type or 'application/json' not in content_type:
            return response

        if response['headers'].get('content-encoding', (None,))[0] == "gzip":
            body = str(gzip.decompress(response['body'].pop('string')), 'utf-8')
        else:
            body = response['body'].pop('string').decode('utf-8')

        body = replace_ocid(body)
        body = replace_email(body)
        response['body']['data'] = json.loads(body)

        return response
    
    def _oci_matcher(self, r1, r2):
        r1_path = self._replace_ocid_in_uri(r1.path)
        r2_path = self._replace_ocid_in_uri(r2.path)
        return r1_path == r2_path
