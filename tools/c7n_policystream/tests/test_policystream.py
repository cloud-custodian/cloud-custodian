# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import json
import subprocess
import os
import yaml
import logging

import pytest

try:
    import pygit2
    import policystream
except ImportError:
    pygit2 = None


from click.testing import CliRunner
from c7n.testing import TestUtils


DEFAULT_CONFIG = """\
[user]
email = "policyauthor@example.com"
name = "WatchFolk"
"""


class GitRepo:

    def __init__(self, repo_path, git_config=None):
        self.repo_path = repo_path
        self.git_config = git_config or DEFAULT_CONFIG

    def init(self):
        subprocess.check_output(['git', 'init'], cwd=self.repo_path)
        with open(os.path.join(self.repo_path, '.git', 'config'), 'w') as fh:
            fh.write(self.git_config)

    def change(self, path, content, serialize=True):
        dpath = os.path.join(self.repo_path, os.path.dirname(path))
        if not os.path.exists(dpath):
            os.makedirs(dpath)

        target = os.path.join(self.repo_path, path)
        exists = os.path.exists(target)

        with open(target, 'w') as fh:
            if serialize:
                fh.write(json.dumps(content))
            else:
                fh.write(content)

        if not exists:
            subprocess.check_output(['git', 'add', path], cwd=self.repo_path)

    def rm(self, path):
        os.remove(os.path.join(self.repo_path, path))

    def repo(self):
        return pygit2.Repository(os.path.join(self.repo_path, '.git'))

    def move(self, src, tgt):
        subprocess.check_output(['git', 'mv', src, tgt], cwd=self.repo_path)

    def commit(self, msg, author=None, email=None):
        env = {}
        if author:
            env['GIT_AUTHOR_NAME'] = author
        if email:
            env['GIT_AUTHOR_EMAIL'] = email

        subprocess.check_output(
            ['git', 'commit', '-am', msg],
            cwd=self.repo_path, env=env)

    def checkout(self, branch, create=True):
        args = ['git', 'checkout']
        if create:
            args.append('-b')
        args.append(branch)
        subprocess.check_output(args, cwd=self.repo_path)


