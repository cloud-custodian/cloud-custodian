import argparse
from datetime import datetime, timedelta
import logging


from c7n.credentials import SessionFactory
from c7n.policy import load
from c7n.resources import load_resources
from c7n.utils import dumps


def setup_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', required=True)
    parser.add_argument('--assume', dest="assume_role")
    parser.add_argument('--profile')
    parser.add_argument('--region', default='us-east-1')
    parser.add_argument('--start', default='us-east-1')
    parser.add_argument('--end', default='us-east-1')
    parser.add_argument('--days', default='us-east-1')
    parser.add_argument('--period', type=int, default=3600)
    return parser


def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('botocore').setLevel(logging.WARNING)

    parser = setup_parser()
    options = parser.parse_args()
    options.log_group = None
    options.cache = None

    factory = SessionFactory(
        options.region, options.profile, options.assume_role)

    session = factory()
    client = session.client('cloudwatch')

    load_resources()
    policies = load(options, options.config)

    start = datetime.now().replace(
          hour=0, minute=0, second=0, microsecond=0) - timedelta(14)
    end = datetime.now().replace(
          hour=0, minute=0, second=0, microsecond=0)
    period = 24 * 60 * 14

    data = {}
    for p in policies:
        logging.info('Getting %s metrics', p)
        data[p.name] = p.get_metrics(start, end, period)
    print dumps(data, indent=2)


if __name__ == '__main__':
    main()
