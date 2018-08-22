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

package ssm

import (
	"context"
	"crypto/md5"
	"encoding/json"
	"fmt"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/ssm"
	"github.com/aws/aws-sdk-go/service/ssm/ssmiface"
	"github.com/golang/time/rate"
	"github.com/pkg/errors"
)

type Config struct {
	*aws.Config

	InstanceRole string
}

type SSM struct {
	ssmiface.SSMAPI

	config  *Config
	ssmRate *rate.Limiter
}

func New(config *Config) *SSM {
	s := &SSM{
		SSMAPI:  ssm.New(session.New(config.Config)),
		config:  config,
		ssmRate: rate.NewLimiter(5, 5),
	}
	return s
}

type Activation struct {
	ActivationId   string `json:"ActivationId"`
	ActivationCode string `json:"ActivationCode"`
}

func (s *SSM) CreateActivation(ctx context.Context, name string) (*Activation, error) {
	s.ssmRate.Wait(context.TODO())
	resp, err := s.SSMAPI.CreateActivationWithContext(ctx, &ssm.CreateActivationInput{
		DefaultInstanceName: aws.String(name),
		IamRole:             aws.String(s.config.InstanceRole),
		Description:         aws.String(name),
	})
	if err != nil {
		return nil, errors.Wrapf(err, "ssm.CreateActivation failed: %#v", name)
	}
	return &Activation{*resp.ActivationId, *resp.ActivationCode}, nil
}

type ResourceTags struct {
	ManagedId string            `json:"ManagedId"`
	Tags      map[string]string `json:"Tags"`
}

func (s *SSM) AddTagsToResource(ctx context.Context, input *ResourceTags) error {
	awsTags := make([]*ssm.Tag, 0)
	for k, v := range input.Tags {
		awsTags = append(awsTags, &ssm.Tag{Key: aws.String(k), Value: aws.String(v)})
	}
	s.ssmRate.Wait(ctx)
	_, err := s.SSMAPI.AddTagsToResourceWithContext(ctx, &ssm.AddTagsToResourceInput{
		ResourceType: aws.String(ssm.ResourceTypeForTaggingManagedInstance),
		ResourceId:   aws.String(input.ManagedId),
		Tags:         awsTags,
	})
	return errors.Wrapf(err, "ssm.AddTagsToResource failed: %#v", input.ManagedId)
}

type CustomInventory struct {
	TypeName    string
	ManagedId   string
	CaptureTime string
	Content     map[string]string
}

func (c *CustomInventory) ContentHash() string {
	data, _ := json.Marshal(c.Content)
	return fmt.Sprintf("%x", md5.Sum(data))
}

func (s *SSM) PutInventory(ctx context.Context, inv *CustomInventory) error {
	s.ssmRate.Wait(ctx)
	_, err := s.SSMAPI.PutInventoryWithContext(ctx, &ssm.PutInventoryInput{
		InstanceId: aws.String(inv.ManagedId),
		Items: []*ssm.InventoryItem{{
			CaptureTime:   aws.String(inv.CaptureTime), // "2006-01-02T15:04:05Z"
			Content:       []map[string]*string{aws.StringMap(inv.Content)},
			ContentHash:   aws.String(inv.ContentHash()),
			SchemaVersion: aws.String("1.0"),
			TypeName:      aws.String(inv.TypeName),
		}},
	})
	return errors.Wrapf(err, "ssm.PutInventory failed: %#v", inv.ManagedId)
}

func (s *SSM) DeregisterManagedInstance(ctx context.Context, managedId string) error {
	s.ssmRate.Wait(context.TODO())
	_, err := s.SSMAPI.DeregisterManagedInstanceWithContext(ctx, &ssm.DeregisterManagedInstanceInput{
		InstanceId: aws.String(managedId),
	})
	return errors.Wrapf(err, "ssm.DeregisterManagedInstance failed: %#v", managedId)
}

type ManagedInstance struct {
	ActivationId     string
	ManagedId        string
	Name             string
	RegistrationDate time.Time
}

func (s *SSM) DescribeInstanceInformation(ctx context.Context, activationId string) (*ManagedInstance, error) {
	resp, err := s.SSMAPI.DescribeInstanceInformationWithContext(ctx, &ssm.DescribeInstanceInformationInput{
		InstanceInformationFilterList: []*ssm.InstanceInformationFilter{
			{
				Key:      aws.String(ssm.InstanceInformationFilterKeyActivationIds),
				ValueSet: aws.StringSlice([]string{activationId}),
			},
		},
		MaxResults: aws.Int64(5),
	})
	if err != nil {
		return nil, errors.Wrapf(err, "ssm.DescribeInstanceInformation failed: %#v", activationId)
	}
	for _, instance := range resp.InstanceInformationList {
		m := &ManagedInstance{
			ActivationId:     aws.StringValue(instance.ActivationId),
			ManagedId:        aws.StringValue(instance.InstanceId),
			Name:             aws.StringValue(instance.Name),
			RegistrationDate: aws.TimeValue(instance.RegistrationDate),
		}
		return m, nil
	}
	return nil, errors.Errorf("activation not found: %#v", activationId)
}
