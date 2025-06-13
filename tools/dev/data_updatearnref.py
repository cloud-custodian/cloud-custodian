#!/usr/bin/env python3
#
# Copyright 2019 Duo Security
# BSD 3 Clause, full text below.
#
# Modifications to produce only the data of interest (resource arns)
# original source
# https://github.com/duo-labs/parliament/blob/main/utils/update_iam_data.py

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# 1. Redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution.
# 3. Neither the name of the copyright holder nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.


from os import listdir
from os.path import isfile, join
import re
import json
import requests
from pathlib import Path

from bs4 import BeautifulSoup

# Code for get_links_from_base_actions_resources_conditions_page and update_html_docs_directory borrowed from https://github.com/salesforce/policy_sentry/blob/1126f174f49050b95bddf7549aedaf11fa51a50b/policy_sentry/scraping/awsdocs.py#L31   # noqa
BASE_DOCUMENTATION_URL = "https://docs.aws.amazon.com/service-authorization/latest/reference/reference_policies_actions-resources-contextkeys.html"


def get_links_from_base_actions_resources_conditions_page():
    """Gets the links from the actions, resources, and conditions keys
    page, and returns their filenames."""
    html = requests.get(BASE_DOCUMENTATION_URL)
    soup = BeautifulSoup(html.content, "html.parser")
    html_filenames = []
    for i in soup.find("div", {"class": "highlights"}).findAll("a"):
        html_filenames.append(i["href"])
    return html_filenames


def update_html_docs_directory(html_docs_destination):
    """
    Updates the HTML docs from remote location to either (1) local directory
    (i.e., this repository, or (2) the config directory
    :return:
    """
    link_url_prefix = "https://docs.aws.amazon.com/service-authorization/latest/reference/"
    initial_html_filenames_list = get_links_from_base_actions_resources_conditions_page()
    # Remove the relative path so we can download it
    html_filenames = [sub.replace("./", "") for sub in initial_html_filenames_list]

    for page in html_filenames:
        response = requests.get(link_url_prefix + page, allow_redirects=False)
        # Replace the CSS stuff. Basically this:
        """
        <link href='href="https://docs.aws.amazon.com/images/favicon.ico"' rel="icon" type="image/ico"/>
        <link href='href="https://docs.aws.amazon.com/images/favicon.ico"' rel="shortcut icon" type="image/ico"/>
        <link href='href="https://docs.aws.amazon.com/font/css/font-awesome.min.css"' rel="stylesheet" type="text/css"/>
        <link href='href="https://docs.aws.amazon.com/css/code/light.css"' id="code-style" rel="stylesheet" type="text/css"/>
        <link href='href="https://docs.aws.amazon.com/css/awsdocs.css?v=20181221"' rel="stylesheet" type="text/css"/>
        <link href='href="https://docs.aws.amazon.com/assets/marketing/css/marketing-target.css"' rel="stylesheet" type="text/css"/>
        list_amazonkendra.html downloaded
        """  # noqa
        soup = BeautifulSoup(response.content, "html.parser")
        for link in soup.find_all("link"):
            if link.get("href").startswith("/"):
                temp = link.attrs["href"]
                link.attrs["href"] = link.attrs["href"].replace(
                    temp, f"https://docs.aws.amazon.com{temp}"
                )

        for script in soup.find_all("script"):
            try:
                if "src" in script.attrs:
                    if script.get("src").startswith("/"):
                        temp = script.attrs["src"]
                        script.attrs["src"] = script.attrs["src"].replace(
                            temp, f"https://docs.aws.amazon.com{temp}"
                        )
            except TypeError as t_e:
                print(t_e)
                print(script)
            except AttributeError as a_e:
                print(a_e)
                print(script)

        with open(html_docs_destination + page, "w") as file:
            # file.write(str(soup.html))
            file.write(str(soup.prettify()))
            file.close()
        # print(f"{page} downloaded")


def chomp(string):
    """This chomp cleans up all white-space, not just at the ends"""
    string = str(string)
    response = string.replace("\n", " ")  # Convert line ends to spaces
    response = re.sub(" [ ]*", " ", response)  # Truncate multiple spaces to single space
    response = re.sub("^[ ]*", "", response)  # Clean start
    return re.sub("[ ]*$", "", response)  # Clean end


def no_white_space(string):
    string = str(string)
    response = string.replace("\n", "")  # Convert line ends to spaces
    response = re.sub("[ ]*", "", response)
    return response


def header_matches(string, table):
    headers = [chomp(str(x)).lower() for x in table.find_all("th")]
    match_found = False
    for header in headers:
        if string in header:
            match_found = True
    if not match_found:
        return False
    return True


# Create the docs directory
Path("iam_docs").mkdir(parents=True, exist_ok=True)

update_html_docs_directory("iam_docs/")

mypath = "./iam_docs/"
schema = []

