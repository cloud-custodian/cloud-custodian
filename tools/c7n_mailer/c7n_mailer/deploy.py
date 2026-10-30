# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import copy
from functools import partial
import logging
import json
import os

from botocore.exceptions import ClientError
from c7n.mu import (
    CloudWatchEventSource,
    LambdaFunction,
    LambdaManager,
    PythonPackageArchive,
    SQSSubscription,
)

log = logging.getLogger("custodian-mailer")

entry_source = """\
import logging

from c7n_mailer import handle

logger = logging.getLogger('custodian.mailer')
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=log_format)
logging.getLogger('botocore').setLevel(logging.WARNING)

def dispatch(event, context):
    return handle.start_c7n_mailer(logger)

def sqs_dispatch(event, context):
    return handle.start_c7n_mailer_sqs(logger, event, context=context)
"""

CORE_DEPS = [
    # core deps
    "jinja2",
    "markupsafe",
    "yaml",
    "ldap3",
    "pyasn1",
    "redis",
    "jmespath",
    # transport datadog - recursive deps
    "datadog",
    "decorator",
    # requests (recursive deps), needed by datadog, slackclient, splunk
    "requests",
    "urllib3",
    "idna",
    "charset_normalizer",
    "certifi",
    # used by splunk mailer transport
    "jsonpointer",
    "jsonpatch",
    # sendgrid dependencies
    "sendgrid",
    "python_http_client",
    "ecdsa",
]


def get_archive(config):
    deps = ["c7n_mailer"] + list(CORE_DEPS)
    archive = PythonPackageArchive(modules=deps)

    for d in sorted(set(config.get("templates_folders", []))):
        if not os.path.exists(d):
            continue
        for t in sorted(f for f in os.listdir(d) if os.path.splitext(f)[1] == ".j2"):
            with open(os.path.join(d, t)) as fh:
                archive.add_contents("msg-templates/%s" % t, fh.read())

    function_config = copy.deepcopy(config)
    function_config["templates_folders"] = ["msg-templates/"]
    archive.add_contents("config.json", json.dumps(function_config))
    archive.add_contents("periodic.py", entry_source)

    archive.close()
    return archive


def get_queue_arn(config, session_factory):
    sqs = session_factory().client("sqs")
    return sqs.get_queue_attributes(QueueUrl=config["queue_url"], AttributeNames=["QueueArn"])[
        "Attributes"
    ]["QueueArn"]


def remove_queue_subscriptions(func, session_factory, should_remove):
    """Removes the SQS triggers of the mailer lambda whose queue arn matches should_remove"""
    client = session_factory().client("lambda")
    try:
        mappings = client.list_event_source_mappings(FunctionName=func.name)["EventSourceMappings"]
    except ClientError as e:
        log.warning("Could not check mailer lambda %s for SQS triggers: %s" % (func.name, e))
        return False
    arns = [
        m["EventSourceArn"]
        for m in mappings
        if m["EventSourceArn"].split(":")[2] == "sqs" and should_remove(m["EventSourceArn"])
    ]
    return bool(arns) and SQSSubscription(session_factory, arns).remove(func)


def is_mailer_queue(config, queue_arn):
    # queue_url ends with /<account>/<name>, the queue arn with :<account>:<name>
    return queue_arn.split(":")[4:] == config["queue_url"].rstrip("/").split("/")[-2:]


def provision(config, session_factory):
    schedule = CloudWatchEventSource(
        {"type": "periodic", "schedule": config.get("lambda_schedule", "rate(5 minutes)")},
        session_factory,
    )
    sqs_trigger = config.get("lambda_trigger", "schedule") == "sqs"
    if sqs_trigger:
        # Invoked by SQS as messages arrive, instead of polling the queue on a schedule.
        queue_arn = get_queue_arn(config, session_factory)
        subscription = SQSSubscription(
            session_factory,
            [queue_arn],
            batch_size=config.get("lambda_sqs_batch_size", 10),
            report_batch_item_failures=True,
        )
        events = [subscription]
    else:
        events = [schedule]

    func_config = dict(
        name=config.get("lambda_name", "cloud-custodian-mailer"),
        description=config.get("lambda_description", "Cloud Custodian Mailer"),
        tags=config.get("lambda_tags", {}),
        handler="periodic.sqs_dispatch" if sqs_trigger else "periodic.dispatch",
        runtime=config["runtime"],
        memory_size=config["memory"],
        timeout=config["timeout"],
        role=config["role"],
        subnets=config["subnets"],
        security_groups=config["security_groups"],
        dead_letter_config=config.get("dead_letter_config", {}),
        events=events,
    )

    archive = get_archive(config)
    func = LambdaFunction(func_config, archive)
    log.info("Provisioning mailer lambda %s" % (session_factory().region_name))
    manager = LambdaManager(session_factory)
    manager.publish(func)

    # Switching between the triggers leaves the other one from an earlier deployment,
    # which would keep invoking the mailer as well.
    if sqs_trigger:
        if schedule.remove(func, func_deleted=False):
            log.info("Removed the periodic schedule of mailer lambda %s" % func.name)
        # The mailer only reads queue_url: drop the triggers on queues it used before.
        if remove_queue_subscriptions(func, session_factory, lambda arn: arn != queue_arn):
            log.info("Removed the SQS triggers of earlier queues of mailer lambda %s" % func.name)
    elif remove_queue_subscriptions(func, session_factory, partial(is_mailer_queue, config)):
        log.info("Removed the SQS trigger of mailer lambda %s" % func.name)
