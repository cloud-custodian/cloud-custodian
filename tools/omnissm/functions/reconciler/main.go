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
	"github.com/hashicorp/go-multierror"
	"github.com/rs/zerolog/log"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/configservice"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/manager"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/store"
)

var (
	config *manager.Config
	mgr    *manager.Manager
)

func init() {
	var err error
	// TODO: needs to get from env var
	config, err = manager.ReadConfig("config.yaml")
	if err != nil {
		panic(err)
	}
	mgr, err = manager.New(&manager.Config{
		Config:             aws.NewConfig().WithMaxRetries(config.MaxRetries),
		RegistrationsTable: config.RegistrationsTable,
		ResourceTags:       config.ResourceTags,
	})
	if err != nil {
		panic(err)
	}
}

func groupEntriesByAccountIdAndRegion(entries []*store.RegistrationEntry) map[string][]*store.RegistrationEntry {
	entriesByKey := make(map[string][]*store.RegistrationEntry)
	for _, entry := range entries {
		entriesByKey[entry.AccountId+entry.Region] = append(entriesByKey[entry.AccountId+entry.Region], entry)
	}
	return entriesByKey
}

type ExecutionType int

const (
	EnrichManagedInstances ExecutionType = iota
)

func main() {
	lambda.Start(func(ctx context.Context) error {
		entries, err := mgr.Registrations.Scan()
		if err != nil {
			return err
		}
		entriesByKey := groupEntriesByAccountIdAndRegion(entries)
		var wg sync.WaitGroup
		for _, entries := range entriesByKey {
			wg.Add(1)
			accountId, region := entries[0].AccountId, entries[0].Region
			go func(awsConfig *aws.Config, accountId string, entries *store.RegistrationEntries) {
				defer wg.Done()

				// if the accountId is not in the roleMap, the lambda execution
				// role will be used
				roleArn, ok := config.HasAssumeRole(accountId)
				if !ok {
					log.Info().Msgf("account %#v not found in role map", accountId)
				}
				cs := configservice.New(&configservice.Config{
					Config:     awsConfig,
					AssumeRole: roleArn,
				})
				resources := make(map[string]string)
				for _, entry := range entries.All() {
					resources[entry.InstanceId] = "AWS::EC2::Instance"
				}
				configurationItems, err := cs.BatchGetResourceConfig(resources)
				if err != nil {
					if mErr, ok := err.(*multierror.Error); ok {
						for _, err := range mErr.Errors {
							log.Info().Err(err).Msg("multierror")
						}
						return
					}
					log.Info().Err(err).Msg("configservice.BatchGetResourceConfig failed")
					return
				}
				i := 0
				for _, ci := range configurationItems {
					entry, ok := entries.Lookup(store.IndexInstanceId, ci.ResourceId)
					if !ok {
						log.Info().Msgf("instance entry not found: %#v", ci.ResourceId)
						continue
					}
					if err := mgr.Update(entry.ManagedId, *ci); err != nil {
						log.Info().Err(err).Msgf("enrichment failed: %#v", entry.ManagedId)
						continue
					}
					entry.Enriched = true
					if err := mgr.Registrations.Update(entry); err != nil {
						log.Info().Err(err).Msgf("unable to update entry: %#v", entry.ManagedId)
					}
					i++
				}
				log.Info().Str("accountId", accountId).Msgf("successfully updated/enriched %d instances", i)
			}(config.Config.Copy().WithRegion(region), accountId, store.NewRegistrationEntries(entries))
		}
		wg.Wait()
		return nil
	})
}