# for filename in ['list_amazons3.html']:
for filename in [f for f in listdir(mypath) if isfile(join(mypath, f))]:
    if not filename.startswith("list_"):
        continue

    with open(mypath + filename, "r") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
        main_content = soup.find(id="main-content")
        if main_content is None:
            continue

        # Get service name
        title = main_content.find("h1", class_="topictitle").text
        title = re.sub(".*Actions, resources, and condition keys for *", "", str(title))
        title = title.replace("</h1>", "")
        service_name = chomp(title)

        prefix = ""
        for c in main_content.find("h1", class_="topictitle").parent.children:
            if "prefix" in str(c):
                prefix = str(c)
                prefix = prefix.split('<code class="code">')[1]
                prefix = chomp(prefix.split("</code>")[0])
                break

        service_schema = {
            "service_name": service_name,
            "prefix": prefix,
            "privileges": [],
            "resources": [],
            "conditions": [],
        }

        tables = main_content.find_all("div", class_="table-contents")

        for table in tables:
            # There can be 3 tables, the actions table, an ARN table, and a condition key table
            # Example: https://docs.aws.amazon.com/IAM/latest/UserGuide/list_awssecuritytokenservice.html
            if not header_matches("actions", table) or not header_matches("description", table):
                continue

            rows = table.find_all("tr")
            row_number = 0
            while row_number < len(rows):
                row = rows[row_number]

                cells = row.find_all("td")
                if len(cells) == 0:
                    # Skip the header row, which has th, not td cells
                    row_number += 1
                    continue

                if len(cells) != 6:
                    # Sometimes the privilege contains Scenarios, and
                    # I don't know how to handle this
                    break
                    # raise Exception("Unexpected format in {}: {}".format(prefix, row))

                # See if this cell spans multiple rows
                rowspan = 1
                if "rowspan" in cells[0].attrs:
                    rowspan = int(cells[0].attrs["rowspan"])

                priv = ""
                # Get the privilege
                for link in cells[0].find_all("a"):
                    if "href" not in link.attrs:
                        # Skip the <a id='...'> tags
                        continue
                    priv = chomp(link.text)
                if priv == "":
                    priv = chomp(cells[0].text)

                description = chomp(cells[1].text)
                access_level = chomp(cells[2].text)

                resource_types = []
                resource_cell = 3

                while rowspan > 0:
                    if len(cells) == 3 or len(cells) == 6:
                        # ec2:RunInstances contains a few "scenarios" which start in the
                        # description field, len(cells) is 5.
                        # I'm ignoring these as I don't know how to handle them.
                        # These include things like "EC2-Classic-InstanceStore" and
                        # "EC2-VPC-InstanceStore-Subnet"

                        resource_type = chomp(cells[resource_cell].text)
                        condition_keys_element = cells[resource_cell + 1]
                        condition_keys = []
                        if condition_keys_element.text != "":
                            for key_element in condition_keys_element.find_all("p"):
                                condition_keys.append(chomp(key_element.text))

                        dependent_actions_element = cells[resource_cell + 2]
                        dependent_actions = []
                        if dependent_actions_element.text != "":
                            for action_element in dependent_actions_element.find_all("p"):
                                dependent_actions.append(chomp(action_element.text))
                        resource_types.append(
                            {
                                "resource_type": resource_type,
                                "condition_keys": condition_keys,
                                "dependent_actions": dependent_actions,
                            }
                        )
                    rowspan -= 1
                    if rowspan > 0:
                        row_number += 1
                        resource_cell = 0
                        row = rows[row_number]
                        cells = row.find_all("td")

                if "[permission only]" in priv:
                    priv = priv.split(" ")[0]

                privilege_schema = {
                    "privilege": priv,
                    "description": description,
                    "access_level": access_level,
                    "resource_types": resource_types,
                }

                service_schema["privileges"].append(privilege_schema)
                row_number += 1

        # Get resource table
        for table in tables:
            if not header_matches("resource types", table) or not header_matches("arn", table):
                continue

            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) == 0:
                    # Skip the header row, which has th, not td cells
                    continue

                if len(cells) != 3:
                    raise Exception(
                        "Unexpected number of resource cells {} in {}".format(len(cells), filename)
                    )

                resource = chomp(cells[0].text)

                arn = no_white_space(cells[1].text)
                conditions = []
                for condition in cells[2].find_all("p"):
                    conditions.append(chomp(condition.text))

                service_schema["resources"].append(
                    {"resource": resource, "arn": arn, "condition_keys": conditions}
                )

        # Get condition keys table
        for table in tables:
            if not (
                header_matches("<th> condition keys </th>", table)
                and header_matches("<th> type </th>", table)
            ):
                continue

            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")

                if len(cells) == 0:
                    # Skip the header row, which has th, not td cells
                    continue

                if len(cells) != 3:
                    raise Exception(
                        "Unexpected number of condition cells {} in {}".format(len(cells), filename)
                    )

                condition = no_white_space(cells[0].text)
                description = chomp(cells[1].text)
                value_type = chomp(cells[2].text)

                service_schema["conditions"].append(
                    {
                        "condition": condition,
                        "description": description,
                        "type": value_type,
                    }
                )
        schema.append(service_schema)


schema.sort(key=lambda x: x["prefix"])

arn_ref = {}
for s in schema:
    if not s.get('resources'):
        continue
    arn_ref[s['prefix']] = {r['resource']: r['arn'] for r in s['resources']}

print(json.dumps(arn_ref, indent=2, sort_keys=True))
