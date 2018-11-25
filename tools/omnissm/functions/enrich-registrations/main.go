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
	"sync"

	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go/aws"
	"github.com/rs/zerolog/log"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/configservice"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/ssm"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/omnissm"
)

var omni *omnissm.OmniSSM

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

func groupEntriesByAccountIdAndRegion(entries []*omnissm.RegistrationEntry) map[string][]*omnissm.RegistrationEntry {
	entriesByKey := make(map[string][]*omnissm.RegistrationEntry)
	for _, entry := range entries {
		entriesByKey[entry.AccountId+entry.Region] = append(entriesByKey[entry.AccountId+entry.Region], entry)
	}
	return entriesByKey
}

func main() {
	lambda.Start(func(ctx context.Context) error {
		entries, err := omni.Registrations.QueryIndexes(ctx, []omnissm.QueryIndexInput{
			{"IsTagged-index", "IsTagged", "0"},
			{"IsInventoried-index", "IsInventoried", "0"},
		}...)
		if err != nil {
			return err
		}
		entriesByKey := groupEntriesByAccountIdAndRegion(entries)
		var wg sync.WaitGroup
		for _, entries := range entriesByKey {
			wg.Add(1)
			accountId, region := entries[0].AccountId, entries[0].Region
			go func(awsConfig *aws.Config, accountId string, entries []*omnissm.RegistrationEntry) {
				defer wg.Done()

				// if the accountId is not in the roleMap, the lambda execution
				// role will be used
				roleArn, ok := omni.HasAssumeRole(accountId)
				if !ok {
					log.Info().Msgf("account %#v not found in role map", accountId)
				}
				cs := configservice.New(&configservice.Config{
					Config:     awsConfig,
					AssumeRole: roleArn,
				})
				var i, j int
				for _, entry := range entries {
					ci, err := cs.GetLatestResourceConfig(ctx, "AWS::EC2::Instance", entry.InstanceId)
					if err != nil {
						log.Info().Err(err).Msg("configservice.GetLatestResourceConfig failed")
						continue
					}
					if !ssm.IsManagedInstance(entry.ManagedId) {
						m, err := omni.SSM.DescribeInstanceInformation(ctx, entry.ActivationId)
						if err != nil {
							log.Info().Err(err).Msg("")
							continue
						}
						if !ssm.IsManagedInstance(m.ManagedId) {
							log.Info().Msgf("invalid ManagedId: %#v", m.ManagedId)
							continue
						}
						entry.ManagedId = m.ManagedId
						if err := omni.Registrations.Put(ctx, entry); err != nil {
							log.Info().Err(err).Msg("")
							continue
						}
					}
					if entry.IsTagged == 0 {
						tags := make(map[string]string)
						for k, v := range ci.Tags {
							if !omni.HasResourceTag(k) {
								continue
							}
							tags[k] = v
						}
						tags["AccountId"] = ci.AWSAccountId
						tags["VPCId"] = ci.Configuration.VPCId
						tags["SubnetId"] = ci.Configuration.SubnetId
						err := omni.SQS.Send(ctx, &omnissm.DeferredActionMessage{
							Type: omnissm.AddTagsToResource,
							Value: &ssm.ResourceTags{
								ManagedId: entry.ManagedId,
								Tags:      tags,
							},
						})
						if err == nil {
							i++
						} else {
							log.Info().Err(err).Msg("unable to defer AddTagsToResource")
						}
					}
					if entry.IsInventoried == 0 {
						err := omni.SQS.Send(ctx, &omnissm.DeferredActionMessage{
							Type: omnissm.PutInventory,
							Value: &ssm.CustomInventory{
								TypeName:    "Custom:CloudInfo",
								ManagedId:   entry.ManagedId,
								CaptureTime: ci.ConfigurationItemCaptureTime,
								Content:     configservice.ConfigurationItemContentMap(*ci),
							},
						})
						if err == nil {
							j++
						} else {
							log.Info().Err(err).Msg("unable to defer PutInventory")
						}
					}
				}
				if i+j > 0 {
					log.Info().Str("accountId", accountId).
						Int("AddTagsToResource", i).
						Int("PutInventory", j).
						Msg("enqueued deferred actions")
				}
			}(omni.Config.Copy().WithRegion(region), accountId, entries)
		}
		wg.Wait()
		return nil
	})
}
