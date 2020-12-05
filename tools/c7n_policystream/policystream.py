#!/usr/bin/env python3
#
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import click
import contextlib
from collections import deque
from datetime import datetime, timedelta
from dateutil.tz import tzoffset, tzutc
from dateutil.parser import parse
from fnmatch import fnmatch
from functools import partial, reduce
import jmespath
import json
import logging
import shutil
import operator
import os
import pygit2
import requests
import tempfile
import yaml

from c7n.config import Config
from c7n.credentials import SessionFactory
from c7n.policy import PolicyCollection as BaseCollection
from c7n.policy import Policy as BasePolicy
from c7n.resources import load_available
from c7n.utils import get_retry

import boto3

try:
    import sqlalchemy as rdb
    HAVE_SQLA = True
except ImportError:
    HAVE_SQLA = False

log = logging.getLogger('c7n.policystream')

EMPTY_TREE = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'


class TempDir:

    def __init__(self):
        self.path = None

    def open(self):
        self.path = tempfile.mkdtemp()
        return self

    def close(self):
        if not self.path:
            return
        shutil.rmtree(self.path)


class ChangeType:

    ADD = 1
    REMOVE = 2
    MODIFIED = 3
    MOVED = 4


SORT_TYPE = {
    'topo': pygit2.GIT_SORT_TOPOLOGICAL,
    'time': pygit2.GIT_SORT_TIME,
    'reverse': pygit2.GIT_SORT_REVERSE
}

CHANGE_TYPE = {
    1: 'ADD',
    2: 'REMOVE',
    3: 'MODIFIED',
    4: 'MOVED'
}

GIT_DELTA = {
    0: 'GIT_DELTA_UNMODIFIED',
    1: 'GIT_DELTA_ADDED',
    2: 'GIT_DELTA_DELETED',
    3: 'GIT_DELTA_MODIFIED',
    4: 'GIT_DELTA_RENAMED',
    5: 'GIT_DELTA_COPIED',
    6: 'GIT_DELTA_IGNORED',
    7: 'GIT_DELTA_UNTRACKED',
    8: 'GIT_DELTA_TYPECHANGE',
    9: 'GIT_DELTA_UNREADABLE'}

GIT_DELTA_INVERT = {v: k for k, v in GIT_DELTA.items()}


class PolicyChange:
    """References a policy change within a given commit.
    """

    def __init__(self, policy, repo_uri, commit, change, previous=None):
        self.policy = policy
        self.repo_uri = repo_uri
        self.commit = commit
        self.kind = change
        self.previous = previous

    @property
    def file_path(self):
        return self.policy.file_path

    @property
    def date(self):
        return commit_date(self.commit)

    def __repr__(self):

        return "<policy-{} policy:{} provider:{} resource:{} date:{} author:{} commit:{}>".format(
            CHANGE_TYPE[self.kind].lower(),
            self.policy.name,
            self.policy.provider_name,
            self.policy.resource_type,
            self.date.isoformat(),
            self.commit.author.name,
            str(self.commit.id)[:6])

    def data(self, indent=2):
        d = {
            'change': CHANGE_TYPE[self.kind].lower(),
            'repo_uri': self.repo_uri,
            'policy': {
                'data': dict(self.policy.data),
                'file': self.policy.file_path,
            },
            'commit': {
                'id': str(self.commit.id),
                'message': self.commit.message,
                'author': str(self.commit.author.name),
                'email': str(self.commit.author.email),
                'date': self.date.isoformat(),
            }
        }
        if self.previous:
            d['previous'] = {
                'data': dict(self.previous.data),
                'file': self.previous.file_path}
        return d


class CollectionDelta:
    """Iterator over changes between two policy collections.

    With a given by url associated to a give commit.
    """

    change = PolicyChange

    def __init__(self, prev, curr, commit=None, repo_uri=None):
        self.prev = prev
        self.curr = curr
        self.commit = commit
        self.repo_uri = repo_uri

    def delta(self):
        removed = set(self.prev.keys()) - set(self.curr.keys())
        added = set(self.curr.keys()) - set(self.prev.keys())

        for r in removed:
            yield PolicyChange(self.prev[r], self.repo_uri, self.commit, ChangeType.REMOVE)

        for a in added:
            yield PolicyChange(self.curr[a], self.repo_uri, self.commit, ChangeType.ADD)

        for extant in set(self.curr.keys()).intersection(set(self.prev.keys())):
            if self.curr[extant].data != self.prev[extant].data:
                yield PolicyChange(
                    self.curr[extant], self.repo_uri, self.commit,
                    ChangeType.MODIFIED, self.prev[extant])
            elif self.curr[extant].file_path != self.prev[extant].file_path:
                yield PolicyChange(
                    self.curr[extant], self.repo_uri, self.commit,
                    ChangeType.MOVED, self.prev[extant])


