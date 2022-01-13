import click
import boto3
import json
import os


from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def process_resource_schema(cfn, rtype):
    return cfn.describe_type(TypeName=rtype, Type='RESOURCE')


def process_resource_list(control, rinfo):
    control.list_resources(TypeName=rinfo['typeName'])
    return True

    
@click.group()
def cli():
    """
    """
    os.environ['AWS_RETRY_MODE'] = 'adaptive'
    os.environ['AWS_MAX_ATTEMPTS'] = '6'


@cli.command()
@click.option('-d', '--schema-dir', required=True, type=click.Path())
def check_permissions(schema_dir):

    sdir = Path(str(schema_dir))
    control = boto3.client('cloudcontrol')
    
    for p in sdir.rglob('*.json'):
        rinfo = json.loads(p.read_text())
        if not rinfo.get('handlers'):
            print(f"type: {rinfo['typeName']} missing handler info")
        

@cli.command()
@click.option('-d', '--schema-dir', required=True, type=click.Path())
def check_list(schema_dir):

    sdir = Path(str(schema_dir))
    control = boto3.client('cloudcontrol')
    with ThreadPoolExecutor(max_workers=4) as w:
        results = {}
    
        for p in sdir.rglob('*.json'):
            rinfo = json.loads(p.read_text())
            results[w.submit(process_resource_list, control, rinfo)] = (p, rinfo)
            
        for f in as_completed(results):
            p, rinfo = results[f]
            exc = f.exception()
            if f.exception():
                print(f"type: {rinfo['typeName']} error {f.exception()}")
                p.unlink()
                continue
        
    
@cli.command()
@click.option('-o', '--output', required=True, type=click.Path())
def download(output):
    """download schema updates"""
    output = Path(str(output))

    cfn = boto3.client('cloudformation')
    resources = sorted(
        [
            t['TypeName']
            for t in cfn.get_paginator('list_types')
            .paginate(
                Visibility='PUBLIC',
                Filters={'Category': 'AWS_TYPES'},
                ProvisioningType='FULLY_MUTABLE',
                DeprecatedStatus='LIVE',
                Type='RESOURCE',
            )
            .build_full_result()['TypeSummaries']
        ]
    )

    results = {}

    with ThreadPoolExecutor(max_workers=4) as w:
        results = {}
        for r in resources:
            results[w.submit(process_resource_schema, cfn, r)] = r

        for f in as_completed(results):
            r = results[f]
            if f.exception():
                print(f'type: {r} error {f.exception()}')
                continue
            fpath = output / ("%s.json" % r.replace('::', '_').lower())
            fpath.write_text(json.dumps(json.loads(f.result()['Schema']), indent=2))
            print(f"downloaded {r}")


if __name__ == '__main__':
    cli()