@pytest.mark.skipif(pygit2 is None, reason="pygit2 not installed")
class StreamTest(TestUtils):

    def setUp(self):
        self.maxDiff = None
        logging.getLogger("").setLevel(logging.DEBUG)

    def setup_basic_repo(self):
        git = GitRepo(self.get_temp_dir())
        git.init()
        git.change('example.yml', {'policies': []})
        git.commit('init')
        git.change('example.yml', {
            'policies': [{
                'name': 'codebuild-check',
                'resource': 'aws.codebuild'}]})
        git.commit('add something')
        git.change('example.yml', {
            'policies': [{
                'name': 'lambda-check',
                'resource': 'aws.lambda'}]})
        git.commit('switch')
        return git

    def test_cli_diff_master(self):
        git = self.setup_basic_repo()
        runner = CliRunner()
        result = runner.invoke(
            policystream.cli,
            ['diff', '-r', git.repo_path])
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(
            yaml.safe_load(result.stdout),
            {'policies': [
                {'name': 'lambda-check', 'resource': 'aws.lambda'}]})

    def test_cli_diff_branch(self):
        git = self.setup_basic_repo()
        git.checkout('pull-request')
        git.change('example.yml', {
            'policies': [
                {'name': 'lambda-check',
                 'resource': 'aws.lambda'},
                {'name': 'ec2-check',
                 'resource': 'aws.ec2'}]})
        git.commit('new stuff')
        runner = CliRunner()
        result = runner.invoke(
            policystream.cli,
            ['diff', '-r', git.repo_path])
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(
            yaml.safe_load(result.stdout),
            {'policies': [
                {'name': 'ec2-check', 'resource': 'aws.ec2'}]})

    def test_diff_subdir_policies(self):
        git = self.setup_basic_repo()
        git.change('subdir/notary.yml', {
            'policies': [
                {'resource': 'azure.vm',
                 'name': 'ornithopter'}]})
        git.commit('azure example')
        repo = git.repo()
        policy_repo = policystream.PolicyRepo(git.repo_path, repo)
        changes = [c.data() for c in policy_repo.delta_commits(
            repo.revparse_single('HEAD^'),
            repo.revparse_single('HEAD'))]
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['change'], 'add')
        self.assertEqual(changes[0]['commit']['message'].strip(), 'azure example')
        self.assertEqual(changes[0]['policy']['file'], 'subdir/notary.yml')
        self.assertEqual(changes[0]['policy']['data']['name'], 'ornithopter')

    def test_stream_basic(self):
        git = self.setup_basic_repo()
        policy_repo = policystream.PolicyRepo(git.repo_path, git.repo())
        changes = [c.data() for c in policy_repo.delta_stream(
            sort=pygit2.GIT_SORT_TOPOLOGICAL | pygit2.GIT_SORT_REVERSE)]
        self.assertEqual(len(changes), 3)
        self.assertEqual(
            [(c['change'],
              c['policy']['data']['name'],
              c['commit']['message'].strip()) for c in changes],
            [('add', 'codebuild-check', 'add something'),
             ('remove', 'codebuild-check', 'switch'),
             ('add', 'lambda-check', 'switch')])

    def test_cli_stream_basic(self):
        git = self.setup_basic_repo()
        runner = CliRunner()
        result = runner.invoke(
            policystream.cli,
            ['stream', '-r', git.repo_path, '-s', 'jsonline'])
        self.assertEqual(result.exit_code, 0)

        rows = [json.loads(l) for l in result.stdout.splitlines()]
        self.maxDiff = None
        self.assertEqual(len(rows), 3)
        self.assertEqual(
            list(sorted(rows[0].keys())),
            ['change', 'commit', 'policy', 'repo_uri'])
        self.assertEqual(
            [r['change'] for r in rows],
            ['add', 'remove', 'add'])
        self.assertEqual(
            rows[-1]['policy'],
            {'data': {'name': 'lambda-check', 'resource': 'aws.lambda'},
             'file': 'example.yml'})

    def test_stream_remove_file(self):
        git = self.setup_basic_repo()
        git.rm('example.yml')
        git.commit('remove file')

        policy_repo = policystream.PolicyRepo(git.repo_path, git.repo())
        changes = [c.data() for c in policy_repo.delta_stream(
            sort=pygit2.GIT_SORT_TOPOLOGICAL | pygit2.GIT_SORT_REVERSE)]
        self.assertEqual(
            [(c['change'],
              c['policy']['data']['name'],
              c['commit']['message'].strip()) for c in changes],
            [('add', 'codebuild-check', 'add something'),
             ('remove', 'codebuild-check', 'switch'),
             ('add', 'lambda-check', 'switch'),
             ('remove', 'lambda-check', 'remove file')])

    def test_stream_move_subdir(self):
        git = GitRepo(self.get_temp_dir())
        git.init()
        git.change('aws/ec2.yml', {'policies': [
            {'name': 'ec2-check',
             'resource': 'aws.ec2'}]})
        git.change('lambda.yml', {'policies': [
            {'name': 'lambda-check',
             'resource': 'aws.lambda'}]})
        git.commit('init')
        git.move('lambda.yml', 'aws/lambda.yml')
        git.change('aws/ec2.yml', {'policies': [
            {'name': 'ec2-check',
             'resource': 'aws.ec2'},
            {'name': 'ec2-ami-check',
             'resource': 'aws.ec2'}]})
        git.commit('move')
        git.rm('aws/ec2.yml')
        git.rm('aws/lambda.yml')
        git.change('aws/all.yml', {'policies': [
            {'name': 'lambda-check',
             'resource': 'aws.lambda'},
            {'name': 'ec2-check',
             'resource': 'aws.ec2'}]})
        git.commit('consolidate')
        policy_repo = policystream.PolicyRepo(git.repo_path, git.repo())
        changes = [c.data() for c in policy_repo.delta_stream(
            sort=pygit2.GIT_SORT_TOPOLOGICAL | pygit2.GIT_SORT_REVERSE)]
        self.assertEqual(
            {(c['change'],
              c['policy']['data']['name'],
              c['commit']['message'].strip()) for c in changes},
            {('add', 'ec2-check', 'init'),
             ('add', 'lambda-check', 'init'),
             ('add', 'ec2-ami-check', 'move'),
             ('moved', 'lambda-check', 'move'),
             ('remove', 'ec2-ami-check', 'consolidate'),
             ('moved', 'ec2-check', 'consolidate'),
             ('moved', 'lambda-check', 'consolidate')}
        )

    def test_stream_move_policy(self):
        git = self.setup_basic_repo()
        git.change('newfile.yml', {
            'policies': [{
                'name': 'ec2-check',
                'resource': 'aws.ec2'}]})
        git.commit('new file')
        git.rm('example.yml')
        git.change('newfile.yml', {
            'policies': [{
                'name': 'ec2-check',
                'resource': 'aws.ec2',
            }, {
                'name': 'lambda-check',
                'resource': 'aws.lambda'}]})
        git.commit('move policy')

        policy_repo = policystream.PolicyRepo(git.repo_path, git.repo())
        changes = [c.data() for c in policy_repo.delta_stream(
            sort=pygit2.GIT_SORT_TOPOLOGICAL | pygit2.GIT_SORT_REVERSE)]
        self.assertEqual(
            [(c['change'],
              c['policy']['data']['name'],
              c['commit']['message'].strip()) for c in changes],
            [('add', 'codebuild-check', 'add something'),
             ('remove', 'codebuild-check', 'switch'),
             ('add', 'lambda-check', 'switch'),
             ('add', 'ec2-check', 'new file'),
             ('moved', 'lambda-check', 'move policy')])
