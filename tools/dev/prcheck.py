from ghapi.all import GhApi, paged
import pprint
import json
import operator
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def cli():
    """Check for directories which have open prs"""


@cli.command()
@click.option('--output', type=click.File('w'))
def download(output):
    """Download extant prs"""
    api = GhApi(owner='cloud-custodian', repo='cloud-custodian')

    pr_data = []
    for page in paged(api.pulls.list, per_page=50):
        for pr in page:
            pr_meta = {
                'number': pr['number'],
                'title': pr['title'],
                'created_at': pr['created_at'],
                'updated_at': pr['updated_at'],
                'user': pr['user']['login'],
                'files': [],
            }
            for file_page in paged(api.pulls.list_files, pull_number=pr['number']):
                pr_meta['files'].extend([finfo['filename'] for finfo in file_page])

            pr_data.append(pr_meta)
    json.dump(pr_data, output, indent=2)


@cli.command()
@click.option('--input', type=click.File('r'))
@click.option('--tree', type=click.Path())
def inspect(input, tree):
    """show the prs that modify a given directory"""

    pr_data = json.load(input)
    root = Path(str(tree))
    dirs = set(sorted(get_dirs(root)))

    table = Table(title="Pull requests")
    table.add_column("PR")
    table.add_column("Author")
    table.add_column("Created")
    table.add_column("Title")

    for pr_meta in sorted(pr_data, key=operator.itemgetter('created_at')):
        pr_dirs = set()
        for fname in pr_meta['files']:
            for p in Path(fname).parents:
                if p in dirs and p not in pr_dirs:
                    pr_dirs.add(p)
                    found = True
        pr_meta.pop('files')
        pr_meta['dirs'] = list(pr_dirs)
        if pr_dirs:
            table.add_row(
                str(pr_meta['number']),
                pr_meta['user'],
                pr_meta['created_at'],
                pr_meta['title'].strip(),
            )

    console.print(table)


@cli.command()
@click.option('--input', type=click.File('r'))
@click.option('--tree', type=click.Path())
def untouched(input, tree):
    """show directories which don't have open prs against them"""

    pr_data = json.load(input)
    root = Path(str(tree))
    dirs = sorted(get_dirs(root))

    for pr in pr_data:
        for fname in pr['files']:
            for p in Path(fname).parents:
                if p in dirs:
                    dirs.remove(p)

    pprint.pprint(dirs)


def get_dirs(root):
    dirs = []
    py_files = False
    for el in root.iterdir():
        if not el.is_dir():
            if el.name.endswith('.py'):
                py_files = True
            continue
        if 'data' in el.name:
            continue
        if 'terraform' in el.name:
            continue
        if '__pycache__' in el.name:
            continue
        if 'build' in el.name:
            continue
        dirs.extend(get_dirs(el))
    if py_files:
        dirs.append(root)
    return dirs


if __name__ == '__main__':
    try:
        cli()
    except SystemExit:
        raise
    except:
        import sys, pdb, traceback

        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])
