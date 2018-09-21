# Copyright 2015-2017 Capital One Services, LLC
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
#
# AWS resources to manage
#
from __future__ import absolute_import, division, print_function, unicode_literals

import time


LOADED = False


def load_resources():

    global LOADED
    if LOADED:
        return

    import c7n.resources.account
    import c7n.resources.acm
    import c7n.resources.ami
    import c7n.resources.apigw
    import c7n.resources.appelb
    import c7n.resources.asg
    import c7n.resources.awslambda
    import c7n.resources.batch
    import c7n.resources.cfn
    import c7n.resources.cloudfront
    import c7n.resources.cloudsearch
    import c7n.resources.cloudtrail
    import c7n.resources.code
    import c7n.resources.cognito
    import c7n.resources.config
    import c7n.resources.cw
    import c7n.resources.directory
    import c7n.resources.directconnect
    import c7n.resources.dms
    import c7n.resources.dynamodb
    import c7n.resources.datapipeline
    import c7n.resources.ebs
    import c7n.resources.ec2
    import c7n.resources.ecr
    import c7n.resources.ecs
    import c7n.resources.efs
    import c7n.resources.elasticache
    import c7n.resources.elasticbeanstalk
    import c7n.resources.elasticsearch
    import c7n.resources.elb
    import c7n.resources.eks
    import c7n.resources.emr
    import c7n.resources.gamelift
    import c7n.resources.glacier
    import c7n.resources.glue
    import c7n.resources.health
    import c7n.resources.hsm
    import c7n.resources.iam
    import c7n.resources.iot
    import c7n.resources.kinesis
    import c7n.resources.kms
    import c7n.resources.ml
    import c7n.resources.mq
    import c7n.resources.opsworks
    import c7n.resources.rds
    import c7n.resources.rdsparamgroup
    import c7n.resources.rdscluster
    import c7n.resources.redshift
    import c7n.resources.route53
    import c7n.resources.s3
    import c7n.resources.sagemaker
    import c7n.resources.secretsmanager
    import c7n.resources.sfn
    import c7n.resources.shield
    import c7n.resources.simpledb
    import c7n.resources.snowball
    import c7n.resources.sns
    import c7n.resources.storagegw
    import c7n.resources.sqs
    import c7n.resources.ssm
    import c7n.resources.support
    import c7n.resources.vpc
    import c7n.resources.waf

    # Load external plugins (private sdks etc)
    from c7n.manager import resources
    resources.load_plugins()
    resources.notify(resources.EVENT_FINAL)

    LOADED = True
