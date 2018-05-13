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

package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"

	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws/external"
	"github.com/rs/zerolog/log"

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

func main() {
	lambda.Start(func(ctx context.Context, event manager.CloudWatchEvent) (err error) {
		if event.Source != "aws.config" {
			return
		}
		if _, ok := resourceTypes[event.Detail.ConfigurationItem.ResourceType]; !ok {
			return
		}
		if _, ok := resourceStatusTypes[event.Detail.ConfigurationItem.ConfigurationItemStatus]; !ok {
			return
		}
		cfg, err := external.LoadDefaultAWSConfig()
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
			managedId := identity.Hash(event.Detail.ConfigurationItem.Name())
			_, err, ok := m.Get(managedId)
			if err != nil {
				return err
			}
			if !ok {
				log.Info().Err(err).Msgf("instance not found: %#v", managedId)
				return nil
			}
			switch event.Detail.ConfigurationItem.ResourceType {
			case "ResourceDiscovered", "OK":
				if err := m.Update(managedId, event.Detail.ConfigurationItem); err != nil {
					return err
				}
			case "ResourceDeleted":
				if err := m.Delete(managedId); err != nil {
					return err
				}
			}
			return nil
		case "OversizedConfigurationItemChangeNotification":
			data, err := json.Marshal(event)
			if err != nil {
				return err
			}
			fmt.Printf("Received oversized configuration item: %s\n", string(data))
			return err
		default:
			err = fmt.Errorf("unknown message type: %#v", event.Detail.MessageType)
		}
		return
	})
}
