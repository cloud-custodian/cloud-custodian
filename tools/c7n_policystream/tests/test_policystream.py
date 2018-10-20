
import json
import subprocess
import os

import pygit2

from c7n.testing import TestUtils

DEFAULT_CONFIG = """\
[user]
email = "policyauthor@example.com"
name = "WatchFolk"
"""


class GitRepo(object):

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
        return pygit2.discover_repository(self.repo_path)

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


class StreamTest(TestUtils):

    def test_stream_basic(self):
        self.git = GitRepo(self.get_temp_dir())
        self.git.init()
        self.git.change('example.yml', {'policies': []})
        self.git.commit('init')
        self.git.change('example.yml', {
            'policies': [{
                'name': 'codebuild-check',
                'resource': 'aws.codebuild'}]})
        self.git.commit('add something')
        self.git.change('example.yml', {
            'policies': [{
                'name': 'lambda-check',
                'resource': 'aws.lambda'}]})
        self.git.commit('switch')
        
        
        
