# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import unittest
from sys import stderr

from botocore.history import get_global_history_recorder


class ApiCallCaptor:
    """
    Boto3 api call monitor accessory to allow making assertions about the precise
    boto calls that CloudCustodian is making.
    This utility works by installing a hook into boto that records all the calls
    made includinfg params. This allows us to make assertions about those calls.

    Usage:
    For throrough usage examples see test_appmesh.py.

    But in short...
    1) Use 'captor = ApiCallCaptor.start_capture()' before running the policy..
    2) then 'captor.calls' provides access the calls made, eg

        self.assertEqual(
            [
                {'operation': 'DescribeVirtualGateway',
                 'params': {'meshName': 'm1', 'virtualGatewayName': 'g1'},
                 'service': 'appmesh'},
                {'operation': 'GetResources',
                 'params': {'ResourceARNList': [
                     'arn:aws:appmesh:eu-west-2:123456789012:mesh/m1/virtualGateway/g1']},
                 'service': 'resourcegroupstaggingapi'}
            ],
            captor.calls
        )

    or if you want an immediate notification where a bad call is made then
    you can set an expection before running the policy.

            capture.expect(
            [
                {'operation': 'DescribeVirtualGateway',
                 'params': {'meshName': 'm1', 'virtualGatewayName': 'g1'},
                 'service': 'appmesh'},
                {'operation': 'GetResources',
                 'params': {'ResourceARNList': [
                     'arn:aws:appmesh:eu-west-2:123456789012:mesh/m1/virtualGateway/g1']},
                 'service': 'resourcegroupstaggingapi'}
            ],)

    See the documentation on the 'expect(..)' method for more info.

    Background:
    Unfortunately the placebo library that cloud custodian uses for recording
    and replayback of api calls has no ability to assert the parameters that
    are actually being sent to boto3 nor the order of the boto calls.
    Placebo just plays back files according to the api and operation and
    does a round-robin on the playback files if more calls are made than there
    are files.

    I prefer to make strong assertions in my tests and it seems a critial
    weakness that we can't make assertion in placebo about the api calls,
    without that we have little idea whether the extension works at all really.
    There has been discussions in the placebo forum about this, but no solutions.
    """

    _INSTANCE = None

    def __init__(self):
        # calls is an array of call objects - see the expect() doco for more info.
        self.calls = []
        # inspect this after the policy exec to see if the 'expect(...)' was not met

        self.first_error = None

        self.calls_made = 0

        # expected_calls is an array of call objects - see the expect() doco for more info
        self.expected_calls = None
        self.on_error = None

    def emit(self, _event_type, payload, _source):
        """
        callback that will be installed into boto.
        the name of this method is dictated by boto.

        :param _event_type - the type of the event eg "'API_CALL"
        :param payload - an object capturing the call
        eg {'operation': 'ListMeshes', 'params': {}, 'service': 'appmesh'}
        :param _source - where the call came from eg "BOTOCORE"
        """
        # print("API CALL : " + str(event_type) + " P:" + str(payload) + " S:" + str(source))
        self.calls.append(payload)

        # if an expectation was made then check immediately
        if self.expected_calls:
            configured_calls = len(self.expected_calls)
            if self.calls_made == configured_calls:
                msg = (
                        "ERROR: too many boto calls made: expected %d, but got %d ...\nunexpected: %s\n" #noqa
                        % (
                            len(self.expected_calls),
                            self.calls_made + 1,
                            str(payload),
                        )
                )
                if not self.first_error:
                    self.first_error = msg
                if self.on_error:
                    self.on_error(payload, msg)

            expected_call = self.expected_calls[self.calls_made]
            if payload != expected_call:
                msg = (
                        "ERROR: incorrect boto call made at call #%d ...\nexpected: %s\n but got: %s\n" #noqa
                        % (
                            self.calls_made + 1,
                            str(expected_call),
                            str(payload),
                        )
                )
                if not self.first_error:
                    self.first_error = msg
                if self.on_error:
                    self.on_error(payload, msg)

        self.calls_made += 1

    def _default_on_err(payload, err):
        stderr.write(err)

    def expect(self, calls, on_error=_default_on_err):
        """
        :param calls: is a list of object like that describe the API calls
        :param on_error: is a callback with the form  "(dict, str) -> void"

        use expect(...) if you want immediate notification when an unexpected call is made, for
        example to set a breakpoint and do debugging.

        calls: is a list of object like that describe the API calls,
        eg :  {'service': 'appmesh', 'operation': 'DescribeMesh', 'params': {'meshName': 'm1'}}

        on_error: is a callback with the form  "(dict, str) -> void"
        where the dict is the call made
        eg {'service': 'appmesh', 'operation': 'DescribeMesh', 'params': {'meshName': 'm1'}}
        and the string is an error message.
        The default impl will print the error message, but you can override this
        for instance to place a breakpoint in your own code if an error occurs
        or to change the action or pass None to disable.
        Because boto swallows any exceptions then throwing an exception is
        ineffectural, however it's still possible to exit the process if you want
        a really aggressive hook.
        """
        self.expected_calls = calls
        self.on_error = on_error

    def assertExpected(self):
        if self.expected_calls != self.calls:
            tc = unittest.TestCase()
            tc.assertEquals(self.expected_calls, self.calls, "bad boto call")

    @classmethod
    def start_capture(cls):
        """
        install a hook in boto to record all api interactions.
        API calls are collected into
        further calls to this method merely reset the 'calls' collection.
        """
        hist = get_global_history_recorder()

        if not cls._INSTANCE:
            cls._INSTANCE = ApiCallCaptor()
            hist.add_handler(ApiCallCaptor._INSTANCE)

        cls._INSTANCE.calls = []
        cls._INSTANCE.expected_calls = None
        cls._INSTANCE.calls_made = 0

        hist.enable()

        return cls._INSTANCE
