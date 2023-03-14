# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import fnmatch
import click
import os


@click.command()
@click.option('--path', type=click.Path())
def main(path):

    for root, dirs, files in os.walk(path):
        if not files:
            continue
        for f in fnmatch.filter(files, "*json"):
            json_path = os.path.join(root, f)
            with open(json_path) as fh:
                data = json.load(fh)
                size = fh.tell()
            locations = data.get('body', {}).get('items', [])
            if not len(locations) > 2 or not isinstance(locations, dict):
                continue
            flocations = {}
            for k, l in locations.items():
                if 'warning' in l:
                    continue
                flocations[k] = l
            data['body']['items'] = flocations
            print("found aggregate result %s %d->%s" % (
                json_path, size, len(json.dumps(data, indent=2))))

            with open(json_path, 'w') as fh:
                fh.write(json.dumps(data, indent=2))


if __name__ == '__main__':
    main()
