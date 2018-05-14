package api_test

import (
	"encoding/json"
	"testing"

	"github.com/google/go-cmp/cmp"
	"github.com/google/go-cmp/cmp/cmpopts"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/api"
	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/store"
)

func TestRegistrationRequestUnmarshal(t *testing.T) {
	testCases := []struct {
		data     []byte
		expected *api.RegistrationRequest
	}{
		{
			data: []byte(`{"provider":"provider","document":"document","signature":"signature","managedId":"managedId"}`),
			expected: &api.RegistrationRequest{
				Provider:  "provider",
				Document:  []byte("\"document\""),
				Signature: "signature",
				ManagedId: "managedId",
			},
		},
	}

	for i, tc := range testCases {
		var req api.RegistrationRequest
		if err := json.Unmarshal([]byte(tc.data), &req); err != nil {
			t.Fatal(err)
		}
		if diff := cmp.Diff(&req, tc.expected, cmpopts.IgnoreUnexported(req)); diff != "" {
			t.Errorf("TestCase %d: after json.Unmarshal: (-got +want)\n%s", i, diff)
		}
	}
}

func TestRegistrationResponseMarshal(t *testing.T) {
	testCases := []struct {
		input    *api.RegistrationResponse
		expected []byte
	}{
		{
			input: &api.RegistrationResponse{
				RegistrationEntry: &store.RegistrationEntry{
					Id:             "id",
					ActivationId:   "aid",
					ActivationCode: "code",
					ManagedId:      "managedId",
				},
				Region: "us-east-2",
			},
			expected: []byte(`{"Id":"id","ActivationId":"aid","ActivationCode":"code","ManagedId":"managedId","region":"us-east-2"}`),
		},
	}

	for i, tc := range testCases {
		data, err := json.Marshal(tc.input)
		if err != nil {
			t.Fatal(err)
		}

		if diff := cmp.Diff(data, tc.expected); diff != "" {
			t.Errorf("TestCase %d: after json.Marshal: (-got +want)\n%s", i, diff)
		}
	}
}
