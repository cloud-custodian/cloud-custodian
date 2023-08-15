import os
import unittest
from logging import LogRecord, DEBUG

import pytest
from mock import patch, Mock
from oci import Response
from oci.exceptions import ServiceError
from oci.logging.models import LogGroupSummary, LogSummary, WorkRequestResource, WorkRequest

from c7n.config import Bag, Config
from c7n.ctx import ExecutionContext
from c7n_oci.output import OCIObjectStorageOutput, OCILogOutput
from oci_common import OciBaseTest

HEADERS = {
    'etag': 'efaff65b-6d3e-4f49-bcf9-e3046d93e951',
    'last-modified': 'Thu, 13 Jul 2023 17:33:51 GMT',
    'opc-content-md5': 'QJEcFoq/iavVx3UNmpikMQ==',
    'version-id': 'ddba771f-4e9e-427f-aeb3-68455f83e9c8',
    'Content-Length': '0',
    'date': 'Thu, 13 Jul 2023 17:33:51 GMT',
    'opc-request-id': 'iad-1:cjkT_72uqSWzVLrhK_imu-uDbXtLfEzm5D',
    'x-api-id': 'native',
    'access-control-allow-origin': '*',
    'access-control-allow-methods': 'POST,PUT,GET,HEAD,DELETE,OPTIONS',
    'access-control-allow-credentials': 'true',
}