class Policy(BasePolicy):
    """Policy that tracks its file origin."""
    def __init__(self, data, options, file_path):
        self.file_path = file_path
        self.data = data
        self.options = options


class PolicyCollection(BaseCollection):
    """Policy collection supporting collection modifications."""

    policy_class = Policy

    def __init__(self, policies=None, options=None):
        self.policies = policies or []
        self.options = options or Config.empty()
        self.pmap = {p.name: p for p in self.policies}

    def __getitem__(self, key):
        return self.pmap[key]

    def __repr__(self):
        return "<PolicyCollection count:%d>" % (len(self.policies))

    def select(self, names):
        """return the named subset of policies"""
        return PolicyCollection(
            [p for p in self.policies if p.name in names], self.options)

    def add(self, p):
        assert p.name not in self.pmap
        self.policies.append(p)
        self.pmap[p.name] = p

    def remove(self, p):
        assert p.name in self.pmap
        self.policies = [ep for ep in self.policies if ep.name != p.name]
        del self.pmap[p.name]

    def __setitem__(self, key, p):
        assert p.name in self.pmap
        self.pmap[p.name] = p
        for idx, ep in enumerate(self.policies):
            if p.name == ep.name:
                self.policies[idx] = p

    def keys(self):
        return self.pmap.keys()

    @classmethod
    def from_data(cls, data, options, file_path):
        policies = [
            cls.policy_class(p, options, file_path)
            for p in data.get('policies', ())]
        return cls(policies, options)


def commit_date(commit):
    tzinfo = tzoffset(None, timedelta(minutes=commit.author.offset))
    return datetime.fromtimestamp(float(commit.author.time), tzinfo)


def policy_path_matcher(path):
    if (path.endswith('.yaml') or path.endswith('.yml')) and not path.startswith('.'):
        return True


