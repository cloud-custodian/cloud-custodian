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
	"errors"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/request"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/ssm"
	"github.com/aws/aws-sdk-go/service/ssm/ssmiface"
	"github.com/jpillora/backoff"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/identity"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/store"
)

const (
	DefaultMaxRetries     = 5
	DefaultSSMServiceRole = "service-role/AmazonEC2RunCommandRoleForManagedInstances"
)

var ErrMaxRetriesExceeded = errors.New("max retries exceeded")

func retry(maxRetries int, fn func() error) error {
	b := &backoff.Backoff{Min: 1 * time.Second, Max: 30 * time.Second, Factor: 2}
	for int(b.Attempt()) < maxRetries {
		if err := fn(); err != nil {
			if request.IsErrorThrottle(err) || request.IsErrorRetryable(err) {
				time.Sleep(b.Duration())
				continue
			}
			return err
		}
		return nil
	}
	return ErrMaxRetriesExceeded
}

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

	maxRetries      int
	resourceTags    map[string]struct{}
	ssmInstanceRole string
	queue           *Queue
}

func NewManager(config *Config) *Manager {
	if config.InstanceRole == "" {
		config.InstanceRole = DefaultSSMServiceRole
	}
	m := &Manager{
		SSMAPI:          ssm.New(session.New(config.Config), aws.NewConfig().WithMaxRetries(0)),
		Registrations:   store.NewRegistrations(config.Config, config.RegistrationsTable),
		maxRetries:      DefaultMaxRetries,
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
		m.queue = NewQueue(config.QueueName, config.Config)
	}
	return m
}

func (m *Manager) Register(doc *identity.Document) (*store.RegistrationEntry, error) {
	var entry *store.RegistrationEntry
	err := retry(m.maxRetries, func() error {
		resp, err := m.SSMAPI.CreateActivation(&ssm.CreateActivationInput{
			DefaultInstanceName: aws.String(doc.Name()),
			IamRole:             aws.String(m.ssmInstanceRole),
			Description:         aws.String(doc.Name()),
		})
		if err != nil {
			return err
		}
		entry = &store.RegistrationEntry{
			Id:             identity.Hash(doc.Name()),
			ActivationId:   *resp.ActivationId,
			ActivationCode: *resp.ActivationCode,
		}
		return m.Put(entry)
	})
	if err == ErrMaxRetriesExceeded {
		msg, err := NewMessage(CreateActivation, doc)
		if err != nil {
			return nil, err
		}
		if err := m.queue.Send(msg); err != nil {
			return nil, err
		}
	}
	return entry, err
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
	err := retry(m.maxRetries, func() error {
		_, err := m.SSMAPI.AddTagsToResource(&ssm.AddTagsToResourceInput{
			ResourceType: aws.String(ssm.ResourceTypeForTaggingManagedInstance),
			ResourceId:   aws.String(id),
			Tags:         tags,
		})
		return err
	})
	if err == ErrMaxRetriesExceeded && m.queue != nil {
		body := struct {
			Id   string
			Tags []*ssm.Tag
		}{
			Id:   id,
			Tags: tags,
		}
		msg, err := NewMessage(AddTagsToResource, &body)
		if err != nil {
			return err
		}
		if err := m.queue.Send(msg); err != nil {
			return err
		}
		return ErrMaxRetriesExceeded
	}
	if err != nil {
		return err
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
	err = retry(m.maxRetries, func() error {
		_, err := m.SSMAPI.PutInventory(&ssm.PutInventoryInput{
			InstanceId: aws.String(id),
			Items: []*ssm.InventoryItem{{
				CaptureTime:   aws.String(ci.ConfigurationItemCaptureTime), // "2006-01-02T15:04:05Z"
				Content:       []map[string]*string{aws.StringMap(content)},
				SchemaVersion: aws.String("1.0"),
				TypeName:      aws.String("Custom:CloudInfo"),
			}},
		})
		return err
	})
	if err == ErrMaxRetriesExceeded {
		body := struct {
			CaptureTime string
			Content     map[string]string
		}{
			CaptureTime: ci.ConfigurationItemCaptureTime,
			Content:     content,
		}
		msg, err := NewMessage(PutInventory, &body)
		if err != nil {
			return err
		}
		if err := m.queue.Send(msg); err != nil {
			return err
		}
		return ErrMaxRetriesExceeded
	}
	return err
}

func (m *Manager) Delete(managedId string) error {
	err := retry(m.maxRetries, func() error {
		_, err := m.SSMAPI.DeregisterManagedInstance(&ssm.DeregisterManagedInstanceInput{
			InstanceId: aws.String(managedId),
		})
		return err
	})
	if err == ErrMaxRetriesExceeded {
		body := struct{ ManagedId string }{ManagedId: managedId}
		msg, err := NewMessage(DeregisterManagedInstance, &body)
		if err != nil {
			return err
		}
		if err := m.queue.Send(msg); err != nil {
			return err
		}
		return ErrMaxRetriesExceeded
	}
	return err
}
