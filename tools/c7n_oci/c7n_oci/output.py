import logging
import os

import oci
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
        if PROFILE in self.config.keys():
            session = SessionFactory(profile=self.config.profile)()
        else:
            session = ctx.session_factory()
        self.os_client = session.client("oci.object_storage.ObjectStorageClient")
        self.namespace = self.os_client.get_namespace().data
        self.create_bucket_if_does_not_exist()

    def upload_file(self, path, key):
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

    def create_bucket_if_does_not_exist(self):
        try:
            self.os_client.head_bucket(namespace_name=self.namespace, bucket_name=self.bucket)
        except ServiceError:
            self.log.warning(
                f"The bucket {self.bucket} does not exist. "
                f"Custodian will attempt to create a bucket in "
                f"the compartment {os.environ.get(OCI_LOG_COMPARTMENT_ID)}. "
                f"The compartment id is picked "
                f"using the environment variable {OCI_LOG_COMPARTMENT_ID} "
            )
            try:
                self.os_client.create_bucket(
                    namespace_name=self.namespace,
                    create_bucket_details=oci.object_storage.models.CreateBucketDetails(
                        name=self.bucket,
                        compartment_id=os.environ.get(OCI_LOG_COMPARTMENT_ID),
                        public_access_type="NoPublicAccess",
                    ),
                )
            except Exception as e:
                self.log.error(f"Unable to create a bucket with the name {self.bucket}. {e}")


@log_outputs.register("oci")
class OCILogOutput(LogOutput):
    log_format = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'

    def __init__(self, ctx, config=None):
        super(OCILogOutput, self).__init__(ctx, config)
        if 'netloc' in self.config.keys():
            self.log_group = self.config['netloc']
        else:
            self.log_group = 'DEFAULT'
        if PROFILE in self.config.keys():
            self.session_factory = SessionFactory(profile=self.config.profile)
        else:
            self.session_factory = SessionFactory()
        try:
            self.log_stream = ctx.policy.data['name']
        except Exception:
            self.log_stream = 'DEFAULT'

    def get_handler(self):
        return OCILogHandler(
            log_group=self.log_group,
            session_factory=self.session_factory,
            log_stream=self.log_stream,
        )