class PolicyRepo:
    """Models a git repository containing policy files.
    """
    def __init__(self, repo_uri, repo, matcher=None):
        self.repo_uri = repo_uri
        self.repo = repo
        self.policy_files = {}
        self.matcher = matcher or policy_path_matcher

    def initialize_tree(self, tree):
        assert not self.policy_files

        for tree_ent in tree:
            fpath = tree_ent.name
            if not self.matcher(fpath):
                continue
            self.policy_files[fpath] = PolicyCollection.from_data(
                yaml.safe_load(self.repo.get(tree[fpath].id).data),
                Config.empty(), fpath)

    def _get_policy_fents(self, tree):
        # get policy file entries from a tree recursively
        results = {}
        q = deque([(tree, '')])
        while q:
            t, prefix = q.popleft()
            for fent in t:
                if fent.type == pygit2.GIT_OBJ_TREE:
                    q.append((
                        self.repo.get(fent.id),
                        os.path.join(prefix, fent.name)))
                elif self.matcher(fent.name):
                    results[os.path.join(prefix, fent.name)] = fent
        return results

    def delta_commits(self, baseline, target):
        """Show policies changes between arbitrary commits.

        The common use form is comparing the heads of two branches.
        """
        baseline_files = self._get_policy_fents(baseline.tree)
        target_files = self._get_policy_fents(target.tree)

        baseline_policies = PolicyCollection()
        target_policies = PolicyCollection()

        # Added
        for f in set(target_files) - set(baseline_files):
            target_policies += self._policy_file_rev(f, target)

        # Removed
        for f in set(baseline_files) - set(target_files):
            baseline_policies += self._policy_file_rev(f, baseline)

        # Modified
        for f in set(baseline_files).intersection(target_files):
            if baseline_files[f].hex == target_files[f].hex:
                continue
            target_policies += self._policy_file_rev(f, target)
            baseline_policies += self._policy_file_rev(f, baseline)

        return CollectionDelta(
            baseline_policies, target_policies, target, self.repo_uri).delta()

    def delta_stream(self, target='HEAD', limit=None,
                     sort=pygit2.GIT_SORT_TIME | pygit2.GIT_SORT_REVERSE,
                     after=None, before=None):
        """Return an iterator of policy changes along a commit lineage in a repo.
        """
        if target == 'HEAD':
            target = self.repo.head.target

        commits = []
        for commit in self.repo.walk(target, sort):
            cdate = commit_date(commit)
            log.debug(
                "processing commit id:%s date:%s parents:%d msg:%s",
                str(commit.id)[:6], cdate.isoformat(),
                len(commit.parents), commit.message)
            if after and cdate > after:
                continue
            if before and cdate < before:
                continue
            commits.append(commit)
            if limit and len(commits) > limit:
                break

        if limit:
            self.initialize_tree(commits[limit].tree)
            commits.pop(-1)

        for commit in commits:
            for policy_change in self._process_stream_commit(commit):
                yield policy_change

    def _policy_file_rev(self, f, commit):
        try:
            return self._validate_policies(
                PolicyCollection.from_data(
                    yaml.safe_load(self.repo.get(commit.tree[f].id).data),
                    Config.empty(), f))
        except Exception as e:
            log.warning(
                "invalid policy file %s @ %s %s %s \n error:%s",
                f, str(commit.id)[:6], commit_date(commit).isoformat(),
                commit.author.name, e)
            return PolicyCollection()

    def _validate_policies(self, policies):
        res = []
        for p in policies:
            try:
                p.resource_type
                p.name
            except KeyError:
                continue
            res.append(p)
        return PolicyCollection(res)

    def _process_stream_commit(self, change):
        if not change.parents:
            change_diff = self.repo.diff(self.repo.get(EMPTY_TREE, change), change)
        else:
            change_diff = self.repo.diff(change.parents[0], change)

        log.debug(
            "processing commit id:%s date:%s parents:%d add:%d del:%d files:%d change:%s",
            str(change.id)[:6], commit_date(change).isoformat(), len(change.parents),
            change_diff.stats.insertions,
            change_diff.stats.deletions,
            change_diff.stats.files_changed,
            change.message.strip())

        change_policies = PolicyCollection()
        current_policies = PolicyCollection()
        removed = set()

        for delta in change_diff.deltas:
            f = delta.new_file.path
            if not self.matcher(f):
                continue
            elif delta.status == GIT_DELTA_INVERT['GIT_DELTA_ADDED']:
                change_policies += self._policy_file_rev(f, change)
                if f in self.policy_files:
                    current_policies += self.policy_files[f]
            elif delta.status == GIT_DELTA_INVERT['GIT_DELTA_MODIFIED']:
                change_policies += self._policy_file_rev(f, change)
                if f in self.policy_files:
                    current_policies += self.policy_files[f]
            elif delta.status == GIT_DELTA_INVERT['GIT_DELTA_DELETED']:
                if f in self.policy_files:
                    # if the policies were moved, only add in policies
                    # that are not already accounted for.
                    current_policies += self.policy_files[f].select(
                        set(current_policies.keys()).difference(
                            self.policy_files[f].keys()))
                    removed.add(f)
            elif delta.status == GIT_DELTA_INVERT['GIT_DELTA_RENAMED']:
                change_policies += self._policy_file_rev(f, change)
                current_policies += self.policy_files[delta.old_file.path]
                removed.add(delta.old_file.path)
            else:
                log.info(
                    "unhandled delta type:%s path:%s commit_id:%s",
                    GIT_DELTA[delta.status], delta.new_file.path, change.id)
                continue

        for change in self._process_stream_delta(CollectionDelta(
                current_policies, change_policies, change, self.repo_uri).delta()):
            yield change

        for r in removed:
            del self.policy_files[r]

    def _process_stream_delta(self, delta_stream):
        """Bookkeeping on internal data structures while iterating a stream."""
        for pchange in delta_stream:
            if pchange.kind == ChangeType.ADD:
                self.policy_files.setdefault(
                    pchange.file_path, PolicyCollection()).add(pchange.policy)
            elif pchange.kind == ChangeType.REMOVE:
                self.policy_files[pchange.file_path].remove(pchange.policy)
            elif pchange.kind in (ChangeType.MOVED, ChangeType.MODIFIED):
                if pchange.policy.file_path != pchange.previous.file_path:
                    self.policy_files[pchange.previous.file_path].remove(pchange.previous)
                    if (pchange.policy.file_path in self.policy_files and
                            pchange.policy.name in self.policy_files[pchange.file_path]):
                        self.policy_files[pchange.file_path][pchange.policy.name] = pchange.policy
                    else:
                        self.policy_files.setdefault(
                            pchange.file_path, PolicyCollection()).add(pchange.policy)
                else:
                    self.policy_files[pchange.file_path][pchange.policy.name] = pchange.policy
            yield pchange


