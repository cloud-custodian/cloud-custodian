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

package api

import (
	"context"

	"github.com/aws/aws-lambda-go/events"
)

type APIGatewayHandlerFunc func(context.Context, events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error)

// ServeResponse changes the input function to the required API Gateway
// request/response handler function signature. This avoids passing around
// handler function responses by copying (potentially large)
// events.APIGatewayProxyResponse structs.
func ServeResponse(fn func(context.Context, *events.APIGatewayProxyRequest) (*events.APIGatewayProxyResponse, error)) APIGatewayHandlerFunc {
	return func(ctx context.Context, req events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
		resp, err := fn(ctx, &req)
		if err != nil {
			return events.APIGatewayProxyResponse{}, err
		}
		// this shouldn't happen but lets be safe
		if resp == nil {
			resp = &events.APIGatewayProxyResponse{}
		}
		return *resp, err
	}
}
