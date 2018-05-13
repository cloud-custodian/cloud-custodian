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
	"net/http"
	"os"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws/external"
	"github.com/pkg/errors"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/api"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/identity"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/manager"
)

var (
	// The DynamodDb table used for storing instance regisrations.
	RegistrationsTable = os.Getenv("OMNISSM_REGISTRATIONS_TABLE")
)

func main() {
	lambda.Start(api.ServeResponse(func(ctx context.Context, req *events.APIGatewayProxyRequest) (*events.APIGatewayProxyResponse, error) {
		whitelist := identity.NewWhitelist(os.Getenv("OMNISSM_ACCOUNT_WHITELIST"))
		cfg, err := external.LoadDefaultAWSConfig()
		if err != nil {
			return nil, err
		}
		router := api.NewRouter(manager.NewManager(&manager.Config{
			Config:             cfg,
			RegistrationsTable: RegistrationsTable,
		}))
		switch req.Resource {
		case "/register":
			var r api.RegisterRequest
			if err := json.Unmarshal([]byte(req.Body), &r); err != nil {
				return api.NewErrorResponse(http.StatusBadRequest, err), nil
			}
			if err := r.Verify(); err != nil {
				return api.NewErrorResponse(http.StatusBadRequest, err), nil
			}
			if !whitelist.Exists(r.Identity().AccountId) {
				return api.NewErrorResponse(http.StatusBadRequest, errors.New("unauthorized account")), nil
			}
			switch req.HTTPMethod {
			case "PATCH":
				return router.HandleUpdateRegisterRequest(ctx, &r)
			case "POST":
				return router.HandleCreateRegisterRequest(ctx, &r)
			}
		}
		return api.NewErrorResponse(http.StatusNotFound, errors.Errorf("cannot find resource %#v", req.Resource)), nil
	}))
}
