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
    import c7n.resources.account
    import c7n.resources.ami
    import c7n.resources.acm
    import c7n.resources.apigw
    import c7n.resources.appelb
    import c7n.resources.asg
    import c7n.resources.awslambda
    import c7n.resources.cfn
    import c7n.resources.cloudfront
    import c7n.resources.cw
    import c7n.resources.dynamodb
    import c7n.resources.ebs
    import c7n.resources.ec2
    import c7n.resources.ecr
    import c7n.resources.ecs
    import c7n.resources.efs
    import c7n.resources.elasticache
    import c7n.resources.elasticsearch
    import c7n.resources.elb
    import c7n.resources.emr
    import c7n.resources.glacier
    import c7n.resources.iam
    import c7n.resources.kinesis
    import c7n.resources.kms
    import c7n.resources.redshift
    import c7n.resources.rds
    import c7n.resources.rdscluster
    import c7n.resources.route53
    import c7n.resources.s3
    import c7n.resources.sns
    import c7n.resources.sqs
    import c7n.resources.vpc

    # Load external plugins (private sdks etc)
    from c7n.manager import resources
    resources.load_plugins()
