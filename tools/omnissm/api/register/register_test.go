package main

import (
	"encoding/json"
	"testing"
)

func TestValidateRequest(t *testing.T) {
	type errorResponse struct {
		Error   string `json:"error"`
		Message string `json:"message"`
	}

	failureCases := []struct {
		name string
		body string
		err  errorResponse
	}{
		{
			name: "empty request",
			body: "",
			err:  errorResponse{"invalid-request", "malformed json"},
		},
		{
			name: "malformed json",
			body: "{",
			err:  errorResponse{"invalid-request", "malformed json"},
		},
		{
			name: "unknown provider",
			body: `{"identity":"","signature":"","provider":"unknown","managed-id":""}`,
			err:  errorResponse{"invalid-request", "unknown provider"},
		},
		{
			name: "signature not base64",
			body: `{"identity":"identity","signature":"not%%base64","provider":"aws","managed-id":""}`,
			err:  errorResponse{"invalid-request", "malformed rsa signature"},
		},
		{
			name: "signature blank",
			body: `{"identity":"identity","signature":"","provider":"aws","managed-id":""}`,
			err:  errorResponse{"invalid-signature", "invalid identity"},
		},
		{
			name: "signature not valid",
			body: `{"identity":"identity","signature":"aWRlbnRpdHkK","provider":"aws","managed-id":""}`,
			err:  errorResponse{"invalid-signature", "invalid identity"},
		},
	}

	for _, c := range failureCases {
		t.Run(c.name, func(t *testing.T) {
			_, resp := validateRequest(c.body)
			if resp.StatusCode != 400 {
				t.Errorf("response status code was %d, expected 400", resp.StatusCode)
			}
			var errResp errorResponse
			if err := json.Unmarshal([]byte(resp.Body), &errResp); err != nil {
				t.Errorf("error unmarshaling reponse body: %v", err)
			}
			if errResp != c.err {
				t.Errorf("\n\texpected '%+v'\n\tgot      '%+v'", c.err, errResp)
			}
		})
	}
}
