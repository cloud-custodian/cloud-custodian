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
	"os"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-sdk-go/aws"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/api"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/apiutil"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/identity"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/manager"
)

var (
	// The DynamodDb table used for storing instance regisrations.
	RegistrationsTable = os.Getenv("OMNISSM_REGISTRATIONS_TABLE")

	// The instance role used by the SSM agent
	InstanceRole = os.Getenv("OMNISSM_INSTANCE_ROLE")

	// The list of accounts authorized to use the register API
	AccountWhitelist = os.Getenv("OMNISSM_ACCOUNT_WHITELIST")

	mgr *manager.Manager
)

func init() {
	mgr = manager.New(&manager.Config{
		Config:             aws.NewConfig(),
		RegistrationsTable: RegistrationsTable,
		InstanceRole:       InstanceRole,
	})
}

func main() {
	apiutil.Start(func(ctx context.Context, req events.APIGatewayProxyRequest) (*events.APIGatewayProxyResponse, error) {
		whitelist := identity.NewWhitelist(AccountWhitelist)
		r := api.RegistrationHandler{mgr}
		switch req.Resource {
		case "/register":
			var registerReq api.RegistrationRequest
			if err := json.Unmarshal([]byte(req.Body), &registerReq); err != nil {
				return nil, err
			}
			if err := registerReq.Verify(); err != nil {
				return nil, err
			}
			if !whitelist.Exists(registerReq.Identity().AccountId) {
				return nil, identity.ErrUnauthorizedAccount
			}
			switch req.HTTPMethod {
			case "POST":
				return apiutil.JSON(r.Create(ctx, &registerReq))
			case "PATCH":
				return apiutil.JSON(r.Update(ctx, &registerReq))
			}
		}
		return nil, apiutil.NotFoundError{fmt.Sprintf("cannot find resource %#v", req.Resource)}
	})
}
