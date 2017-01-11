# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import json
import os
import subprocess
import tempfile
from unittest import TestCase

import boto3


def load_images_for_region(region):
    # Uses a catalog downloaded from:
    #   http://cloud-images.ubuntu.com/releases/streams/v1/
    ourdir = os.path.join(os.path.dirname(__file__))
    filename = os.path.join(ourdir, 'com.ubuntu.cloud:released:aws.json')
    products = json.load(open(filename))['products']
    product_id = sorted(products.keys())[-1]
    versions = products[product_id]['versions']
    version_id = sorted(versions.keys())[-1]
    items = versions[version_id]['items'].items()
    return sorted(v for k,v in items if v['crsn'] == region)


class TestQuickstart(TestCase):


    def run_custodian(self, policy):
        tempdir = tempfile.mkdtemp()
        f = tempfile.NamedTemporaryFile(suffix='-custodian.yml', dir=tempdir)
        filepath = os.path.join(tempdir, f.name)
        open(filepath, 'w+').write(policy)
        cmd = 'custodian run -c {} -s {}'.format(filepath, tempdir),
        subprocess.call(cmd, shell=True)


    def test_example_works(self):

        session = boto3.session.Session()

        # find an AMI
        images_for_region = load_images_for_region(session.region_name)
        images = [i for i in images_for_region if i['virt'] == 'hvm']
        assert images, "No suitable AMIs available"
        image_id = images[0]['id']

        # setup
        api = session.client('ec2')
        instance_id = api.run_instances(
            ImageId=image_id,
            InstanceType='t2.nano',
            MinCount=1,
            MaxCount=1,
        )['Instances'][0]['InstanceId']

        ec2 = session.resource('ec2')
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
