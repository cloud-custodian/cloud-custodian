# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import yaml
import re
import os
import jinja2
import boto3
import logging
import argparse
import time
import datetime
import jsonschema

c7n_data = {}


def create_html_file(config):
    """ You can customize the automated documentation by altering
        the code directly in this script or the associated jinja2 template
    """
    logging.debug("Starting create_html_file")
    logging.debug(
        "\tjinja2_template_file = {}"
        .format(config['jinja2_template_filename']))
    logging.debug(
        "\ttrendered_filename = {}"
        .format(config['rendered_filename']))

    ts = time.time()
    timestamp = datetime.datetime.utcfromtimestamp(ts).strftime(
        '%Y-%m-%d %H:%M:%S')
    script_path = os.path.dirname(os.path.abspath(__file__))
    rendered_file_path = os.path.join(
        script_path, config['rendered_filename'])
    environment = jinja2.Environment(
        loader=jinja2.FileSystemLoader(script_path))

    environment_column = True if config['environment_tags'] else False

    render_vars = {
        "timestamp": timestamp,
        "c7n_data": c7n_data,
        "environment_column": environment_column,
        "environment_tags": config['environment_tags']
    }

    with open(rendered_file_path, "w") as result_file:
        result_file.write(
            environment.get_template(config['jinja2_template_filename'])
            .render(render_vars))

    logging.debug("File created: %s", rendered_file_path)

    return rendered_file_path


def get_file_url(path, config):
    """ Update this function to help build the link to your file
    """
    file_url_regex = re.compile(config['file_url_regex'])
    new_path = re.sub(file_url_regex, config['file_url_base'], path)
    return new_path


def gather_file_data(config):
    """ Gather policy information from files
    """
    file_regex = re.compile(config['file_regex'])
    category_regex = re.compile(config['category_regex'])
    policies = {}

    for root, dirs, files in os.walk(config['c7n_policy_directory']):
        for file in files:
            if file_regex.match(file):
                file_path = root + '/' + file
                logging.debug('Processing file %s', file_path)
                with open(file_path, 'r') as stream:
                    try:
                        if category_regex.search(file_path):
                            category = 'Security & Governance'
                        else:
                            category = 'Cost Controls'

                        policies = yaml.load(stream)
                        for policy in policies['policies']:
                            logging.debug(
                                'Processing policy %s', policy['name'])
                            policy['file_url'] = get_file_url(
                                file_path, config)
                            resource_type = policy['resource']
                            if category not in c7n_data:
                                c7n_data[category] = {}
                            if resource_type not in c7n_data[category]:
                                c7n_data[category][resource_type] = []
                            c7n_data[category][resource_type].append(policy)
                    except yaml.YAMLError as exc:
                        logging.error(exc)


def upload_to_s3(file_path, config):
    """ Upload html file to S3
    """
    logging.info("Uploading file to S3 bucket: %s", config['s3_bucket_name'])
    s3 = boto3.resource('s3')
    s3_filename = config['s3_bucket_path'] + config['rendered_filename']
    s3.Bucket(config['s3_bucket_name']).upload_file(
        file_path, s3_filename, ExtraArgs={
            'ContentType': 'text/html', 'ACL': 'public-read'})


def validate_inputs(config):

    CONFIG_SCHEMA = {
        'type': 'object',
        'additionalProperties': False,
        'required': [
            'c7n_policy_directory',
            'file_regex',
            'jinja2_template_filename',
            'rendered_filename',
            'category_regex'
        ],
        'properties': {
            'jinja2_template_filename': {'type': 'string'},
            'rendered_filename': {'type': 'string'},
            'c7n_policy_directory': {'type': 'string'},
            'file_regex': {'type': 'string'},
            'category_regex': {'type': 'string'},
            'file_url_base': {'type': 'string'},
            'file_url_regex': {'type': 'string'},
            's3_bucket_name': {'type': 'string'},
            's3_bucket_path': {'type': 'string'},
            'environment_tags': {'type': 'object'}
        }
    }

    jsonschema.validate(config, CONFIG_SCHEMA)
    logging.info("Successfully validated configuration file")


def main():

    parser = argparse.ArgumentParser(
        description='Automatic policy documentation for Cloud Custodian.')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument(
        '-c', '--config_filename',
        required=True,
        dest='config_filename',
        help='YAML config filename')
    args = parser.parse_args()

    with open(args.config_filename) as fh:
        config_tmp = yaml.load(fh.read(), Loader=yaml.SafeLoader)

    config = config_tmp['config']
    validate_inputs(config)

    logging_format = '%(asctime)s %(levelname)-4s %(message)s'

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format=logging_format)
    else:
        logging.basicConfig(level=logging.INFO, format=logging_format)

    gather_file_data(config)
    rendered_file = create_html_file(config)
    if 's3_bucket_name' in config:
        upload_to_s3(rendered_file, config)


if __name__ == '__main__':
    main()
