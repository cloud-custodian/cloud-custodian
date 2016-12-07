# Copyright 2016 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import json
import os
import sys

from c7n.mu import (
    CloudWatchEventSource,
    LambdaFunction,
    LambdaManager,
    PythonPackageArchive)


entry_source = """\
import logging
logging.root.setLevel(logging.DEBUG)

from c7n_mailer import handle

def dispatch(event, context):
    return handle.run(event, context)
"""


def get_archive(config):

    required = ['ldap', 'jinja2', 'markupsafe']
    remove = ['_yaml.so', 'c7n.egg-link']

    def lib_filter(root, dirs, files):
        for f in tuple(files):
            if f.endswith('.pyo'):
                files.remove(f)
        for r in remove:
            if r in files:
                files.remove(r)

        if os.path.basename(root) == 'site-packages':
            for n in tuple(dirs):
                if n not in required:
                    dirs.remove(n)
        return dirs, files

    archive = PythonPackageArchive(
        os.path.dirname(__file__),
        skip='*.pyc',
        lib_filter=lib_filter)

    archive.create()

    template_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', 'msg-templates'))

    for t in os.listdir(template_dir):
        with open(os.path.join(template_dir, t)) as fh:
            archive.add_contents('msg-templates/%s' % t, fh.read())

    archive.add_contents('config.json', json.dumps(config))
    archive.add_contents('periodic.py', entry_source)

    archive.close()
    return archive


def provision(config, session_factory):
    func_config = dict(
        name='cloud-custodian-mailer',
        description='Cloud Custodian/Maid Mailer',
        handler='periodic.dispatch',
        runtime='python2.7',
        memory_size=config['memory'],
        timeout=config['timeout'],
        role=config['role'],
        subnets=config['subnets'],
        security_groups=config['security_groups'],
        events=[
            CloudWatchEventSource(
                {'type': 'periodic',
                 'schedule': 'rate(5 minutes)'},
                session_factory,
                prefix="")
        ])


    archive = get_archive(config)
    func = LambdaFunction(func_config, archive)
    manager = LambdaManager(session_factory)
    manager.publish(func)
