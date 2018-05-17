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

package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"os"
	"strings"

	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/s3"
	"github.com/pkg/errors"
	"github.com/rs/zerolog/log"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/awsutil"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/identity"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/manager"
)

var (
	resourceTypes = map[string]struct{}{
		"AWS::EC2::Instance": struct{}{},
	}

	resourceStatusTypes = map[string]struct{}{
		"ResourceDeleted":    struct{}{},
		"ResourceDiscovered": struct{}{},
		"OK":                 struct{}{},
	}
	resourceTags = make(map[string]struct{})

	RegistrationsTable = os.Getenv("OMNISSM_REGISTRATIONS_TABLE")
	ResourceTags       = os.Getenv("OMNISSM_RESOURCE_TAGS")
)

func init() {
	if RegistrationsTable == "" {
		RegistrationsTable = "omnissm-registrations"
	}
	if ResourceTags == "" {
		ResourceTags = "App,OwnerContact,Name"
	}
}

func handleConfigurationItemChange(detail manager.ConfigurationItemDetail) error {
	managedId := identity.Hash(detail.ConfigurationItem.Name())
	_, err, ok := m.Get(managedId)
	if err != nil {
		return err
	}
	if !ok {
		log.Info().Err(err).Msgf("instance not found: %#v", managedId)
		return nil
	}
	switch detail.ConfigurationItem.ResourceType {
	case "ResourceDiscovered", "OK":
		if err := m.Update(managedId, detail.ConfigurationItem); err != nil {
			return err
		}
	case "ResourceDeleted":
		if err := m.Delete(managedId); err != nil {
			return err
		}
	}
	return nil
}

func downloadS3ConfigurationItem(path string) ([]byte, error) {
	cfg, err := awsutil.LoadDefaultAWSConfig()
	if err != nil {
		return
	}
	s3 := s3.New(session.New(cfg))
	parts := strings.SplitN(path, "/", 2)
	if len(parts) != 2 {
		return nil, errors.Errorf("invalid path: %#v", path)
	}
	resp, err := s3.GetObject(&s3.GetObjectInput{
		Bucket: aws.String(parts[0]),
		Key:    aws.String(parts[1]),
	})
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	data, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	return data, nil
}

func main() {
	lambda.Start(func(ctx context.Context, event manager.Event) (err error) {
		if event.Source != "aws.config" {
			return
		}
		cfg, err := awsutil.LoadDefaultAWSConfig()
		if err != nil {
			return
		}
		m := manager.NewManager(&manager.Config{
			Config:             cfg,
			RegistrationsTable: RegistrationsTable,
			ResourceTags:       strings.Split(ResourceTags, ","),
		})
		switch event.Detail.MessageType {
		case "ConfigurationItemChangeNotification":
			if _, ok := resourceTypes[event.Detail.ConfigurationItem.ResourceType]; !ok {
				return
			}
			if _, ok := resourceStatusTypes[event.Detail.ConfigurationItem.ConfigurationItemStatus]; !ok {
				return
			}
			return handleConfigurationItemChange(event.Detail)
		case "OversizedConfigurationItemChangeNotification":
			if _, ok := resourceTypes[event.Detail.ConfigurationItemSummary.ResourceType]; !ok {
				return
			}
			if _, ok := resourceStatusTypes[event.Detail.ConfigurationItemSummary.ConfigurationItemStatus]; !ok {
				return
			}
			data, err := downloadS3ConfigurationItem(event.Detail.S3DeliverySummary.S3BucketLocation)
			if err != nil {
				return err
			}
			var eventDetail manager.ConfigurationItemDetail
			if err := json.Unmarshal(data, &eventDetail); err != nil {
				return err
			}
			return handleConfigurationItemChange(eventDetail)
		default:
			err = fmt.Errorf("unknown message type: %#v", event.Detail.MessageType)
		}
		return
	})
}
