import json

import botocore.session
import click


@click.command()
@click.option('-f', '--output', default='-', type=click.File('w'))
def main(output):
    session = botocore.session.get_session()
    loader = session.get_component('data_loader')
    endpoints = loader.load_data('endpoints')
    region_partition_map = {}

    for partition in endpoints['partitions']:
        partition_name = partition['partition']
        region_partition_map.update({region: partition_name for region in partition['regions']})

    json.dump(region_partition_map, output, indent=4, sort_keys=True)


if __name__ == '__main__':
    main()
