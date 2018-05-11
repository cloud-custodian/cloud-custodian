package main

import (
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb/dynamodbiface"
	"github.com/aws/aws-sdk-go-v2/service/ssm"
	"github.com/aws/aws-sdk-go-v2/service/ssm/ssmiface"
)

type ManagedInstance struct {
	dynamodbiface.DynamoDBAPI
	ssmiface.SSMAPI
}

func NewManagedInstance(cfg aws.Config) *ManagedInstance {
	return &ManagedInstance{
		DynamoDBAPI: dynamodb.New(cfg),
		SSMAPI:      ssm.New(cfg),
	}
}

func (m *ManagedInstance) Update(id string, ci configurationItem) error {
	var platform string
	if ci.Configuration.Platform == "" {
		platform = "Linux"
	}
	tags := make([]ssm.Tag, 0)
	for k, v := range ci.Tags {
		tags = append(tags, ssm.Tag{Key: aws.String(k), Value: aws.String(v)})
	}
	req := m.SSMAPI.AddTagsToResourceRequest(&ssm.AddTagsToResourceInput{
		ResourceType: ssm.ResourceTypeForTaggingManagedInstance,
		ResourceId:   aws.String(id),
		Tags:         tags,
	})
	if _, err := req.Send(); err != nil {
		return err
	}
	preq := m.SSMAPI.PutInventoryRequest(&ssm.PutInventoryInput{
		InstanceId: aws.String(id),
		Items: []ssm.InventoryItem{{
			CaptureTime: aws.String(ci.ConfigurationItemCaptureTime), // "2006-01-02T15:04:05Z"
			Content: []map[string]string{
				map[string]string{
					"Region":       ci.AWSRegion,
					"AccountId":    ci.AWSAccountId,
					"Created":      ci.ResourceCreationTime,
					"InstanceId":   ci.ResourceId,
					"InstanceType": ci.Configuration.InstanceType,
					"InstanceRole": ci.Configuration.IAMInstanceProfile.ARN,
					"VPCId":        ci.Configuration.VPCId,
					"ImageId":      ci.Configuration.ImageId,
					"KeyName":      ci.Configuration.KeyName,
					"SubnetId":     ci.Configuration.SubnetId,
					"Platform":     platform,
					"State":        string(ci.Configuration.State),
				},
			},
			SchemaVersion: aws.String("1.0"),
			TypeName:      aws.String("Custom:CloudInfo"),
		}},
	})
	if _, err := preq.Send(); err != nil {
		return err
	}
	return nil
}

func (m *ManagedInstance) Delete(managedId string) error {
	req := m.SSMAPI.DeregisterManagedInstanceRequest(&ssm.DeregisterManagedInstanceInput{
		InstanceId: aws.String(managedId),
	})
	if _, err := req.Send(); err == nil {
		return err
	}
	return nil
}

func (m *ManagedInstance) GetItem(id string) error {
	req := m.DynamoDBAPI.GetItemRequest(&dynamodb.GetItemInput{
		TableName: aws.String(RegistrationsTable),
		Key:       map[string]dynamodb.AttributeValue{"id": {S: aws.String(id)}},
	})
	_, err := req.Send()
	return err
}
