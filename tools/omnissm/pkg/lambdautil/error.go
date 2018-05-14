package lambdautil

import "net/http"

type APIGatewayError interface {
	StatusCode() int
}

type NotFoundError struct {
	Message string
}

func (e NotFoundError) Error() string {
	return e.Message
}
func (NotFoundError) StatusCode() int { return http.StatusNotFound }
