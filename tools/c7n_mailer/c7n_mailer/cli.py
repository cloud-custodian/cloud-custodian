import argparse
import boto3
import functools

import jsonschema
import yaml

from c7n_mailer import deploy, utils


CONFIG_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['queue_url', 'role', 'from_address'],
    'properties': {
        'queue_url': {'type': 'string'},
        'from_address': {'type': 'string'},
        'contact_tags': {'type': 'array', 'items': {'type': 'string'}},

        # Standard Lambda Function Config
        'region': {'type': 'string'},
        'role': {'type': 'string'},
        'memory': {'type': 'integer'},
        'timeout': {'type': 'integer'},
        'subnets': {'type': 'array', 'items': {'type': 'string'}},
        'security_groups': {'type': 'array', 'items': {'type': 'string'}},

        # Mailer Infrastructure Config
        'cache': {'type': 'string'},
        'ldap_uri': {'type': 'string'},
        'ldap_bind_dn': {'type': 'string'},
        'ldap_bind_user': {'type': 'string'},
        'ldap_bind_password': {'type': 'string'},
        'cross_accounts': {'type': 'object'},

        # SDK Config
        'profile': {'type': 'string'},
        'http_proxy': {'type': 'string'},
        'https_proxy': {'type': 'string'},
    }
}


def setup_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', required=True)
    return parser


def session_factory(config):
    return boto3.Session(
        region_name=config['region'],
        profile_name=config.get('profile'))


def main():
    parser = setup_parser()
    options = parser.parse_args()

    import logging
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('botocore').setLevel(logging.WARNING)

    with open(options.config) as fh:
        config = yaml.load(fh.read(), Loader=yaml.SafeLoader)

    jsonschema.validate(config, CONFIG_SCHEMA)
    utils.setup_defaults(config)

    try:
        deploy.provision(config, functools.partial(session_factory, config))
    except Exception:
        import traceback, pdb, sys
        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])


if __name__ == '__main__':
    main()
