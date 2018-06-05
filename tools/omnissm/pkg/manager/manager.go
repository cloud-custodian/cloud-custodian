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
	"github.com/aws/aws-sdk-go/aws/request"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/ssm"
	"github.com/aws/aws-sdk-go/service/ssm/ssmiface"
	"github.com/pkg/errors"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/identity"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/store"
)

const DefaultSSMServiceRole = "service-role/AmazonEC2RunCommandRoleForManagedInstances"

type Config struct {
	*aws.Config
	RegistrationsTable string
	ResourceTags       []string
	InstanceRole       string
	QueueName          string
}

type Manager struct {
	ssmiface.SSMAPI
	*store.Registrations

	resourceTags    map[string]struct{}
	ssmInstanceRole string
	queue           *Queue
}

func New(config *Config) (*Manager, error) {
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
	if config.QueueName != "" {
		var err error
		m.queue, err = NewQueue(config.QueueName, config.Config)
		if err != nil {
			return nil, errors.Wrap(err, "cannot get SQS queue url")
		}
	}
	return m, nil
}

func (m *Manager) Register(doc *identity.Document) (*store.RegistrationEntry, error) {
	resp, err := m.SSMAPI.CreateActivation(&ssm.CreateActivationInput{
		DefaultInstanceName: aws.String(doc.Name()),
		IamRole:             aws.String(m.ssmInstanceRole),
		Description:         aws.String(doc.Name()),
	})
	if err != nil {
		if request.IsErrorThrottle(err) || request.IsErrorRetryable(err) && m.queue != nil {
			msg, mErr := NewMessage(CreateActivation, doc)
			if mErr != nil {
				return nil, mErr
			}
			if mErr := m.queue.Send(msg); err != nil {
				return nil, mErr
			}
		}
		return nil, errors.Wrapf(err, "ssm.CreateActivation failed: %#v", doc.Name())
	}
	entry := &store.RegistrationEntry{
		Id:             identity.Hash(doc.Name()),
		ActivationId:   *resp.ActivationId,
		ActivationCode: *resp.ActivationCode,
	}
	err = m.Put(entry)
	if err != nil {
		if request.IsErrorThrottle(err) || request.IsErrorRetryable(err) && m.queue != nil {
			msg, mErr := NewMessage(CreateActivation, doc)
			if mErr != nil {
				return nil, mErr
			}
			if mErr := m.queue.Send(msg); err != nil {
				return nil, mErr
			}
		}
		return nil, errors.Wrapf(err, "dynamodb.PutItem failed for RegistrationEntry Id: %#v", doc.Name())
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
		if request.IsErrorThrottle(err) || request.IsErrorRetryable(err) && m.queue != nil {
			body := struct {
				Id   string
				Tags []*ssm.Tag
			}{
				Id:   id,
				Tags: tags,
			}
			msg, mErr := NewMessage(AddTagsToResource, &body)
			if mErr != nil {
				return mErr
			}
			if mErr := m.queue.Send(msg); err != nil {
				return mErr
			}
		}
		return errors.Wrapf(err, "ssm.AddTagsToResource failed: %#v", id)
	}
	content := map[string]string{
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
	}
	_, err = m.SSMAPI.PutInventory(&ssm.PutInventoryInput{
		InstanceId: aws.String(id),
		Items: []*ssm.InventoryItem{{
			CaptureTime:   aws.String(ci.ConfigurationItemCaptureTime), // "2006-01-02T15:04:05Z"
			Content:       []map[string]*string{aws.StringMap(content)},
			SchemaVersion: aws.String("1.0"),
			TypeName:      aws.String("Custom:CloudInfo"),
		}},
	})
	if err != nil {
		if request.IsErrorThrottle(err) || request.IsErrorRetryable(err) && m.queue != nil {
			body := struct {
				CaptureTime string
				Content     map[string]string
			}{
				CaptureTime: ci.ConfigurationItemCaptureTime,
				Content:     content,
			}
			msg, mErr := NewMessage(PutInventory, &body)
			if mErr != nil {
				return mErr
			}
			if mErr := m.queue.Send(msg); err != nil {
				return mErr
			}
		}
		return errors.Wrapf(err, "ssm.PutInventory failed: %#v", id)
	}
	return nil
}

func (m *Manager) Delete(managedId string) error {
	_, err := m.SSMAPI.DeregisterManagedInstance(&ssm.DeregisterManagedInstanceInput{
		InstanceId: aws.String(managedId),
	})
	if err != nil {
		if request.IsErrorThrottle(err) || request.IsErrorRetryable(err) && m.queue != nil {
			body := struct{ ManagedId string }{ManagedId: managedId}
			msg, mErr := NewMessage(DeregisterManagedInstance, &body)
			if mErr != nil {
				return mErr
			}
			if mErr := m.queue.Send(msg); err != nil {
				return mErr
			}
		}
		return errors.Wrapf(err, "ssm.DeregisterManagedInstance failed: %#v", managedId)
	}
	return nil
}
