package manager

import (
	"encoding/json"
	"testing"
)

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
	var ev Event
	err := json.Unmarshal([]byte(configurationItemChangeStateNull), &ev)
	if err != nil {
		t.Fatal(err)
	}
	if ev.Detail.ConfigurationItem.Configuration.State != "" {
		t.Error("expected \"\", received: %#V", ev.Detail.ConfigurationItem.Configuration.State)
	}
}
