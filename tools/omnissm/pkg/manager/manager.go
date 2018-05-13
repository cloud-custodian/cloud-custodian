/*
Copyright 2018 Capital One Services, LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.

You may obtain a copy of the License at
	http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package manager

import (
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/ssm"
	"github.com/aws/aws-sdk-go-v2/service/ssm/ssmiface"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/identity"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/store"
)

const (
	// SSMInstanceRole IAM Role to associate to instance registration
	SSMInstanceRole = "service-role/AmazonEC2RunCommandRoleForManagedInstances"
)

type Config struct {
	aws.Config
	RegistrationsTable string
	ResourceTags       []string
}

type Manager struct {
	ssmiface.SSMAPI
	*store.Registrations

	resourceTags map[string]struct{}
}

func NewManager(config *Config) *Manager {
	m := &Manager{
		SSMAPI:        ssm.New(config.Config),
		Registrations: store.NewRegistrations(config.Config, config.RegistrationsTable),
	}
	var tags string
	if len(config.ResourceTags) == 0 {
		tags = "App,OwnerContact,Name"
	}
	for _, t := range strings.Split(tags, ",") {
		m.resourceTags[t] = struct{}{}
	}
	return m
}

func (m *Manager) Register(doc *identity.Document) (*store.RegistrationEntry, error) {
	req := m.SSMAPI.CreateActivationRequest(&ssm.CreateActivationInput{
		DefaultInstanceName: aws.String(doc.Name()),
		IamRole:             aws.String(SSMInstanceRole),
		Description:         aws.String(doc.Name()),
	})
	resp, err := req.Send()
	if err != nil {
		return nil, err
	}
	entry := &store.RegistrationEntry{
		Id:             identity.Hash(doc.Name()),
		ActivationId:   *resp.ActivationId,
		ActivationCode: *resp.ActivationCode,
	}
	if err := m.Put(entry); err != nil {
		return nil, err
	}
	return entry, nil
}

func (m *Manager) Update(id string, ci ConfigurationItem) error {
	var platform string
	if ci.Configuration.Platform == "" {
		platform = "Linux"
	}
	tags := make([]ssm.Tag, 0)
	for k, v := range ci.Tags {
		if _, ok := m.resourceTags[k]; !ok {
			continue
		}
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

func (m *Manager) Delete(managedId string) error {
	req := m.SSMAPI.DeregisterManagedInstanceRequest(&ssm.DeregisterManagedInstanceInput{
		InstanceId: aws.String(managedId),
	})
	if _, err := req.Send(); err == nil {
		return err
	}
	return nil
}
