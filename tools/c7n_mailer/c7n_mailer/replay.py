# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
Allow local testing of mailer and templates by replaying an SQS message.

MAILER_FILE input is a file containing the exact base64-encoded, gzipped
data that's enqueued to SQS via :py:meth:`c7n.actions.Notify.send_sqs`.

Alternatively, with -p|--plain specified, the file will be assumed to be
JSON data that can be loaded directly.
"""
import argparse
import base64
import json
import logging
import os
import zlib
import yaml
import uuid
from datetime import datetime

import boto3
import jsonschema
from c7n_mailer.cli import CONFIG_SCHEMA
from c7n_mailer.email_delivery import EmailDelivery
from c7n_mailer.slack_delivery import SlackDelivery
from c7n_mailer.utils import setup_defaults
from c7n_mailer.utils_email import get_mimetext_message

logger = logging.getLogger(__name__)


class MailerTester:
    def __init__(self, config, raw=None, msg_file=None, msg_plain=False, json_dump_file=None):
        if msg_file:
            if not os.path.exists(msg_file):
                raise RuntimeError("File does not exist: %s" % msg_file)
            logger.debug("Reading message from: %s", msg_file)
            with open(msg_file, "r") as fh:
                raw = fh.read()
            logger.debug("Read %d byte message", len(raw))
            if msg_plain:
                raw = raw.strip()
            else:
                logger.debug("base64-decoding and zlib decompressing message")
                raw = zlib.decompress(base64.b64decode(raw))
                if json_dump_file is not None:
                    with open(json_dump_file, "wb") as fh:  # pragma: no cover
                        fh.write(raw)
            self.data = json.loads(raw)
        else:
            self.data = raw
        logger.debug("Loaded message JSON")
        self.config = config
        self.session = boto3.Session()

    def run(self, dry_run=False, print_only=False):
        is_slack = self.data["action"].get("slack_template") is not None
        if is_slack:
            sd = SlackDelivery(self.config, self.session, logger)
            addrs_to_msgs = sd.get_to_addrs_slack_messages_map(self.data)
            logger.info("Would send to: %s", addrs_to_msgs.keys())

            if print_only:
                print(list(addrs_to_msgs.values())[0])
                return
            if dry_run:
                for to_addrs, body in addrs_to_msgs.items():
                    print("-> SEND MESSAGE TO: %s" % to_addrs)
                    print(body)
                return
            for to_addrs, body in addrs_to_msgs.items():
                logger.info("Actually sending to: %s", to_addrs)
                sd.send_slack_msg(to_addrs, body)
        else:
            emd = EmailDelivery(self.config, self.session, logger)
            addrs_to_msgs = emd.get_emails_to_mimetext_map(self.data)
            logger.info("Would send to: %s", addrs_to_msgs.keys())

            if print_only:
                mime = get_mimetext_message(
                    self.config, logger, self.data, self.data["resources"], ["foo@example.com"]
                )
                logger.info('Send mail with subject: "%s"', mime["Subject"])
                print(mime.get_payload(None, True).decode("utf-8"))
                return
            if dry_run:
                for to_addrs, mimetext_msg in addrs_to_msgs.items():
                    print("-> SEND MESSAGE TO: %s" % "; ".join(to_addrs))
                    print(mimetext_msg.get_payload(None, True).decode("utf-8"))
                return
            # else actually send the message...
            logger.info("Actually sending to: %s", addrs_to_msgs.keys())
            emd.send_c7n_email(self.data)


def setup_parser():
    parser = argparse.ArgumentParser("Test c7n-mailer templates and mail")
    parser.add_argument("-c", "--config", required=True)
    parser.add_argument(
        "-d",
        "--dryrun",
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=False,
        help="Log messages that would be sent, but do not send",
    )
    parser.add_argument(
        "-T",
        "--template-print",
        dest="print_only",
        action="store_true",
        default=False,
        help="Just print rendered templates",
    )
    parser.add_argument(
        "-t", "--templates", default=None, type=str, help="message templates folder location"
    )
    parser.add_argument(
        "-p",
        "--plain",
        dest="plain",
        action="store_true",
        default=False,
        help="Expect MESSAGE_FILE to be a plain string, "
        "rather than the base64-encoded, gzipped SQS "
        "message format",
    )
    parser.add_argument(
        "-j",
        "--json-dump-file",
        dest="json_dump_file",
        type=str,
        action="store",
        default=None,
        help="If dump JSON of MESSAGE_FILE to this path; "
        "useful to base64-decode and gunzip a message",
    )
    parser.add_argument(
        "MESSAGE_FILE", type=str, nargs="?", help="Path to SQS message dump/content file"
    )
    parser.add_argument("-f", "--policy-file", type=str, help="Policy file to mimic MESSAGE_FILE")
    parser.add_argument(
        "--policy-name",
        type=str,
        help="Policy name if multiple policies to mimic MESSAGE_FILE. Defaults to the first.",
    )
    parser.add_argument(
        "-s", "--output-dir", type=str, help="Directory for policy output to mimic MESSAGE_FILE"
    )
    parser.add_argument(
        "-n",
        "--notify-index",
        type=int,
        default=0,
        help="Index of notify action if multiple notifies exist to mimic MESSAGE_FILE. "
        "Defaults to 0.",
    )
    return parser


def session_factory(config):
    return boto3.Session(region_name=config["region"], profile_name=config.get("profile"))


def mimic_sqs(region, policy_file, policy_name, notify_index, output_dir):
    template = {
        "event": None,
        "account_id": "snip",
        "account": "snip",
        "region": region,
        "execution_id": str(uuid.uuid4()),
        "execution_start": datetime.utcnow().timestamp(),
    }

    with open(policy_file, "r") as f:
        data = yaml.safe_load(f.read())
    policies = data["policies"]

    # if there is only one policy, select it
    # otherwise choose the one using the name as the unique identifier
    policy = None
    if len(data["policies"]) == 1 or policy_name is None:
        policy = data["policies"][0]
        policy_name = policy["name"]
    else:
        assert policy_name, "For multiple policies we need a policy name"
        for pol in policies:
            if pol["name"] == policy_name:
                policy = pol
                break
    assert policy

    template["policy"] = policy

    action = None
    notify_idx = 0
    for act in policy["actions"]:
        if act["type"] == "notify":
            if notify_index == notify_idx:
                action = act
                break
            notify_idx += 1

    template["action"] = action

    resources_path = "{}/{}/resources.json".format(output_dir, policy_name)
    with open(resources_path, "r") as f:
        resources = json.loads(f.read())

    template["resources"] = resources

    return template


def main():
    parser = setup_parser()
    options = parser.parse_args()

    module_dir = os.path.dirname(os.path.abspath(__file__))
    default_templates = [
        os.path.abspath(os.path.join(module_dir, "msg-templates")),
        os.path.abspath(os.path.join(module_dir, "..", "msg-templates")),
        os.path.abspath("."),
    ]
    templates = options.templates
    if templates:
        default_templates.append(os.path.abspath(os.path.expanduser(os.path.expandvars(templates))))

    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=logging.DEBUG, format=log_format)
    logging.getLogger("botocore").setLevel(logging.WARNING)

    with open(options.config) as fh:
        config = yaml.load(fh.read(), Loader=yaml.SafeLoader)

    jsonschema.validate(config, CONFIG_SCHEMA)
    setup_defaults(config)
    config["templates_folders"] = default_templates

    if options.MESSAGE_FILE:
        msg_file = options.MESSAGE_FILE
        tester = MailerTester(
            config,
            msg_file=msg_file,
            msg_plain=options.plain,
            json_dump_file=options.json_dump_file,
        )
    else:
        try:
            region = config["region"]
        except KeyError:
            region = os.environ["AWS_REGION"]
        except KeyError:
            region = "us-east-1"
        raw = mimic_sqs(
            region,
            options.policy_file,
            options.policy_name,
            options.notify_index,
            options.output_dir,
        )
        tester = MailerTester(config, raw)

    tester.run(options.dry_run, options.print_only)


if __name__ == "__main__":
    main()
