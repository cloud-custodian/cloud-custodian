# /// script
# dependencies = [
#   "click",
#   "ghapi",
#   "rich",
# ]
# ///

import click

from ghapi.all import GhApi
from fastcore import net
from rich.console import Console

console = Console()


@click.group()
def cli():
    """Clear out venv caches"""


@cli.command()
def clear():
    """Clear out github action cache virtualenvs"""
    api = GhApi(owner='cloud-custodian', repo='cloud-custodian')
    console.print('removing venv caches')
    page = api.actions.get_actions_cache_list(
        key='venv-',
    )
    for cache in page['actions_caches']:
        console.print(cache)
        try:
            api.actions.delete_actions_cache_by_key(
                owner='cloud-custodian', repo='cloud-custodian', key=cache['key']
            )
        except net.HTTP404NotFoundError:
            console.print('404')


if __name__ == '__main__':
    cli()