def parse_arn(arn):
    # http://docs.aws.amazon.com/general/latest/gr/aws-arns-and-namespaces.html
    elements = arn.split(':', 5)
    result = {
        'arn': elements[0],
        'partition': elements[1],
        'service': elements[2],
        'region': elements[3],
        'account': elements[4],
        'resource': elements[5],
        'resource_type': None
    }
    if '/' in result['resource']:
        result['resource_type'], result['resource'] = result['resource'].split('/', 1)
    elif ':' in result['resource']:
        result['resource_type'], result['resource'] = result['resource'].split(':', 1)
    return result


class Transport:

    BUF_SIZE = 1

    def __init__(self, session, info):
        self.session = session
        self.info = info
        self.buf = []

    def send(self, change):
        """send the given policy change"""
        self.buf.append(change)
        if len(self.buf) % self.BUF_SIZE == 0:
            self.flush()

    def flush(self):
        """flush any buffered messages"""
        buf = self.buf
        self.buf = []
        if buf:
            self._flush(buf)

    def close(self):
        self.flush()


class KinesisTransport(Transport):

    BUF_SIZE = 50

    retry = staticmethod(get_retry(('ProvisionedThroughputExceededException',)))

    def __init__(self, session, info):
        super(KinesisTransport, self).__init__(session, info)
        self.client = self.session.client('kinesis', region_name=info['region'])

    def _flush(self, buf):
        self.retry(
            self.client.put_records,
            StreamName=self.info['resource'],
            Records=[
                {'Data': json.dumps(c.data()),
                 'PartitionKey': c.repo_uri}
                for c in buf])


class IndexedTransport(Transport):
    """marker denoting transports that support querying for last seen value"""

    def last(self):
        raise NotImplementedError()


class SQLTransport(IndexedTransport):

    BUF_SIZE = 200

    def __init__(self, session, info):
        super(SQLTransport, self).__init__(session, info)
        self.metadata = rdb.MetaData()
        self.table = rdb.Table(
            'policy_changes', self.metadata,
            rdb.Column('commit_id', rdb.String(32), primary_key=True),
            rdb.Column('policy_name', rdb.String(256), primary_key=True),
            rdb.Column('resource_type', rdb.String(32)),
            rdb.Column('change_type', rdb.String(8)),
            rdb.Column('commit_date', rdb.DateTime()),
            rdb.Column('committer_name', rdb.String(128)),
            rdb.Column('committer_email', rdb.String(64)),
            rdb.Column('repo_uri', rdb.String(384)),
            rdb.Column('repo_file', rdb.String(1024)),
            rdb.Column('commit_msg', rdb.String(4096)),
            rdb.Column('policy', rdb.Text())
        )
        self.engine = rdb.create_engine(info['db_uri'])
        self.metadata.bind = self.engine
        self.metadata.create_all()
        self.conn = self.engine.connect()

    def _flush(self, buf):
        with self.conn.begin():
            self.conn.execute(
                self.table.insert(),
                [dict(
                    commit_id=str(c.commit.id),
                    policy_name=c.policy.name,
                    resource_type=c.policy.resource_type,
                    change_type=c.kind,
                    commit_date=c.date,
                    committer_name=c.commit.committer.name,
                    committer_email=c.commit.committer.email,
                    repo_uri=c.repo_uri,
                    repo_file=c.file_path,
                    commit_msg=c.commit.message,
                    policy=json.dumps(c.policy.data))
                 for c in buf])

    def last(self):
        value = self.conn.execute(
            'select max(commit_date) from policy_changes').fetchone()[0]
        if not value:
            return None
        if isinstance(value, str):
            last_seen = parse(value)
            last_seen = last_seen.replace(tzinfo=tzutc())
        return last_seen

    def close(self):
        super(SQLTransport, self).close()
        self.conn.close()


