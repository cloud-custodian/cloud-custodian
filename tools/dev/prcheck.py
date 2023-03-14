import pprint
import json
import operator
from pathlib import Path

import click
from ghapi.all import GhApi
from ghapi.all import paged
from rich.console import Console
from rich.table import Table
from rich.progress import track

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


DIR_LABEL_MAP = {
    'c7n/resources': 'provider/aws',
    'tools/c7n_gcp': 'provider/gcp',
    'tools/c7n_azure': 'provider/azure',
    'tools/c7n_left': 'provider/shift-left',
    'tools/c7n_mailer': 'area/tools-mailer',
    'tools/c7n_tencentcloud': 'provider/tencentcloud',
}


@cli.command()
@click.option('--input', type=click.File('r'))
@click.option('--tree', type=click.Path(), multiple=True)
@click.option('--check', is_flag=True, default=False)
@click.option('--tag', is_flag=True, default=False)
def inspect(input, tree, check, tag):
    """show the prs that modify a given directory"""

    pr_data = json.load(input)

    for root in tree:
        root = Path(str(root))
        prs = list(get_prs(pr_data, root))
        if check and prs:
            prs = check_prs(prs)
        if tag and prs:
            tag_prs(root, prs)
        if prs:
            print_prs(root, prs)
        else:
            console.print(f'no prs for {root.name}')


def check_prs(prs):
    api = GhApi(owner='cloud-custodian', repo='cloud-custodian')
    results = []
    for pr in track(prs, description="Checking current PR state"):
        cur = api.pulls.get(pr['number'])
        if cur['merged'] or cur['closed_at']:
            continue
        results.append(pr)
    return results


def tag_prs(root, prs):
    if str(root) not in DIR_LABEL_MAP:
        console.print(f'{root} not in known labels')
        return
    api = GhApi(owner='cloud-custodian', repo='cloud-custodian')
    for pr in track(prs, description="Adding Labels"):
        label = DIR_LABEL_MAP[str(root)]
        api.issues.add_labels(issue_number=pr['number'], labels=[label])


def get_prs(pr_data, root, sort='created_at', sort_reverse=False):
    dirs = set(sorted(get_dirs(root)))
    for pr_meta in sorted(pr_data, key=operator.itemgetter(sort), reverse=sort_reverse):
        pr_meta = dict(pr_meta)
        pr_dirs = set()
        for fname in pr_meta['files']:
            for p in Path(fname).parents:
                if p in dirs and p not in pr_dirs:
                    pr_dirs.add(p)
        pr_meta.pop('files')
        pr_meta['dirs'] = list(pr_dirs)
        if pr_dirs:
            yield pr_meta


def print_prs(root, prs):
    table = Table(title="Pull requests %s" % root.name)
    table.add_column("PR")
    table.add_column("Author")
    table.add_column("Created")
    table.add_column("Title")

    for pr_meta in prs:
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
    except:  # noqa
        import sys, pdb, traceback  # noqa

        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])
