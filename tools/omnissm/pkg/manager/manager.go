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

package manager

import (
	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/ssm"
	"github.com/aws/aws-sdk-go/service/ssm/ssmiface"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/identity"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/store"
)

const DefaultSSMServiceRole = "service-role/AmazonEC2RunCommandRoleForManagedInstances"

type Config struct {
	*aws.Config
	RegistrationsTable string
	ResourceTags       []string
	InstanceRole       string
}

type Manager struct {
	ssmiface.SSMAPI
	*store.Registrations

	resourceTags    map[string]struct{}
	ssmInstanceRole string
}

func NewManager(config *Config) *Manager {
	if config.InstanceRole == "" {
		config.InstanceRole = DefaultSSMServiceRole
	}
	m := &Manager{
		SSMAPI:          ssm.New(session.New(config.Config)),
		Registrations:   store.NewRegistrations(config.Config, config.RegistrationsTable),
		resourceTags:    make(map[string]struct{}),
		ssmInstanceRole: config.InstanceRole,
	}
	if len(config.ResourceTags) == 0 {
		config.ResourceTags = []string{"App", "OwnerContact", "Name"}
	}
	for _, t := range config.ResourceTags {
		m.resourceTags[t] = struct{}{}
	}
	return m
}

func (m *Manager) Register(doc *identity.Document) (*store.RegistrationEntry, error) {
	resp, err := m.SSMAPI.CreateActivation(&ssm.CreateActivationInput{
		DefaultInstanceName: aws.String(doc.Name()),
		IamRole:             aws.String(m.ssmInstanceRole),
		Description:         aws.String(doc.Name()),
	})
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
	platform := "Linux"
	if ci.Configuration.Platform != "" {
		platform = ci.Configuration.Platform
	}
	tags := make([]*ssm.Tag, 0)
	for k, v := range ci.Tags {
		if _, ok := m.resourceTags[k]; !ok {
			continue
		}
		tags = append(tags, &ssm.Tag{Key: aws.String(k), Value: aws.String(v)})
	}
	_, err := m.SSMAPI.AddTagsToResource(&ssm.AddTagsToResourceInput{
		ResourceType: aws.String(ssm.ResourceTypeForTaggingManagedInstance),
		ResourceId:   aws.String(id),
		Tags:         tags,
	})
	if err != nil {
		return err
	}
	_, err = m.SSMAPI.PutInventory(&ssm.PutInventoryInput{
		InstanceId: aws.String(id),
		Items: []*ssm.InventoryItem{{
			CaptureTime: aws.String(ci.ConfigurationItemCaptureTime), // "2006-01-02T15:04:05Z"
			Content: []map[string]*string{
				aws.StringMap(map[string]string{
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
				}),
			},
			SchemaVersion: aws.String("1.0"),
			TypeName:      aws.String("Custom:CloudInfo"),
		}},
	})
	return err
}

func (m *Manager) Delete(managedId string) error {
	_, err := m.SSMAPI.DeregisterManagedInstance(&ssm.DeregisterManagedInstanceInput{
		InstanceId: aws.String(managedId),
	})
	return err
}