class OCIObjectStorageOutputTest(unittest.TestCase, OciBaseTest):
    @patch('c7n_oci.session.Session')
    @patch('c7n_oci.session.oci')
    def test_upload_file(self, oci_mock, session_mock):
        client = Mock()
        response = Response(status=200, headers=HEADERS, data=None, request=None)
        client.put_object.return_value = response
        oci_mock.identity.IdentityClient.return_value = Mock()
        session_mock.client.return_value = client
        output = self.get_oci_output()
        with open(os.path.join(output.root_dir, "foo.txt"), "w") as fh:
            fh.write("abc")
        output.upload()
        output.upload()

    @patch('c7n_oci.session.Session')
    @patch('c7n_oci.session.oci')
    @patch('c7n_oci.session.os')
    def test_upload_file_no_bucket(self, os_mock, oci_mock, session_mock):
        oci_mock.identity.IdentityClient.return_value = Mock()
        os_mock.environ.get.return_value = Mock()
        session_mock_return = Mock()
        client = Mock()
        response = Response(status=200, headers=HEADERS, data=None, request=None)
        client.put_object.return_value = response
        client.head_bucket = Mock(
            side_effect=ServiceError(status=404, code=None, headers=HEADERS, message="Test 404")
        )
        session_mock_return.client.return_value = client
        session_mock.return_value = session_mock_return
        output = self.get_oci_output_no_existing_bucket()
        with open(os.path.join(output.root_dir, "foo.txt"), "w") as fh:
            fh.write("abc")
        with pytest.raises(ValueError, match=r'The bucket [^\s]+ does not exist.'):
            output.upload()

    @patch('c7n_oci.session.Session')
    @patch('c7n_oci.session.oci')
    @patch('c7n_oci.session.os')
    def test_upload_file_no_bucket_other_err(self, os_mock, oci_mock, session_mock):
        oci_mock.identity.IdentityClient.return_value = Mock()
        os_mock.environ.get.return_value = Mock()
        session_mock_return = Mock()
        client = Mock()
        response = Response(status=200, headers=HEADERS, data=None, request=None)
        client.put_object.return_value = response
        client.head_bucket = Mock(
            side_effect=ServiceError(status=401, code=None, headers=HEADERS, message="Test 401")
        )
        session_mock_return.client.return_value = client
        session_mock.return_value = session_mock_return
        output = self.get_oci_output_no_existing_bucket()
        with open(os.path.join(output.root_dir, "foo.txt"), "w") as fh:
            fh.write("abc")
        with pytest.raises(ValueError, match=r'Unable to connect to the bucket [^\s]+'):
            output.upload()

    @patch('c7n_oci.log.oci')
    @patch('c7n_oci.session.Session')
    @patch('c7n_oci.session.oci')
    @patch('c7n_oci.session.os')
    @patch('c7n_oci.output.os')
    def test_log_output(self, os_log_mock, os_session_mock, oci_mock, session_mock, log_oci_mock):
        oci_mock.identity.IdentityClient.return_value = Mock()
        os_session_mock.environ.get.return_value = Mock()
        environ_mock = Mock()
        session_mock_return = Mock()
        composite_client = Mock()
        log_clients_mock = Mock()

        environ_mock.get.return_value = "custodian"
        os_log_mock.environ = environ_mock
        session_mock.return_value = session_mock_return
        resources_log_group = [WorkRequestResource(identifier="ocid1234")]
        data_log_group = WorkRequest(resources=resources_log_group)
        data_list_log_groups = []
        response_list_log_groups = Response(
            status=200, headers=HEADERS, data=data_list_log_groups, request=None
        )
        response_create_log_groups = Response(
            status=200, headers=HEADERS, data=data_log_group, request=None
        )
        composite_client.create_log_group_and_wait_for_state.return_value = (
            response_create_log_groups
        )
        composite_client.create_log_and_wait_for_state.return_value = response_create_log_groups
        log_oci_mock.logging.LoggingManagementClientCompositeOperations.return_value = (
            composite_client
        )
        data_list_logs = []
        response_list_logs = Response(
            status=200, headers=HEADERS, data=data_list_logs, request=None
        )
        log_clients_mock.list_log_groups.return_value = response_list_log_groups
        log_clients_mock.list_logs.return_value = response_list_logs
        session_mock_return.client.return_value = log_clients_mock
        log_output = self.get_oci_log_output()
        logging_handler = log_output.get_handler()
        logging_handler.emit(
            LogRecord(
                name="Custodian",
                msg="Test",
                args=None,
                level=DEBUG,
                pathname="/tmp",
                exc_info=None,
                lineno=0,
            )
        )
        logging_handler.flush()
        logging_handler.close()

    @patch('c7n_oci.session.Session')
    @patch('c7n_oci.session.oci')
    @patch('c7n_oci.session.os')
    @patch('c7n_oci.output.os')
    def test_log_output_already_existing_log(
        self, os_log_mock, os_session_mock, oci_mock, session_mock
    ):
        oci_mock.identity.IdentityClient.return_value = Mock()
        os_session_mock.environ.get.return_value = Mock()
        environ_mock = Mock()
        environ_mock.get.return_value = "custodian"
        os_log_mock.environ = environ_mock
        session_mock_return = Mock()
        session_mock.return_value = session_mock_return
        data_list_log_groups = [LogGroupSummary(id="ocid-1234", lifecycle_state='ACTIVE')]
        response_list_log_groups = Response(
            status=200, headers=HEADERS, data=data_list_log_groups, request=None
        )
        data_list_logs = [LogSummary(id="ocid-4568", lifecycle_state='ACTIVE')]
        response_list_logs = Response(
            status=200, headers=HEADERS, data=data_list_logs, request=None
        )
        log_clients_mock = Mock()
        log_clients_mock.list_log_groups.return_value = response_list_log_groups
        log_clients_mock.list_logs.return_value = response_list_logs
        log_clients_mock.create_log_group = Mock(
            side_effect=ServiceError(
                status=409, code='Conflict', headers=HEADERS, message="Test 409"
            )
        )
        log_clients_mock.create_log = Mock(
            side_effect=ServiceError(
                status=409, code='Conflict', headers=HEADERS, message="Test 409"
            )
        )
        session_mock_return.client.return_value = log_clients_mock
        log_output = self.get_oci_log_output()
        logging_handler = log_output.get_handler()
        logging_handler.emit(
            LogRecord(
                name="Custodian",
                msg="Test",
                args=None,
                level=DEBUG,
                pathname="/tmp",
                exc_info=None,
                lineno=0,
            )
        )
        logging_handler.emit(
            LogRecord(
                name="Custodian",
                msg="Test2",
                args=None,
                level=DEBUG,
                pathname="/tmp",
                exc_info=None,
                lineno=10,
            )
        )
        logging_handler.flush()
        logging_handler.close()

    @patch('c7n_oci.session.Session')
    @patch('c7n_oci.session.oci')
    @patch('c7n_oci.session.os')
    @patch('c7n_oci.output.os')
    def test_log_output_inactive_group(self, os_log_mock, os_session_mock, oci_mock, session_mock):
        oci_mock.identity.IdentityClient.return_value = Mock()
        os_session_mock.environ.get.return_value = Mock()
        environ_mock = Mock()
        environ_mock.get.return_value = "custodian"
        os_log_mock.environ = environ_mock
        session_mock_return = Mock()
        session_mock.return_value = session_mock_return
        data_list_log_groups = [LogGroupSummary(id="ocid-1234", lifecycle_state='INACTIVE')]
        response_list_log_groups = Response(
            status=200, headers=HEADERS, data=data_list_log_groups, request=None
        )
        data_list_logs = [LogSummary(id="ocid-4568", lifecycle_state='ACTIVE')]
        response_list_logs = Response(
            status=200, headers=HEADERS, data=data_list_logs, request=None
        )
        log_clients_mock = Mock()
        log_clients_mock.list_log_groups.return_value = response_list_log_groups
        log_clients_mock.list_logs.return_value = response_list_logs
        session_mock_return.client.return_value = log_clients_mock
        log_output = self.get_oci_log_output()
        with pytest.raises(ValueError, match=r'Log group [^\s]+ is not ACTIVE'):
            handler = log_output.get_handler()
            handler.emit(
                LogRecord(
                    name="Custodian",
                    msg="Test",
                    args=None,
                    level=DEBUG,
                    pathname="/tmp",
                    exc_info=None,
                    lineno=0,
                )
            )

    @patch('c7n_oci.session.Session')
    @patch('c7n_oci.session.oci')
    @patch('c7n_oci.session.os')
    @patch('c7n_oci.output.os')
    def test_log_output_inactive_log(self, os_log_mock, os_session_mock, oci_mock, session_mock):
        oci_mock.identity.IdentityClient.return_value = Mock()
        os_session_mock.environ.get.return_value = Mock()
        environ_mock = Mock()
        environ_mock.get.return_value = "custodian"
        os_log_mock.environ = environ_mock
        session_mock_return = Mock()
        session_mock.return_value = session_mock_return
        data_list_log_groups = [LogGroupSummary(id="ocid-1234", lifecycle_state='ACTIVE')]
        response_list_log_groups = Response(
            status=200, headers=HEADERS, data=data_list_log_groups, request=None
        )
        data_list_logs = [LogSummary(id="ocid-4568", lifecycle_state='INACTIVE')]
        response_list_logs = Response(
            status=200, headers=HEADERS, data=data_list_logs, request=None
        )
        log_clients_mock = Mock()
        log_clients_mock.list_log_groups.return_value = response_list_log_groups
        log_clients_mock.list_logs.return_value = response_list_logs
        session_mock_return.client.return_value = log_clients_mock
        log_output = self.get_oci_log_output()
        with pytest.raises(ValueError, match=r'Log stream [^\s]+ is not ACTIVE'):
            handler = log_output.get_handler()
            handler.emit(
                LogRecord(
                    name="Custodian",
                    msg="Test",
                    args=None,
                    level=DEBUG,
                    pathname="/tmp",
                    exc_info=None,
                    lineno=0,
                )
            )

    def get_oci_output(self):
        output_dir = "oci://TEST/custodian"
        output = OCIObjectStorageOutput(
            ExecutionContext(
                Mock(), Bag(name="xyz", provider_name='oci'), Config.empty(output_dir=output_dir)
            ),
            {'url': output_dir},
        )
        return output

    def get_oci_output_no_existing_bucket(self):
        output_dir = "oci://TEST/custodian"
        session_mock_return = Mock()
        client = Mock()
        response = Response(status=200, headers=HEADERS, data=None, request=None)
        client.put_object.return_value = response
        client.create_bucket.return_value = response
        session_mock_return.client.return_value = client
        session_factory = Mock()
        session_factory.return_value = session_mock_return
        output = OCIObjectStorageOutput(
            ExecutionContext(
                session_factory,
                Bag(name="xyz", provider_name='oci'),
                Config.empty(output_dir=output_dir),
            ),
            {'url': output_dir},
        )
        return output

    def get_oci_log_output(self):
        output_dir = "oci://TEST/custodian"
        return OCILogOutput(
            ExecutionContext(
                None, Bag(name="xyz", provider_name='oci'), Config.empty(output_dir=output_dir)
            )
        )
