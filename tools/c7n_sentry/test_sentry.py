# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import unittest
import time

from c7n_sentry import c7nsentry


class SentrySenderTests(unittest.TestCase):

    def test_parse_traceback(self):
        emsg, error = c7nsentry.parse_traceback(msg)
        self.assertIn("custodian.output - Error while executing", emsg)
        self.assertEqual(msg.count('File'), len(error['stacktrace']['frames']))

    def test_get_sentry_message(self):
        config = dict(
            project='custodian',
            account_name='c7n-test',
            account_id='9111411911411',
        )
        sentry_msg = c7nsentry.get_sentry_message(
            config, {'logGroup': '/cloud-custodian/',
                     'logStream': 'night-policy', 'logEvents': [{
                         'message': msg, 'timestamp': time.time() * 1000}]})
        self.assertEqual(sentry_msg['user'], {
            'id': config['account_id'], 'username': config['account_name']})

    def test_preserve_full_message(self):
        _, error = c7nsentry.parse_traceback(msg2)
        self.assertIn(
            "FinalDBSnapshotIdentifier is not a valid identifier",
            error['value'])


msg = """2016-07-07 19:14:24,160 - ERROR - custodian.output - Error while executing policy\nTraceback (most recent call last):\n  File \"/usr/local/custodian/lib/python2.7/site-packages/c7n/policy.py\", line 191, in poll\n    resources = self.resource_manager.resources()\n  File \"/usr/local/custodian/lib/python2.7/site-packages/c7n/query.py\", line 141, in resources\n    resources = self.augment(resources)\n  File \"/usr/local/custodian/lib/python2.7/site-packages/c7n/resources/s3.py\", line 95, in augment\n    results = filter(None, results)\n  File \"/usr/local/custodian/lib/python2.7/site-packages/concurrent/futures/_base.py\", line 581, in result_iterator\n    yield future.result()\n  File \"/usr/local/custodian/lib/python2.7/site-packages/concurrent/futures/_base.py\", line 405, in result\n    return self.__get_result()\n  File \"/usr/local/custodian/lib/python2.7/site-packages/concurrent/futures/thread.py\", line 55, in run\n    result = self.fn(*self.args, **self.kwargs)\n  File \"/usr/local/custodian/lib/python2.7/site-packages/c7n/resources/s3.py\", line 126, in assemble_bucket\n    v = method(Bucket=b['Name'])\n  File \"/usr/local/custodian/lib/python2.7/site-packages/botocore/client.py\", line 258, in _api_call\n    return self._make_api_call(operation_name, kwargs)\n  File \"/usr/local/custodian/lib/python2.7/site-packages/botocore/client.py\", line 537, in _make_api_call\n    operation_model, request_dict)\n  File \"/usr/local/custodian/lib/python2.7/site-packages/botocore/endpoint.py\", line 117, in make_request\n    return self._send_request(request_dict, operation_model)\n  File \"/usr/local/custodian/lib/python2.7/site-packages/botocore/endpoint.py\", line 146, in _send_request\n    success_response, exception):\n  File \"/usr/local/custodian/lib/python2.7/site-packages/botocore/endpoint.py\", line 219, in _needs_retry\n    caught_exception=caught_exception)\n  File \"/usr/local/custodian/lib/python2.7/site-packages/botocore/hooks.py\", line 227, in emit\n    return self._emit(event_name, kwargs)\n  File \"/usr/local/custodian/lib/python2.7/site-packages/botocore/hooks.py\", line 210, in _emit\n    response = handler(**kwargs)\n  File \"/usr/local/custodian/lib/python2.7/site-packages/botocore/retryhandler.py\", line 183, in __call__\n    if self._checker(attempts, response, caught_exception):\n  File \"/usr/local/custodian/lib/python2.7/site-packages/botocore/retryhandler.py\", line 251, in __call__\n    caught_exception)\n  File \"/usr/local/custodian/lib/python2.7/site-packages/botocore/retryhandler.py\", line 274, in _should_retry\n    return self._checker(attempt_number, response, caught_exception)\n  File \"/usr/local/custodian/lib/python2.7/site-packages/botocore/retryhandler.py\", line 314, in __call__\n    caught_exception)\n  File \"/usr/local/custodian/lib/python2.7/site-packages/botocore/retryhandler.py\", line 223, in __call__\n    attempt_number, caught_exception)\n  File \"/usr/local/custodian/lib/python2.7/site-packages/botocore/retryhandler.py\", line 356, in _check_caught_exception\n    raise caught_exception\nSSLError: EOF occurred in violation of protocol (_ssl.c:765)""" # NOQA


msg2 = """
2016-08-09 19:16:28,943 - ERROR - custodian.output - Error while executing policy Traceback (most recent call last):\n  File "/usr/local/custodian/lib/python2.7/site-packages/c7n/policy.py", line 234, in poll\n results = a.process(resources)\n File "/usr/local/custodian/lib/python2.7/site-packages/c7n/resources/rds.py", line 291, in process\n client.delete_db_instance(**params)\n  File "/usr/local/custodian/lib/python2.7/site-packages/botocore/client.py", line 278, in _api_call\n return self._make_api_call(operation_name, kwargs)\n File "/usr/local/custodian/lib/python2.7/site-packages/botocore/client.py", line 572, in _make_api_call\n raise ClientError(parsed_response, operation_name)\n ClientError: An error occurred (InvalidParameterValue) when calling the DeleteDBInstance operation: The parameter FinalDBSnapshotIdentifier is not a valid identifier. Identifiers must begin with a letter; must contain only ASCII letters, digits, and hyphens; and must not end with a hyphen or contain two consecutive hyphens.""" # NOQA

if __name__ == '__main__':
    unittest.main()
