# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import subprocess
import tempfile
from unittest import TestCase

import boto3


class TestQuickstart(TestCase):


    def run_custodian(self, policy):
        tempdir = tempfile.mkdtemp()
        f = tempfile.NamedTemporaryFile(suffix='-custodian.yml', dir=tempdir)
        filepath = os.path.join(tempdir, f.name)
        open(filepath, 'w+').write(policy)
        cmd = 'custodian run -c {} -s {}'.format(filepath, tempdir),
        subprocess.call(cmd, shell=True)


    def test_example_works(self):

        # setup
        api = boto3.client('ec2')
        instance_id = api.run_instances(
            ImageId='ami-1e299d7e',
            InstanceType='t2.micro',
            MinCount=1,
            MaxCount=1,
        )['Instances'][0]['InstanceId']

        ec2 = boto3.resource('ec2')
        instance = ec2.Instance(instance_id)
        instance.wait_until_exists()
        instance.create_tags(Tags=[{'Key': 'Custodian', 'Value': ''}])
        instance.wait_until_running()

        # test
        self.run_custodian('''
            policies:
              - name: my-first-policy
                resource: ec2
                filters:
                  - "tag:Custodian": present
                actions:
                  - stop
        ''')
        instance.wait_until_stopped()

        # teardown
        instance.terminate()
