import logging
import os

from oci.exceptions import ServiceError

from c7n.output import blob_outputs, BlobOutput, log_outputs, LogOutput
from c7n_oci.constants import PROFILE, OCI_LOG_COMPARTMENT_ID
from c7n_oci.log import OCILogHandler
from c7n_oci.session import SessionFactory


@blob_outputs.register("oci")
class OCIObjectStorageOutput(BlobOutput):
    log = logging.getLogger('custodian.oci.output.OCIObjectStorageOutput')

    def __init__(self, ctx, config):
        super(OCIObjectStorageOutput, self).__init__(ctx, config)
        self.session = SessionFactory(profile=self.config.get(PROFILE))()
        self.os_client = None
        self.namespace = None
        self.bucket_exist = False

    def upload_file(self, path, key):
        if self.bucket_exist:
            with open(path, 'rb') as f:
                response = self.os_client.put_object(
                    namespace_name=self.namespace,
                    bucket_name=self.bucket,
                    object_name=key,
                    put_object_body=f,
                )
                self.log.debug(
                    f"Response status for sending {path} with the name {key} "
                    f"to object storage is {response.status}"
                )
        else:
            self.os_client = self.session.client("oci.object_storage.ObjectStorageClient")
            self.namespace = self.os_client.get_namespace().data
            try:
                self.os_client.head_bucket(namespace_name=self.namespace, bucket_name=self.bucket)
            except ServiceError as se:
                if se.status == 404:
                    self.log.error(f"The bucket {self.bucket} does not exist.")
                    raise ValueError(f"The bucket {self.bucket} does not exist.")
                else:
                    self.log.error(f"Unable to connect to the bucket {self.bucket} : {se.message}")
                    raise ValueError(
                        f"Unable to connect to the bucket {self.bucket} : {se.message}"
                    )
            self.bucket_exist = True


@log_outputs.register("oci")
class OCILogOutput(LogOutput):
    log_format = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'

    def __init__(self, ctx, config=None):
        super(OCILogOutput, self).__init__(ctx, config)
        if 'netloc' in self.config.keys():
            self.log_group = self.config['netloc']
        else:
            self.log_group = 'DEFAULT'
        self.session_factory = SessionFactory(profile=self.config.get(PROFILE))
        try:
            self.log_stream = ctx.policy.data['name']
        except Exception:
            self.log_stream = 'DEFAULT'

    def get_handler(self):
        if self.config.get(OCI_LOG_COMPARTMENT_ID):
            log_compartment_id = self.config.get(OCI_LOG_COMPARTMENT_ID)
        else:
            log_compartment_id = os.environ.get(OCI_LOG_COMPARTMENT_ID)
        if not log_compartment_id:
            raise ValueError(
                f"{OCI_LOG_COMPARTMENT_ID} must be provided as a query param or "
                f"environment variable in order to use the OCI Logging services."
            )
        return OCILogHandler(
            log_group=self.log_group,
            session_factory=self.session_factory,
            log_stream=self.log_stream,
            log_compartment_id=log_compartment_id,
        )
