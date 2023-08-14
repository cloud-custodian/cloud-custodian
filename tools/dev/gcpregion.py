import click
import requests
import jmespath
import json


@click.command()
@click.option('-f', '--output', type=click.File('w'), default='-')
def main(output):
    data = requests.get('https://www.gstatic.com/ipranges/cloud.json').json()
    regions = sorted(list(set(jmespath.search('prefixes[].scope', data))))
    regions.remove('global')
    output.write(json.dumps(regions, indent=2))


if __name__ == '__main__':
    main()
