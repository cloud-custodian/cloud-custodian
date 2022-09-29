import click


from c7n.loader import DirectoryLoader
from c7n.config import Config

# from .output import report_outputs
from .provider import ResultSet


@click.group()
def cli():
    """Shift Left Policy"""


@cli.command()
@click.option("--format", default="terraform")
@click.option("-p", "--policy-dir", type=click.Path())
@click.option("-d", "--directory", type=click.Path())
@click.option("-o", "--output", type=click.Path())
def run(format, policy_dir, directory, output):
    """evaluate policies against iaac sources"""
    loader = DirectoryLoader(Config.empty(source_dir=directory))
    policies = loader.load_directory(policy_dir)
    # reporter = report_outputs.select()
    all_results = ResultSet()

    for p in policies:
        p.expand_variables(p.get_variables())
        p.validate()
        results = p()
        if results:
            all_results += results

    # reporter.report(all_results)


if __name__ == "__main__":
    try:
        cli()
    except Exception:
        import pdb, sys, traceback

        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])