class SQSTransport(Transport):

    BUF_SIZE = 10

    def __init__(self, session, info):
        super(SQSTransport, self).__init__(session, info)
        self.client = self.session.client('sqs', region_name=info['region'])

    def _flush(self, buf):
        self.client.send_message_batch(
            QueueUrl=self.info['resource'],
            Entries=[{
                'Id': str(change.commit.id) + change.policy.name,
                'MessageDeduplicationId': str(change.commit.id) + change.policy.name,
                'MessageGroupId': change.repo_uri,
                'MessageBody': json.dumps(change.data())}
                for change in buf])


class OutputTransport(Transport):

    def send(self, change):
        if self.info.get('format', '') == 'jsonline':
            print(json.dumps(change.data(), indent=None))
        else:
            print(change)


def transport(stream_uri, assume):
    if stream_uri == 'stdout':
        return OutputTransport(None, {})
    elif stream_uri == 'jsonline':
        return OutputTransport(None, {'format': 'jsonline'})
    if (stream_uri.startswith('sqlite') or
            stream_uri.startswith('postgresql') or
            stream_uri.startswith('mysql')):
        if not HAVE_SQLA:
            raise ValueError("missing dependency sqlalchemy")
        return SQLTransport(None, {'db_uri': stream_uri})
    if not stream_uri.startswith('arn'):
        raise ValueError("invalid transport")
    info = parse_arn(stream_uri)
    session_factory = boto3.Session
    if assume:
        session_factory = partial(SessionFactory, assume_role=assume)
    if info['service'] == 'kinesis':
        return KinesisTransport(session_factory(), info)
    elif info['service'] == 'sqs':
        qurl = "https://sqs.{region}.amazonaws.com/{account}/{resource}".format(**info)
        info['resource'] = qurl
        return SQSTransport(session_factory(), info)

    raise ValueError("unsupported transport %s" % stream_uri)


@click.group()
def cli():
    """Policy changes from git history"""


query = """
query($organization: String!, $cursor: String) {
  organization(login: $organization) {
    repositories(first: 100, after: $cursor, orderBy: {field: UPDATED_AT, direction: DESC}){
      edges {
        node {
          name
          url
          createdAt
        }
      }
      pageInfo {
        endCursor
        hasNextPage
      }
    }
  }
}
"""


def github_repos(organization, github_url, github_token):
    """Return all github repositories in an organization."""
    # Get github repos
    headers = {"Authorization": "token {}".format(github_token)}
    next_cursor = None

    while next_cursor is not False:
        params = {'query': query, 'variables': {
            'organization': organization, 'cursor': next_cursor}}
        response = requests.post(github_url, headers=headers, json=params)
        result = response.json()
        if response.status_code != 200 or 'errors' in result:
            raise ValueError("Github api error %s" % (
                response.content.decode('utf8'),))

        repos = jmespath.search(
            'data.organization.repositories.edges[].node', result)
        for r in repos:
            yield r
        page_info = jmespath.search(
            'data.organization.repositories.pageInfo', result)
        if page_info:
            next_cursor = (page_info['hasNextPage'] and
                           page_info['endCursor'] or False)
        else:
            next_cursor = False


@cli.command(name='org-stream')
@click.option('--organization', envvar="GITHUB_ORG",
              required=True, help="Github Organization")
@click.option('--github-url', envvar="GITHUB_API_URL",
              default='https://api.github.com/graphql')
@click.option('--github-token', envvar='GITHUB_TOKEN',
              help="Github credential token")
@click.option('-v', '--verbose', default=False, help="Verbose", is_flag=True)
@click.option('-d', '--clone-dir', help="Local directory to checkout repos to")
@click.option('-f', '--filter', multiple=True, help="glob for repositories within org to include")
@click.option('-e', '--exclude', multiple=True, help="glob for repository within org to exclude")
@click.option('-s', '--stream-uri', default="stdout",
              help=("Destination stream for logical changes "
                    "(default stdout supports jsonline/kinesis/sqs/sqlalchemy)"))
