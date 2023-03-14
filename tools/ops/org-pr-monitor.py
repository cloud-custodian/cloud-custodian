# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""Generate metrics for a Github org's pull request status hooks.

Monitoring CI tools, by tracking latency of status on a pull request,
and pending counts.

cat requirements.txt

click
dateparser
c7n
requests
"""
import click
import dateparser
from collections import Counter
from datetime import datetime
from dateutil.parser import parse as parse_date
from dateutil.tz import tzutc
import jmespath
import logging
import requests

from c7n.config import Bag
from c7n.credentials import SessionFactory
from c7n.resources.aws import MetricsOutput, DEFAULT_NAMESPACE
from c7n.utils import dumps

log = logging.getLogger('c7nops.cimetrics')


query = """
query($organization: String!) {
  organization(login: $organization) {
    repositories(first: 100, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes {
        name
        updatedAt
        pullRequests(states: OPEN, last: 10) {
          edges {
            node {
              commits(last: 1) {
                nodes {
                  commit {
                    authoredDate
                    committedDate
                    pushedDate
                    status {
                      contexts {
                        targetUrl
                        description
                        createdAt
                        context
                        state
                      }
                      state
                    }
                  }
                }
              }
              title
              updatedAt
            }
          }
        }
      }
    }
  }
}
"""


class RepoMetrics(MetricsOutput):

    BUF_SIZE = 1000
    dims = None

    def _default_dimensions(self):
        return self.dims or {}

    def _format_metric(self, key, value, unit, dimensions):
        d = {
            "MetricName": key,
            "Timestamp": self.get_timestamp(),
            "Value": value,
            'Dimensions': [],
            "Unit": unit}
        dimensions.update(self._default_dimensions())
        for k, v in dimensions.items():
            d['Dimensions'].append({"Name": k, "Value": v})
        return d

    def get_timestamp(self):
        return datetime.utcnow()


def process_commit(c, r, metrics, stats, since, now):
    # Find the oldest of the pr commit/dates
    # TODO find commit dates
    commit_date = parse_date(max(filter(
        None, (
            c['authoredDate'],
            c['committedDate'],
            c['pushedDate']))))

    if commit_date < since:
        return

    found = False
    for status_ctx in c['status']['contexts']:
        if status_ctx['context'] == metrics.dims['Hook']:
            status_time = parse_date(status_ctx['createdAt'])
            found = True
    if found:
        tdelta = (status_time - commit_date).total_seconds()
        metrics.put_metric('RepoHookLatency', tdelta, 'Seconds')
        stats['runtime'] += tdelta
        stats['count'] += 1
    else:
        stats['missing'] += 1
        stats['missing_time'] += (now - commit_date).total_seconds()


@click.group('status-metrics')
def cli():
    """github organization repository status hook metrics"""


@cli.command()
@click.option('--organization', envvar="GITHUB_ORG",
              required=True, help="Github Organization")
@click.option('--hook-context', envvar="GITHUB_HOOK",
              required=True, help="Webhook context name")
@click.option('--github-url', envvar="GITHUB_API_URL",
              default='https://api.github.com/graphql')
@click.option('--github-token', envvar='GITHUB_TOKEN',
              help="Github credential token")
@click.option('-v', '--verbose', help="Verbose output")
@click.option('-m', '--metrics', help="Publish metrics")
@click.option('--assume', help="Assume a role for publishing metrics")
@click.option('--region', help="Region to target for metrics")
@click.option('--since', help="Look at pull requests/commits younger than",
              default="1 week")
def run(organization, hook_context, github_url, github_token,
        verbose, metrics=False, since=None, assume=None, region=None):
    """scan org repo status hooks"""
    logging.basicConfig(level=logging.DEBUG)

    since = dateparser.parse(
        since, settings={
            'RETURN_AS_TIMEZONE_AWARE': True, 'TO_TIMEZONE': 'UTC'})

    headers = {"Authorization": "token {}".format(github_token)}

    response = requests.post(
        github_url, headers=headers,
        json={'query': query, 'variables': {'organization': organization}})

    result = response.json()

    if response.status_code != 200 or 'errors' in result:
        raise Exception(
            "Query failed to run by returning code of {}. {}".format(
                response.status_code, response.content))

    now = datetime.now(tzutc())
    stats = Counter()
    repo_metrics = RepoMetrics(
        Bag(session_factory=SessionFactory(region, assume_role=assume)),
        {'namespace': DEFAULT_NAMESPACE}
    )

    for r in result['data']['organization']['repositories']['nodes']:
        commits = jmespath.search(
            'pullRequests.edges[].node[].commits[].nodes[].commit[]', r)
        if not commits:
            continue
        log.debug("processing repo: %s prs: %d", r['name'], len(commits))
        repo_metrics.dims = {
            'Hook': hook_context,
            'Repo': '{}/{}'.format(organization, r['name'])}

        # Each commit represents a separate pr
        for c in commits:
            process_commit(c, r, repo_metrics, stats, since, now)

    repo_metrics.dims = None

    if stats['missing']:
        repo_metrics.put_metric(
            'RepoHookPending', stats['missing'], 'Count',
            Hook=hook_context)
        repo_metrics.put_metric(
            'RepoHookLatency', stats['missing_time'], 'Seconds',
            Hook=hook_context)

    if not metrics:
        print(dumps(repo_metrics.buf, indent=2))
        return
    else:
        repo_metrics.BUF_SIZE = 20
        repo_metrics.flush()


if __name__ == '__main__':
    try:
        cli()
    except Exception:
        import traceback, sys, pdb
        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])
