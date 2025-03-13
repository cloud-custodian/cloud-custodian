# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import click
import logging
import os
from c7n.config import Bag, Config
from c7n.resources.aws import ApiStats
from c7n.credentials import assumed_session, SessionFactory
from c7n.utils import yaml_dump
import re

ROLE_TEMPLATE = "arn:aws:iam::{Id}:role/OrganizationAccountAccessRole"
NAME_TEMPLATE = "{name}"

log = logging.getLogger("orgaccounts")


@click.command()
@click.option(
    "--role",
    default=ROLE_TEMPLATE,
    help="Role template for accounts in the config, defaults to %s" % ROLE_TEMPLATE,
)
@click.option(
    "--name",
    default=NAME_TEMPLATE,
    help="Name template for accounts in the config, defaults to %s" % NAME_TEMPLATE,
)
@click.option(
    "--ou",
    multiple=True,
    default=["/"],
    help="Only export the given subtrees of an organization",
)
@click.option(
    "-r",
    "--regions",
    multiple=True,
    help="If specified, set regions per account in config",
)
@click.option("--assume", help="Role to assume for Credentials")
@click.option("--profile", help="AWS CLI Profile to use for Credentials")
@click.option(
    "-f",
    "--output",
    type=click.File("w"),
    help="File to store the generated config (default stdout)",
)
@click.option(
    "-a", "--active", is_flag=True, default=False, help="Get only active accounts"
)
@click.option(
    "-i",
    "--ignore",
    multiple=True,
    help="list of accounts that won't be added to the config file",
)
def main(role, name, ou, assume, profile, output, regions, active, ignore):
    """Generate a c7n-org accounts config file using AWS Organizations

    With c7n-org you can then run policies or arbitrary scripts across
    accounts.
    """
    logging.basicConfig(level=logging.INFO)

    stats, session = get_session(assume, "c7n-org", profile)
    client = session.client("organizations")
    accounts = []
    for path in ou:
        ou = get_ou_from_path(client, path)
        accounts.extend(get_accounts_for_ou(client, ou, active, ignoredAccounts=ignore))

    results = []
    for a in accounts:
        tags = []

        path_parts = a["Path"].strip("/").split("/")
        for idx, _ in enumerate(path_parts):
            tags.append("path:/%s" % "/".join(path_parts[: idx + 1]))

        for k, v in a.get("Tags", {}).items():
            tags.append("{}:{}".format(k, v))

        a["OrgId"] = a["Arn"].split("/")[1]
        if not role.startswith("arn"):
            arn_role = "arn:aws:iam::{}:role/{}".format(a["Id"], role)
        else:
            arn_role = role.format(**a)
        ainfo = {
            "account_id": a["Id"],
            "email": a["Email"],
            "display_name": a["Name"],
            "name": a["Name"],
            "org_id": a["OrgId"],
            "tags": tags,
            "role": arn_role,
        }
        ainfo["name"] = name.format(**ainfo)
        if regions:
            ainfo["regions"] = list(regions)
        if "Tags" in a and a["Tags"]:
            ainfo["vars"] = a["Tags"]

        results.append(ainfo)

    # log.info('api calls {}'.format(stats.get_metadata()))
    print(yaml_dump({"accounts": results}), file=output)


def get_session(role, session_name, profile):
    region = os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")
    stats = ApiStats(Bag(), Config.empty())
    if role:
        s = assumed_session(role, session_name, region=region)
    else:
        s = SessionFactory(region, profile)()
    stats(s)
    return stats, s


def get_ou_from_path(client, path):
    ou = client.list_roots()["Roots"][0]

    if path == "/":
        ou["Path"] = path
        return ou

    ou_pager = client.get_paginator("list_organizational_units_for_parent")
    for part in path.strip("/").split("/"):
        found = False
        for page in ou_pager.paginate(ParentId=ou["Id"]):
            for child in page.get("OrganizationalUnits"):
                if child["Name"] == part:
                    found = True
                    ou = child
                    break
            if found:
                break
        if found is False:
            raise ValueError("No OU named:%r found in path: %s" % (path, path))
    ou["Path"] = path
    return ou


def get_sub_ous(client, ou):
    results = [ou]
    ou_pager = client.get_paginator("list_organizational_units_for_parent")
    for sub_ou in (
        ou_pager.paginate(ParentId=ou["Id"])
        .build_full_result()
        .get("OrganizationalUnits")
    ):
        sub_ou["Path"] = "/%s/%s" % (ou["Path"].strip("/"), sub_ou["Name"])
        results.extend(get_sub_ous(client, sub_ou))
    return results


def get_accounts_for_ou(client, ou, active, recursive=True, ignoredAccounts=()):
    results = []
    ous = [ou]
    if recursive:
        ous = get_sub_ous(client, ou)

    account_pager = client.get_paginator("list_accounts_for_parent")
    for ou in ous:
        for a in (
            account_pager.paginate(ParentId=ou["Id"])
            .build_full_result()
            .get("Accounts", [])
        ):
            a["Path"] = ou["Path"]
            a["Tags"] = {
                t["Key"]: t["Value"]
                for t in client.list_tags_for_resource(ResourceId=a["Id"]).get(
                    "Tags", ()
                )
            }
            if a["Id"] in ignoredAccounts:
                continue

            if active:
                if a["Status"] == "ACTIVE":
                    results.append(a)
            else:
                results.append(a)
    return results


if __name__ == "__main__":
    main()