@click.option('--assume', '--assume',
              help="Assume role for cloud stream destinations")
@click.pass_context
def org_stream(ctx, organization, github_url, github_token, clone_dir,
               verbose, filter, exclude, stream_uri, assume):
    """Stream changes for repos in a GitHub organization.
    """
    logging.basicConfig(
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s",
        level=(verbose and logging.DEBUG or logging.INFO))

    log.info("Checkout/Update org repos")
    repos = ctx.invoke(
        org_checkout,
        organization=organization,
        github_url=github_url,
        github_token=github_token,
        clone_dir=clone_dir,
        verbose=verbose,
        filter=filter,
        exclude=exclude)

    log.info('Streaming org changes')
    change_count = 0
    for r in repos:
        change_count += ctx.invoke(
            stream,
            repo_uri=r,
            stream_uri=stream_uri,
            verbose=verbose,
            assume=assume)
    log.info("Streamed %d org changes", change_count)


@cli.command(name='org-checkout')
@click.option('--organization', envvar="GITHUB_ORG",
              required=True, help="Github Organization")
@click.option('--github-url', envvar="GITHUB_API_URL",
              default='https://api.github.com/graphql')
@click.option('--github-token', envvar='GITHUB_TOKEN',
              help="Github credential token")
@click.option('-v', '--verbose', default=False, help="Verbose", is_flag=True)
@click.option('-d', '--clone-dir')
@click.option('-f', '--filter', multiple=True)
@click.option('-e', '--exclude', multiple=True)
def org_checkout(organization, github_url, github_token, clone_dir,
                 verbose, filter, exclude):
    """Checkout repositories from a GitHub organization."""
    logging.basicConfig(
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s",
        level=(verbose and logging.DEBUG or logging.INFO))

    callbacks = pygit2.RemoteCallbacks(
        pygit2.UserPass(github_token, 'x-oauth-basic'))

    repos = []
    for r in github_repos(organization, github_url, github_token):
        if filter:
            found = False
            for f in filter:
                if fnmatch(r['name'], f):
                    found = True
                    break
            if not found:
                continue

        if exclude:
            found = False
            for e in exclude:
                if fnmatch(r['name'], e):
                    found = True
                    break
            if found:
                continue

        repo_path = os.path.join(clone_dir, r['name'])
        repos.append(repo_path)
        if not os.path.exists(repo_path):
            log.debug("Cloning repo: %s/%s" % (organization, r['name']))
            repo = pygit2.clone_repository(
                r['url'], repo_path, callbacks=callbacks)
        else:
            repo = pygit2.Repository(repo_path)
            if repo.status():
                log.warning('repo %s not clean skipping update')
                continue
            log.debug("Syncing repo: %s/%s" % (organization, r['name']))
            pull(repo, callbacks)
    return repos


def pull(repo, creds, remote_name='origin', branch='master'):
    found = False
    for remote in repo.remotes:
        if remote.name != remote_name:
            continue
        found = True
        break

    if not found:
        return

    # from https://github.com/MichaelBoselowitz/pygit2-examples/blob/master/examples.py
    # License MIT Copyright (c) 2015 Michael Boselowitz
    remote.fetch(callbacks=creds)
    remote_master_id = repo.lookup_reference('refs/remotes/origin/%s' % branch).target
    merge_result, _ = repo.merge_analysis(remote_master_id)
    # Up to date, do nothing
    if merge_result & pygit2.GIT_MERGE_ANALYSIS_UP_TO_DATE:
        return
    # We can just fastforward
    elif merge_result & pygit2.GIT_MERGE_ANALYSIS_FASTFORWARD:
        repo.checkout_tree(repo.get(remote_master_id))
        try:
            master_ref = repo.lookup_reference('refs/heads/%s' % (branch))
            master_ref.set_target(remote_master_id)
        except KeyError:
            repo.create_branch(branch, repo.get(remote_master_id))
        repo.head.set_target(remote_master_id)
    elif merge_result & pygit2.GIT_MERGE_ANALYSIS_NORMAL:
        log.warning("Local commits, repo %s must be manually synced", repo)


