package lambdautil

import (
	"context"
	"encoding/json"
	"net/http"

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
			resp, err := Error(err)
			if err != nil {
				return events.APIGatewayProxyResponse{}, err
			}
			return *resp, nil
			//return events.APIGatewayProxyResponse{}, err
		}
		// this shouldn't happen but lets be safe
		if resp == nil {
			resp = &events.APIGatewayProxyResponse{}
		}
		return *resp, err
	}
}

func Error(err error) (*events.APIGatewayProxyResponse, error) {
	code := http.StatusInternalServerError
	if gwErr, ok := err.(APIGatewayError); ok {
		code = gwErr.StatusCode()
	}
	return &events.APIGatewayProxyResponse{StatusCode: code, Body: err.Error()}, nil
}

func JSON(resp json.Marshaler, err error) (*events.APIGatewayProxyResponse, error) {
	if err != nil {
		return nil, err
	}
	data, err := json.Marshal(resp)
	if err != nil {
		return nil, err
	}
	return &events.APIGatewayProxyResponse{StatusCode: http.StatusOK, Body: string(data)}, nil
}
