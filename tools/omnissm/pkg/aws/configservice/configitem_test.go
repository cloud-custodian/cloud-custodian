// Copyright 2018 Capital One Services, LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package configservice

import (
	"encoding/json"
	"testing"
)

var oversizedConfigurationItem = `{
    "account": "123456789012",
    "detail": {
        "configurationItemSummary": {
            "ARN": "arn:aws:ssm:us-east-1:123456789012:managed-instance-inventory/mi-1234567890123456",
            "awsAccountId": "123456789012",
            "awsRegion": "us-east-1",
            "changeType": "UPDATE",
            "configurationItemCaptureTime": "2018-05-17T06:31:40.400Z",
            "configurationItemStatus": "OK",
            "configurationItemVersion": "1.3",
            "configurationStateId": 1526538700400,
            "configurationStateMd5Hash": "",
            "resourceId": "mi-1234567890123456",
            "resourceType": "AWS::SSM::ManagedInstanceInventory"
        },
        "messageType": "OversizedConfigurationItemChangeNotification",
        "notificationCreationTime": "2018-05-17T06:31:41.245Z",
        "recordVersion": "1.0",
        "s3DeliverySummary": {
            "s3BucketLocation": "bucket/file.json.gz"
        }
    },
    "detail-type": "Config Configuration Item Change",
    "id": "11111111-2222-3333-4444-555555555555",
    "region": "us-east-1",
    "resources": [
        "arn:aws:ssm:us-east-1:123456789012:managed-instance-inventory/mi-1234567890123456"
    ],
    "source": "aws.config",
    "time": "2018-05-17T06:31:41Z",
    "version": "0"
}`

var configurationItemChange = `{
    "version": "0",
    "id": "11111111-2222-3333-4444-555555555555",
    "detail-type": "Config Configuration Item Change",
    "source": "aws.config",
    "account": "123456789012",
    "time": "2018-05-02T16:20:56Z",
    "region": "us-east-1",
    "resources": [
        "arn:aws:ec2:us-east-1:123456789012:instance/i-12345678901234567"
    ],
    "detail": {
        "recordVersion": "1.3",
        "messageType": "ConfigurationItemChangeNotification",
        "configurationItemDiff": {
            "changedProperties": {},
            "changeType": "CREATE"
        },
        "notificationCreationTime": "2018-05-02T16:20:56.017Z",
        "configurationItem": {
            "configuration": {
                "imageId": "ami-12345678",
                "instanceId": "i-12345678901234567",
				"platform": "Linux",
                "instanceType": "t2.small",
                "keyName": "my-key-name",
                "launchTime": "2018-05-02T16:18:05.000Z",
                "state": {
                    "code": 16,
                    "name": "running"
                },
                "subnetId": "subnet-12345678",
                "vpcId": "vpc-12345678",
                "iamInstanceProfile": {
                    "arn": "arn:aws:iam::123456789012:instance-profile/EC2InstanceProfileRole",
                    "id": "ABCDEFGHIJKLMNOPQSTUV"
                }
            },
            "supplementaryConfiguration": {},
            "tags": {
                "Name": "ec2-instance-name"
            },
            "configurationItemVersion": "1.3",
            "configurationItemCaptureTime": "2018-05-02T16:20:55.108Z",
            "configurationStateId": 1525278055108,
            "awsAccountId": "123456789012",
            "configurationItemStatus": "ResourceDiscovered",
            "resourceType": "AWS::EC2::Instance",
            "resourceId": "i-12345678901234567",
            "ARN": "arn:aws:ec2:us-east-1:123456789012:instance/i-12345678901234567",
            "awsRegion": "us-east-1",
            "availabilityZone": "us-east-1b",
            "configurationStateMd5Hash": "",
            "resourceCreationTime": "2018-05-02T16:18:05.000Z"
        }
    }
}`

var configurationItemChangeStateNull = `{
    "version": "0",
    "id": "11111111-2222-3333-4444-555555555555",
    "detail-type": "Config Configuration Item Change",
    "source": "aws.config",
    "account": "123456789012",
    "time": "2018-05-02T16:20:56Z",
    "region": "us-east-1",
    "resources": [
        "arn:aws:ec2:us-east-1:123456789012:instance/i-12345678901234567"
    ],
    "detail": {
        "recordVersion": "1.3",
        "messageType": "ConfigurationItemChangeNotification",
        "configurationItemDiff": {
            "changedProperties": {},
            "changeType": "CREATE"
        },
        "notificationCreationTime": "2018-05-02T16:20:56.017Z",
        "configurationItem": {
            "configuration": {
                "imageId": "ami-12345678",
                "instanceId": "i-12345678901234567",
				"platform": "Linux",
                "instanceType": "t2.small",
                "keyName": "my-key-name",
                "launchTime": "2018-05-02T16:18:05.000Z",
				"state": null,
                "subnetId": "subnet-12345678",
                "vpcId": "vpc-12345678",
                "iamInstanceProfile": {
                    "arn": "arn:aws:iam::123456789012:instance-profile/EC2InstanceProfileRole",
                    "id": "ABCDEFGHIJKLMNOPQSTUV"
                }
            },
            "supplementaryConfiguration": {},
            "tags": {
                "Name": "ec2-instance-name"
            },
            "configurationItemVersion": "1.3",
            "configurationItemCaptureTime": "2018-05-02T16:20:55.108Z",
            "configurationStateId": 1525278055108,
            "awsAccountId": "123456789012",
            "configurationItemStatus": "ResourceDiscovered",
            "resourceType": "AWS::EC2::Instance",
            "resourceId": "i-12345678901234567",
            "ARN": "arn:aws:ec2:us-east-1:123456789012:instance/i-12345678901234567",
            "awsRegion": "us-east-1",
            "availabilityZone": "us-east-1b",
            "configurationStateMd5Hash": "",
            "resourceCreationTime": "2018-05-02T16:18:05.000Z"
        }
    }
}`

func TestConfigurationStateNull(t *testing.T) {
	var ev struct {
		Detail CloudWatchEventDetail `json:"detail"`
	}
	err := json.Unmarshal([]byte(configurationItemChangeStateNull), &ev)
	if err != nil {
		t.Fatal(err)
	}
	if ev.Detail.ConfigurationItem.Configuration.State != "" {
		t.Error("expected \"\", received: %#V", ev.Detail.ConfigurationItem.Configuration.State)
	}
}
