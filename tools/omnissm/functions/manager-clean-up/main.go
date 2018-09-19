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
	"time"

	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/service/ssm"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/omnissm"
	"github.com/rs/zerolog/log"
)

var (
	omni *omnissm.OmniSSM
)

func init() {
	config, err := omnissm.ReadConfig("config.yaml")
	if err != nil {
		panic(err)
	}
	omni, err = omnissm.New(config)
	if err != nil {
		panic(err)
	}
}

func main() {
	lambda.Start(func(ctx context.Context) (err error) {
		output, err := omni.SSM.DescribeInstanceInformationWithContext(ctx, &ssm.DescribeInstanceInformationInput{
			InstanceInformationFilterList: []*ssm.InstanceInformationFilter{
				{
					Key:      aws.String("PingStatus"),
					ValueSet: aws.StringSlice([]string{"ConnectionLost"}),
				},
			},
		})
		if err != nil {
			return err
		}
		for _, element := range output.InstanceInformationList {
			if (time.Since(element.LastPingDateTime.UTC()).Hours() / 24) > omni.Config.CleanupAfterDays {
				entry, err, ok := omni.Registrations.GetByManagedId(ctx, *element.InstanceId)
				if err != nil {
					log.Error().Err(err)
					continue
				}
				if ok {
					//entry found do full cleanup
					if err := omni.DeregisterInstance(ctx, entry); err != nil {
						log.Error().Err(err)
					}
					log.Info().Msgf("Successfully deregistered instance: %#v", entry.ManagedId)
				} else {
					//entry not found, just clean up ssm registry
					if err := omni.SSM.DeregisterManagedInstance(ctx, *element.InstanceId); err != nil {
						// if we fail here, log and try again with next run
						log.Error().Err(err)
					} else {
						log.Info().Msgf("Successfully removed manager instance: %#v", *element.InstanceId)
					}
				}
			}
		}
		return nil
	})
}
