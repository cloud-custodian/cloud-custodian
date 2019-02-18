# Copyright 2019 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import yaml
import re
import os
import jinja2
import boto3
import logging

# --------------------------------------
# Update the variables in this section
# --------------------------------------
rendered_filename = "c7n-autodoc.html"

# This tool will create a link to each policy.  This URL will be used
# as the base.  See regex below.
file_url_base = 'https://github.com/your_project_path'

# This regex will be used in a re.sub to go from local file path to URL
file_url_regex = re.compile(r'.*\/my_dir\/my_dir2')

# This is the local directory that will be crawled to find policy files
# c7n_policy_directory = './aws/c7n/'
c7n_policy_directory = '/path/to/files'

# This regex will be used to identify files in the directory listed above
file_regex = re.compile('(custodian.*yml$)')

# This regex will be used with a regex 'search' against the file path
# & name to determine category valid categories are: 'Security &
# Governance' and 'Cost Controls' if the below regex does not match it
# will be category 'Cost Controls' Example:
# '/misc_cloud_stuff/c7n/aws/security-governance/policy1.yml' would
# match and thus be put in the 'Security & Governance' category.
category_regex = re.compile('security-governance')

# S3 information
s3_upload = True
s3_bucket_name = 's3-bucket-name'
s3_bucket_path = ''

# Environment tagging - Many users will have a tagging strategy which dictates
# what environments a policy is deployed.  Use the following fields to include
# environment columns to your autodoc.
# Dictionary key is the tag which should exist on the policy and the value is what
# you will see in the autodoc
environment_column = True
environment_tags = {
    'environment:Sandbox': 'Sandbox',
    'environment:Test': 'Test',
    'environment:Production': 'Production'
}

# -------------------------------------------------------
# Don't alter
# -------------------------------------------------------
c7n_data = {}
jinja2_template_filename = "./template.html.j2"


# -------------------------------------------------------
# You can customize the automated documentation by altering
# the code directly in this script or the associated jinja2 template
# -------------------------------------------------------


def create_html_file():

    script_path = os.path.dirname(os.path.abspath(__file__))
    template_file_path = os.path.join(script_path, jinja2_template_filename)
    rendered_file_path = os.path.join(script_path, rendered_filename)
    environment = jinja2.Environment(loader=jinja2.FileSystemLoader(script_path))

    render_vars = {
        "c7n_data": c7n_data,
        "environment_column": environment_column,
        "environment_tags": environment_tags
    }

    with open(rendered_file_path, "w") as result_file:
        result_file.write(environment.get_template(template_file_path).render(render_vars))

    logging.info("File created: %s", rendered_file_path)

    return rendered_file_path


def get_file_url(path):
    """ Update this function to help build the link to your file
    """
    new_path = re.sub(file_url_regex, file_url_base, path)
    return new_path


def gather_file_data(mydir):
    """ Gather policy information from files
    """
    policies = {}
    for root, dirs, files in os.walk(mydir):
        for file in files:
            if file_regex.match(file):
                file_path = root + '/' + file
                logging.info('Processing file %s', file_path)
                with open(file_path, 'r') as stream:
                    try:
                        category = ('Security & Governance' if category_regex.search(file_path)
                                    else 'Cost Controls')
                        policies = yaml.load(stream)
                        for policy in policies['policies']:
                            logging.info('Processing policy %s', policy['name'])
                            policy['file_url'] = get_file_url(file_path)
                            resource_type = policy['resource']
                            if category not in c7n_data:
                                c7n_data[category] = {}
                            if resource_type not in c7n_data[category]:
                                c7n_data[category][resource_type] = []
                            c7n_data[category][resource_type].append(policy)
                    except yaml.YAMLError as exc:
                        logging.error(exc)


def upload_to_s3(file_path):
    """ Upload html file to S3
    """
    logging.info("Uploading file to S3 bucket: %s", s3_bucket_name)
    s3 = boto3.resource('s3')
    s3_filename = s3_bucket_path + rendered_filename
    s3.Bucket(s3_bucket_name).upload_file(
        file_path, s3_filename, ExtraArgs={
            'ContentType': 'text/html', 'ACL': 'public-read'})


def main():
    logging_format = '%(asctime)s %(levelname)-4s %(message)s'
    logging.basicConfig(level=logging.INFO, format=logging_format)
    gather_file_data(c7n_policy_directory)
    rendered_file = create_html_file()
    if s3_upload:
        upload_to_s3(rendered_file)


if __name__ == '__main__':
    main()
