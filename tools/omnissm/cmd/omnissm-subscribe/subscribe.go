package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"

	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws/awserr"
	"github.com/aws/aws-sdk-go-v2/aws/external"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	"github.com/rs/zerolog/log"
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
	RegistrationsTable = os.Getenv("REGISTRATIONS_TABLE")
)

func init() {
	if RegistrationsTable == "" {
		RegistrationsTable = "omnissm-registrations"
	}
}

func main() {
	lambda.Start(func(ctx context.Context, event cloudWatchEvent) (err error) {
		if event.Source != "aws.config" {
			return
		}
		if _, ok := resourceTypes[event.Detail.ConfigurationItem.ResourceType]; !ok {
			return
		}
		if _, ok := resourceStatusTypes[event.Detail.ConfigurationItem.ConfigurationItemStatus]; !ok {
			return
		}
		switch event.Detail.MessageType {
		case "ConfigurationItemChangeNotification":
			cfg, err := external.LoadDefaultAWSConfig()
			if err != nil {
				return err
			}
			managedId := event.Detail.ConfigurationItem.getIdentity()
			m := NewManagedInstance(cfg)
			if err := m.GetItem(managedId); err != nil {
				if aerr, ok := err.(awserr.Error); ok {
					if aerr.Code() == dynamodb.ErrCodeResourceNotFoundException {
						log.Info().Err(err).Msgf("instance not found: %#v", managedId)
						return err
					}
				}
			}
			switch event.Detail.ConfigurationItem.ResourceType {
			case "ResourceDiscovered", "OK":
				m.Update(managedId, event.Detail.ConfigurationItem)
			case "ResourceDeleted":
				m.Delete(managedId)
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
