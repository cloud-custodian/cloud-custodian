# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import base64
import contextlib
from datetime import datetime
import json
import logging
import uuid
import os

from botocore.exceptions import ClientError
import boto3

from c7n import handler
from c7n.credentials import assumed_session
from c7n.log import CloudWatchLogHandler

log = logging.getLogger("c7n_awscc.hook")


def _get_boto_session(creds, region=None):
    return boto3.Session(
        aws_access_key_id=creds["accessKeyId"],
        aws_secret_access_key=creds["secretAccessKey"],
        aws_session_token=creds["sessionToken"],
        region=region,
    )


def get_event_credentials(request_data):
    if request_data.get("hookEncryptionKeyRole"):
        session = assumed_session(
            role_arn=request_data["hookEncryptionKeyRole"],
            session_name=str(uuid.uuid4()),
            region=os.environ.get("AWS_REGION"),
        )

        kms = session.client("kms")
        caller_creds = kms.decrypt(
            KeyId=request_data["hookEncryptionKeyArn"],
            CiphertextBlob=base64.b64decode(request_data.pop("callerCredentials")),
        )
        provider_creds = kms.decrypt(
            KeyId=request_data["hookEncryptionKeyArn"],
            CiphertextBlob=base64.b64decode(request_data.pop("providerCredentials")),
        )
    else:
        caller_creds = request_data.pop("callerCredentials")
        provider_creds = request_data.pop("providerCredentials")

    caller = _get_boto_session(json.loads(caller_creds))
    provider = _get_boto_session(json.loads(provider_creds))
    return caller, provider


@contextlib.contextmanager
def log_group(provider, event):
    group_name = event["requestData"]["providerLogGroupName"]

    stack_id = event.get("stackId")
    logical_id = event["requestData"].get("targetLogicalId")
    account_id = event["awsAccountId"]

    if stack_id and logical_id:
        stream_name = f"{stack_id}/{logical_id}"
    else:
        stream_name = f"{account_id}-{uuid.uuid4()}"

    try:
        handler = CloudWatchLogHandler(
            lambda: provider, log_group=group_name, log_stream=stream_name
        )
        logging.getLogger("custodian").addHandler(handler)
        logging.getLogger("c7n_awscc").addHandler(handler)
        yield handler
    except Exception:
        log.exception("Handler error", exc_info=True)
    finally:
        logging.getLogger("custodian").removeHandler(handler)
        logging.getLogger("c7n_awscc").removeHandler(handler)


class MetricOutput:

    namespace_root = "AWS/CloudFormation"

    def __init__(self, session, namespace, default_dims=None):
        self.client = session.client("cloudwatch")
        self.default_dims = default_dims or {}
        self.namespace = namespace
        self.start = None

    def get_value_params(self, value):
        params = {"Value": value}
        if isinstance(value, datetime):
            params["Unit"] = "Milliseconds"
        else:
            params["Unit"] = "Count"
        return params

    def get_metric_data(self, name, value, dims):
        metric = self.get_value_params(value)
        metric["MetricName"] = name
        metric["Timestamp"] = (str(datetime.utcnow()),)
        metric["Dimensions"] = self.get_dimensions(dims)
        return metric

    def get_dimensions(self, dims):
        dimensions = dict(self.default_dims)
        dimensions.update(dims)
        return dimensions

    def put(self, name, value, **dims):
        try:
            self.client.put_metric_data(
                Namespace=self.namespace,
                MetricData=[self.get_metric_data(name, value, dims)],
            )
        except ClientError:
            log.exception("An error occurred publishing metrics", exc_info=True)

    @classmethod
    def get(cls, provider, event):
        return cls(
            provider,
            "%s/%s/%s"
            % (
                cls.namespace_root,
                event["awsAccountId"],
                event["hookTypeName"].replace("::", "/"),
            ),
            {
                "DimensionKeyHookType": event["hookTypeName"],
                "DimensionKeyInvocationPointType": event["actionInvocationPoint"],
            },
        )

    def __enter__(self):
        self.start = datetime.utcnow()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.put("HandlerInvocationDuration", datetime.utcnow() - self.start)
        if exc_type:
            self.put("HandlerException", 1, DimensionKeyExceptionType=str(exc_value))


class ProgressOutput(dict):
    def set_progress(self, message, status):
        self["message"] = message
        self["status"] = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            self["status"] = "FAILED"
            self["errorCode"] = "InternalFailure"


def handle(event, context):
    caller, provider = get_event_credentials(event["requestData"])
    metrics = MetricOutput.get(provider, event)
    progress = ProgressOutput(message="")

    start = datetime.utcnow()
    with log_group(provider, event):
        log.info("processing %s", event)
        with metrics:
            metrics.put("HandlerInvocationCount", 1)
            with progress:
                handler.dispatch_event(
                    event, {"context": context, "progress": progress}
                )
            metrics.put("HandlerInvocationDuration", datetime.utcnow() - start)
    return json.dumps(dict(progress))
