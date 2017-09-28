# Copyright 2017 Capital One Services, LLC
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

from __future__ import absolute_import, division, print_function, unicode_literals


RESOURCE = {
            "Website": None,
            "Logging": {},
            "Name": "teapot",
            "Tags": [
                {
                    "Value": "418",
                    "Key": "Status"
                }
            ],
            "Notification": {
                "LambdaFunctionConfigurations": []
            },
            "Acl": {
                "Owner": {
                    "DisplayName": "teapot-owner",
                    "ID": "imalittleteapot"
                },
                "Grants": []
            },
            "Replication": None,
            "Location": {
                "LocationConstraint": None
            },
            "Policy": None,
            "CreationDate": "2016-10-21T18:47:14+00:00",
            "Lifecycle": {
                "Rules": [
                    {
                        "Status": "Enabled",
                        "Prefix": "",
                        "AbortIncompleteMultipartUpload": {
                            "DaysAfterInitiation": 1
                        },
                        "Expiration": {
                            "Days": 15
                        },
                        "ID": "dev-standard"
                    }
                ]
            },
            "Versioning": {}
        }

SQS_MESSAGE = {
    "account": "dev",
    "account_id": "123456789012",
    "region": "us-east-1",
    "action": {
        "to": [],
        "type": "notify",
        "transport": {
            "topic": "arn:aws:sns:us-east-1:123456789012:find-teapots",
            "type": "sns"
        }
    },
    "policy": {
        "resource": "s3",
        "name": "test-s3",
        "region": "us-east-1",
        "actions": [
            {
                "to": [],
                "type": "notify",
                "transport": {
                    "topic": "arn:aws:sns:us-east-1:123456789012:find-teapots",
                    "type": "sns"
                }
            }
        ]
    },
    "event": None,
    "resources": [RESOURCE]
}