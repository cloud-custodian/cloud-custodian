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
#
# AWS resources to manage
#


def load_resources():
    import ami
    import acm
    import apigw
    import asg
    import awslambda
    import cache
    import cfn
    import cw
    import dynamodb
    import ebs
    import ec2
    import ecr
    import ecs
    import elb
    import emr
    import firehose
    import glacier
    import iam
    import kinesis
    import kms
    import redshift
    import rds
    import route53
    import s3
    import sns
    import sqs
    import vpc
