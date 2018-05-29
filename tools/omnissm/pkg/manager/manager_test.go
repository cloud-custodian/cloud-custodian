package manager

import (
	"encoding/json"
	"testing"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/service/dynamodb"
	"github.com/aws/aws-sdk-go/service/dynamodb/dynamodbattribute"
	"github.com/aws/aws-sdk-go/service/dynamodb/dynamodbiface"
	"github.com/aws/aws-sdk-go/service/ssm"
	"github.com/aws/aws-sdk-go/service/ssm/ssmiface"
	"github.com/google/go-cmp/cmp"
	"github.com/google/go-cmp/cmp/cmpopts"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/identity"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/store"
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

type mockSSMAPI struct {
	ssmiface.SSMAPI

	tags             []*ssm.Tag
	inventoryContent map[string]string
}

func (s *mockSSMAPI) CreateActivation(input *ssm.CreateActivationInput) (*ssm.CreateActivationOutput, error) {
	resp := &ssm.CreateActivationOutput{
		ActivationId:   aws.String("1"),
		ActivationCode: aws.String("1"),
	}
	return resp, nil
}

func (s *mockSSMAPI) AddTagsToResource(input *ssm.AddTagsToResourceInput) (*ssm.AddTagsToResourceOutput, error) {
	s.tags = input.Tags
	return nil, nil
}

func (s *mockSSMAPI) PutInventory(input *ssm.PutInventoryInput) (*ssm.PutInventoryOutput, error) {
	s.inventoryContent = aws.StringValueMap(input.Items[0].Content[0])
	return nil, nil
}

type mockDynamoDBAPI struct {
	dynamodbiface.DynamoDBAPI

	values map[string]map[string]*dynamodb.AttributeValue
}

func (d *mockDynamoDBAPI) PutItem(input *dynamodb.PutItemInput) (*dynamodb.PutItemOutput, error) {
	key := *input.Item["id"].S
	d.values[key] = input.Item
	return nil, nil
}

var (
	d = &mockDynamoDBAPI{values: make(map[string]map[string]*dynamodb.AttributeValue)}
	s = &mockSSMAPI{}
)

func newMockManager() *Manager {
	resourceTags := map[string]struct{}{
		"App":          struct{}{},
		"OwnerContact": struct{}{},
		"Name":         struct{}{},
	}
	m := &Manager{
		SSMAPI: s,
		Registrations: &store.Registrations{
			DynamoDBAPI: d,
		},
		resourceTags:    resourceTags,
		ssmInstanceRole: DefaultSSMServiceRole,
	}
	return m
}

func TestManagerRegister(t *testing.T) {
	m := newMockManager()
	entry, err := m.Register(&identity.Document{
		AvailabilityZone: "us-east-1b",
		Region:           "us-east-1",
		InstanceId:       "i-12345678901234567",
		AccountId:        "123456789012",
		InstanceType:     "t2.micro",
	})
	if err != nil {
		t.Fatal(err)
	}
	var e store.RegistrationEntry
	if err := dynamodbattribute.UnmarshalMap(d.values[entry.Id], &e); err != nil {
		t.Fatal(err)
	}
	if diff := cmp.Diff(entry, &e); diff != "" {
		t.Errorf("TestCase %s: after dynanmodbattribute.UnmarshalMap: (-got +want)\n%s", t.Name(), diff)
	}
}

func TestManagerUpdate(t *testing.T) {
	m := newMockManager()
	var ev Event
	if err := json.Unmarshal([]byte(configurationItemChange), &ev); err != nil {
		t.Fatal(err)
	}
	err := m.Update(identity.Hash(ev.Detail.ConfigurationItem.Name()), ev.Detail.ConfigurationItem)
	if err != nil {
		t.Fatal(err)
	}
	expectedTags := []*ssm.Tag{
		{Key: aws.String("Name"), Value: aws.String("ec2-instance-name")},
	}
	if diff := cmp.Diff(s.tags, expectedTags, cmpopts.IgnoreUnexported(ssm.Tag{})); diff != "" {
		t.Errorf("TestCase %s: after Manager.Update: (-got +want)\n%s", t.Name(), diff)
	}
	expectedInventory := map[string]string{
		"Region":       "us-east-1",
		"AccountId":    "123456789012",
		"Created":      "2018-05-02T16:18:05.000Z",
		"InstanceId":   "i-12345678901234567",
		"InstanceType": "t2.small",
		"InstanceRole": "arn:aws:iam::123456789012:instance-profile/EC2InstanceProfileRole",
		"VPCId":        "vpc-12345678",
		"ImageId":      "ami-12345678",
		"KeyName":      "my-key-name",
		"SubnetId":     "subnet-12345678",
		"Platform":     "Linux",
		"State":        "running",
	}
	if diff := cmp.Diff(s.inventoryContent, expectedInventory); diff != "" {
		t.Errorf("TestCase %s: after Manager.Update: (-got +want)\n%s", t.Name(), diff)
	}
}
