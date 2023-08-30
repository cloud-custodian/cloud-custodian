import logging
import uuid
from datetime import datetime

import oci
from oci.exceptions import ServiceError

from c7n_oci.utils import spec_version

log = logging.getLogger("custodian.oci.log")


class OCILogHandler(logging.Handler):
    def __init__(
        self, log_group=__name__, log_stream=None, session_factory=None, log_compartment_id=None
    ):
        super(OCILogHandler, self).__init__()
        self.log_group = log_group
        self.log_stream = log_stream
        self.session_factory = session_factory
        self.transport = None
        self.log_compartment_id = log_compartment_id
        self.session = session_factory()
        self.logging_client = None
        self.loggingingestion_client = None
        self.log_group_id = None
        self.log_stream_id = None

    def init_oci_logging(self):
        try:
            self.logging_client = self.session.client("oci.logging.LoggingManagementClient")
            self.loggingingestion_client = self.session.client("oci.loggingingestion.LoggingClient")

            log_groups = self.logging_client.list_log_groups(
                compartment_id=self.log_compartment_id, display_name=self.log_group
            ).data

            if not log_groups:
                self.log_group_id = self.create_log_group()
            elif log_groups and log_groups[0].lifecycle_state != 'ACTIVE':
                raise ValueError(f"Log group {log_groups[0].display_name} is not ACTIVE")
            else:
                self.log_group_id = log_groups[0].id

            list_logs_response = self.logging_client.list_logs(
                log_group_id=self.log_group_id, display_name=self.log_stream
            )
            if not list_logs_response.data:
                self.log_stream_id = self.create_log()
            elif list_logs_response.data and list_logs_response.data[0].lifecycle_state != 'ACTIVE':
                raise ValueError(
                    f"Log stream {list_logs_response.data[0].display_name} is not ACTIVE"
                )
            else:
                self.log_stream_id = list_logs_response.data[0].id

        except ServiceError as se:
            log.debug(f"{se}")
            raise ValueError(f"Unable to instantiate OCI logging handler: {se.message}")
        except ValueError as ve:
            raise ve
        except Exception as e:
            log.debug(f"{e}")
            raise ValueError(
                "Unable to instantiate OCI logging handler. Please check the logs for error"
            )

    def create_log_group(self):
        composite_client = oci.logging.LoggingManagementClientCompositeOperations(
            self.logging_client
        )
        response = composite_client.create_log_group_and_wait_for_state(
            create_log_group_details=oci.logging.models.CreateLogGroupDetails(
                compartment_id=self.log_compartment_id,
                display_name=self.log_group,
                description="Cloud Custodian Logs",
            ),
            wait_for_states=['SUCCEEDED'],
        )
        return response.data.resources[0].identifier

    def create_log(self):
        composite_client = oci.logging.LoggingManagementClientCompositeOperations(
            self.logging_client
        )
        response = composite_client.create_log_and_wait_for_state(
            log_group_id=self.log_group_id,
            create_log_details=oci.logging.models.CreateLogDetails(
                display_name=self.log_stream,
                is_enabled=True,
                log_type="CUSTOM",
            ),
            wait_for_states=['SUCCEEDED'],
        )
        return response.data.resources[0].identifier

    def emit(self, message):
        if self.log_stream_id:
            msg = self.format_message(message)
            tz = datetime.now().astimezone().tzinfo
            try:
                self.loggingingestion_client.put_logs(
                    log_id=self.log_stream_id,
                    put_logs_details=oci.loggingingestion.models.PutLogsDetails(
                        specversion=spec_version(),
                        log_entry_batches=[
                            oci.loggingingestion.models.LogEntryBatch(
                                entries=[
                                    oci.loggingingestion.models.LogEntry(
                                        data=msg["message"],
                                        id=str(uuid.uuid4()),
                                        time=datetime.fromtimestamp(msg["timestamp"], tz=tz),
                                    )
                                ],
                                source="Cloud-Custodian",
                                type=message.levelname,
                            )
                        ],
                    ),
                )
            except Exception as e:
                log.exception(e, stack_info=True)
        else:
            self.init_oci_logging()

    def flush(self):
        pass

    def close(self):
        pass

    def format_message(self, msg):
        """format message."""
        return {
            'timestamp': int(msg.created),
            'message': self.format(msg),
            'stream': self.log_stream or msg.name,
            'group': self.log_group,
        }
