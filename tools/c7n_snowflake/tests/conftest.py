# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import os
import threading
from pathlib import Path
from c7n.vendored.distutils.util import strtobool

import pytest
from vcr import config

from c7n.config import Config
from c7n.testing import PyTestUtils, reset_session_cache, C7N_FUNCTIONAL
from c7n.utils import reset_session_cache, JsonEncoder
from c7n_snowflake.provider import Snowflake
from c7n_snowflake.session import SessionFactory


# Monkey patch JsonEncoder to handle SessionFactory
_original_default = JsonEncoder.default

def _patched_default(self, obj):
    """Enhanced JsonEncoder that can serialize SessionFactory objects"""
    if isinstance(obj, SessionFactory):
        return {
            'type': 'SnowflakeSessionFactory',
            'account': os.environ.get("SNOWFLAKE_ACCOUNT", "<redacted>"),
            'user': os.environ.get("SNOWFLAKE_USER", "<redacted>"),
            'role': os.environ.get("SNOWFLAKE_ROLE", None)
        }
    return _original_default(self, obj)

JsonEncoder.default = _patched_default


class SnowflakeFlightRecorder:
    """VCR-based flight recorder for Snowflake API interactions"""
    
    cassette_dir = Path(__file__).parent / "cassettes"
    recording = False
    
    def cleanUp(self):
        """Clean up session cache and thread local storage"""
        threading.local().http = None
        return reset_session_cache()
    
    def record_flight_data(self, test_class, test_case):
        """Record HTTP interactions for the given test case"""
        self.recording = True
        
        if not os.path.exists(self.cassette_dir):
            os.makedirs(self.cassette_dir)
        
        self.myvcr = config.VCR(
            record_mode="all",
            before_record_request=self._request_callback,
            before_record_response=self._response_callback,
        )
        
        cassette_path = self._get_cassette_name(test_class, test_case)
        if os.path.exists(cassette_path):
            os.remove(cassette_path)
            
        cm = self.myvcr.use_cassette(cassette_path)
        cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        return SessionFactory()
    
    def replay_flight_data(self, test_class, test_case):
        """Replay recorded HTTP interactions for the given test case"""
        self.recording = False
        
        self.myvcr = config.VCR(
            record_mode="once",
            before_record_request=self._request_callback,
            before_record_response=self._response_callback,
        )
        
        cassette_path = self._get_cassette_name(test_class, test_case)
        cm = self.myvcr.use_cassette(cassette_path, allow_playback_repeats=True)
        cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        return SessionFactory()
    
    def snowflake_session_factory(self, test_class=None, test_case=None):
        """Get session factory for tests - record or replay based on environment"""
        if not test_class or not test_case:
            # Extract test class and case from stack frame if not provided
            import inspect
            frame = inspect.currentframe()
            try:
                # Look through the call stack to find the test method
                caller_frame = frame.f_back
                while caller_frame:
                    frame_locals = caller_frame.f_locals
                    if 'self' in frame_locals and hasattr(frame_locals['self'], '__class__'):
                        # Check if this looks like a test class (has test methods)
                        cls = frame_locals['self'].__class__
                        if any(method.startswith('test_') for method in dir(cls)):
                            test_class = cls.__name__
                            test_case = caller_frame.f_code.co_name
                            break
                    caller_frame = caller_frame.f_back
                
                # Fallback if we couldn't find test info
                if not test_class or not test_case:
                    test_class = 'UnknownTest'
                    test_case = 'unknown_method'
            finally:
                del frame
        
        if C7N_FUNCTIONAL or not self._cassette_file_exists(test_class, test_case):
            return self.record_flight_data(test_class, test_case)
        else:
            return self.replay_flight_data(test_class, test_case)
    
    def _cassette_file_exists(self, test_class, test_case):
        """Check if cassette file exists for the given test case"""
        return os.path.isfile(self._get_cassette_name(test_class, test_case))
    
    def _get_cassette_name(self, test_class, test_case):
        """Generate cassette filename for the given test case"""
        return f"{self.cassette_dir}/{test_class}.{test_case}.yml"
    
    def _request_callback(self, request):
        """Sanitize request before recording"""
        # Remove sensitive headers
        if request.headers:
            sensitive_headers = ['authorization', 'x-snowflake-authorization-token-type']
            for header in sensitive_headers:
                if header in request.headers:
                    request.headers[header] = ['REDACTED']
        
        # Sanitize request body if it contains credentials
        if request.body and hasattr(request.body, 'decode'):
            try:
                body_str = request.body.decode('utf-8') if isinstance(request.body, bytes) else str(request.body)
                # Basic sanitization for common credential patterns
                if 'password' in body_str.lower():
                    request.body = b'{"credentials":"REDACTED"}'
            except (UnicodeDecodeError, AttributeError):
                pass
        
        return request
    
    def _response_callback(self, response):
        """Sanitize response before recording"""
        # Filter sensitive headers from response
        if response.get('headers'):
            sensitive_headers = ['set-cookie', 'authorization']
            for header in sensitive_headers:
                if header in response['headers']:
                    response['headers'][header] = ['REDACTED']
        
        return response
    
    def addCleanup(self, func, *args, **kwargs):
        """Stub method for cleanup - pytest handles this"""
        pass


class CustodianSnowflakeTesting(PyTestUtils, SnowflakeFlightRecorder):
    """Pytest Snowflake Testing Fixture combining utilities and flight recorder"""
    pass


@pytest.fixture(scope='function')
def test(request):
    """Main test fixture providing testing utilities and VCR recording"""
    test_utils = CustodianSnowflakeTesting(request)
    test_utils.addCleanup(reset_session_cache)
    return test_utils


@pytest.fixture(scope='function', autouse=True) 
def setup(request):
    """Setup fixture that initializes the Snowflake provider"""
    try:
        snowflake_provider = Snowflake()
        snowflake_provider.initialize(Config.empty())
        yield
    finally:
        reset_session_cache()


@pytest.fixture
def snowflake_session():
    """Fixture providing a Snowflake session factory for tests"""
    return SessionFactory()