@cli.command(name='diff')
@click.option('-r', '--repo-uri', help="Path/Url to git repository")
@click.option('--source', default=None, help="source/baseline revision spec")
@click.option('--target', default=None, help="target revision spec")
@click.option('-o', '--output', type=click.File('wb'), default='-')
@click.option('-v', '--verbose', default=False, help="Verbose", is_flag=True)
def diff(repo_uri, source, target, output, verbose):
    """Policy diff between two arbitrary revisions.

    Revision specifiers for source and target can use fancy git refspec syntax
    for symbolics, dates, etc.

    See: https://git-scm.com/book/en/v2/Git-Tools-Revision-Selection

    Default revision selection is dependent on current working tree
    branch. The intent is for two use cases, if on a non-master branch
    then show the diff to master.  If on master show the diff to
    previous commit on master. For repositories not using the
    `master` convention, please specify explicit source and target.
    """
    logging.basicConfig(
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s",
        level=(verbose and logging.DEBUG or logging.INFO))
    logging.getLogger('botocore').setLevel(logging.WARNING)

    if repo_uri is None:
        repo_uri = pygit2.discover_repository(os.getcwd())

    repo = pygit2.Repository(repo_uri)
    load_available()

    # If on master show diff between last commit to current head
    if repo.head.shorthand == 'master':
        if source is None:
            source = 'HEAD^1'
        if target is None:
            target = 'master'
    # Else show difference between master and current head
    elif target is None:
        target = repo.head.shorthand
    if source is None:
        source = 'master'

    policy_repo = PolicyRepo(repo_uri, repo)
    changes = list(policy_repo.delta_commits(
        repo.revparse_single(source), repo.revparse_single(target)))
    output.write(
        yaml.safe_dump({
            'policies': [c.policy.data for c in changes
                         if c.kind != ChangeType.REMOVE]}).encode('utf8'))


@cli.command()
@click.option('-r', '--repo-uri', help="Path/Url to git repository")
@click.option(
    '-s', '--stream-uri', default="stdout",
    help=("Destination stream for logical changes "
          "(supports stdout/jsonline/kinesis/sqs/sqlalchemy)"))
@click.option('-v', '--verbose', default=False, help="Verbose", is_flag=True)
@click.option('--assume', help="Role assumption for AWS stream outputs")
@click.option('--before', help="Only stream commits before given date")
@click.option('--after', help="Only stream commits after given date")
@click.option('--sort', multiple=True, default=["reverse", "time"],
              type=click.Choice(SORT_TYPE.keys()),
              help="Git sort ordering")
def stream(repo_uri, stream_uri, verbose, assume, sort, before=None, after=None):
    """Stream git history policy changes to destination.


    Default stream destination is a summary of the policy changes to stdout, one
    per line. Also supported for stdout streaming is `jsonline`.

    AWS Kinesis and SQS destinations are specified by providing the ARN.

    Database destinations are supported by providing a sqlalchemy DSN. Note
    SQLAlchemy and db drivers must be installed separately as they an optional
    dependency.

    When using database destinations, streaming defaults to incremental.
    """
    logging.basicConfig(
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s",
        level=(verbose and logging.DEBUG or logging.INFO))
    logging.getLogger('botocore').setLevel(logging.WARNING)

    if before:
        before = parse(before)
    if after:
        after = parse(after)
    if sort:
        sort = reduce(operator.or_, [SORT_TYPE[s] for s in sort])

    with contextlib.closing(TempDir().open()) as temp_dir:
        if repo_uri is None:
            repo_uri = pygit2.discover_repository(os.getcwd())
            log.debug("Using repository %s", repo_uri)
        if repo_uri.startswith('http') or repo_uri.startswith('git@'):
            log.info("Cloning repository: %s", repo_uri)
            repo = pygit2.clone_repository(repo_uri, temp_dir.path)
        else:
            repo = pygit2.Repository(repo_uri)
        load_available()
        policy_repo = PolicyRepo(repo_uri, repo)
        change_count = 0

        with contextlib.closing(transport(stream_uri, assume)) as t:
            if after is None and isinstance(t, IndexedTransport):
                after = t.last()
            for change in policy_repo.delta_stream(after=after, before=before):
                change_count += 1
                t.send(change)

        log.info("Streamed %d policy repo changes", change_count)
    return change_count


if __name__ == '__main__':
    try:
        cli()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        raise
    except: # NOQA
        import traceback, pdb, sys
        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])
