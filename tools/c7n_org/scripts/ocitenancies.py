# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import os
import oci
import click
import logging
import configparser

from c7n.utils import yaml_dump

from c7n_oci.session import Session

DEFAULT_LOCATION = os.path.join("~", ".oci", "config")

log = logging.getLogger("ocitenancies")


def get_profile_from_tenancy_id(parser, sections, id, name):
    for section in sections:
        for k, v in parser.items(section):
            if k == "tenancy" and v == id:
                return section

    return "<ADD_PROFILE>"


def get_region_from_tenancy_id(parser, sections, id):
    for section in sections:
        tenancy_id = parser.get(section, "tenancy")
        if tenancy_id == id:
            return parser.get(section, "region")


def get_config_parser():
    parser = configparser.ConfigParser(interpolation=None)
    expanded_file_location = os.path.expanduser(DEFAULT_LOCATION)
    if os.path.isfile(expanded_file_location) and not parser.read(expanded_file_location):
        raise Exception(
            "Could not find config file at {}, please follow the instructions in the link to"
            " setup the config file"
            " https://docs.cloud.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm".format(
                DEFAULT_LOCATION
            )
        )
    return parser


def create_config_entry(name, profile, region=None):
    tenancy_info = {"name": name, "profile": profile}
    if region:
        tenancy_info["regions"] = [region]
    return tenancy_info


def add_config_tenancies(parser, sections, tenancies, tenancy_set):
    for section in sections:
        tenancy_id = parser.get(section, "tenancy")
        if tenancy_id:
            tenancy_set.add(tenancy_id)
            tenancy_info = create_config_entry(
                section,
                section,
                get_region_from_tenancy_id(parser, sections, tenancy_id),
            )
            tenancies.append(tenancy_info)
    return tenancies


def get_config_sections(parser):
    sections = parser.sections()
    sections.append(parser.default_section)
    return sections


def add_organization_child_tenancies(tenancies, tenancy_set, parser, sections):
    client = Session(oci.config.from_file()).client(
        "oci.tenant_manager_control_plane.OrganizationClient")
    orgs_response = client.list_organizations(
        compartment_id=parser.get(parser.default_section, "tenancy")
        )
    orgs = orgs_response.data.items
    for org in orgs:
        tenancies_response = client.list_organization_tenancies(organization_id=org.id)
        org_tenancies = tenancies_response.data.items
        for tenancy in org_tenancies:
            if tenancy.lifecycle_state != "ACTIVE" or tenancy.tenancy_id in tenancy_set:
                continue
            tenancy_info = create_config_entry(
                tenancy.name,
                get_profile_from_tenancy_id(parser, sections, tenancy.tenancy_id, tenancy.name),
            )
            tenancies.append(tenancy_info)
            tenancy_set.add(tenancy.tenancy_id)


@click.command()
@click.option(
    "-f",
    "--output",
    type=click.File("w"),
    default="-",
    help="File to store the generated config (default stdout)",
)
@click.option(
    "--add-child-tenancies",
    is_flag=True,
    default=False,
    help="Add the child tenancies to the c7n-org configuration file",
)
def main(output, add_child_tenancies):
    """Generate a c7n-org OCI tenancies configuration file using OCI configuration file and
    OCI Organizations API

    With c7n-org you can then run policies or arbitrary scripts across
    tenancies.
    """
    tenancies = []
    tenancy_set = set()
    parser = get_config_parser()
    sections = get_config_sections(parser)
    # Add the tenancies from OCI configurtion file
    add_config_tenancies(parser, sections, tenancies, tenancy_set)
    if add_child_tenancies:
        # Add the child tenancies using OCI Organizations API
        add_organization_child_tenancies(tenancies, tenancy_set, parser, sections)
    print(yaml_dump({"tenancies": tenancies}), file=output)


if __name__ == "__main__":
    main()
