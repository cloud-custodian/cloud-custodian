package ssm_test

import (
	"testing"

	"github.com/capitalone/cloud-custodian/tools/omnissm/pkg/aws/ssm"
)

func TestSanitizeTag(t *testing.T) {
	cases := []struct {
		in, out string
	}{
		{"Normal Tag", "Normal Tag"},
		{"TAG_with-Numbers123", "TAG_with-Numbers123"},
		{"  extra space ", "extra space"},
		{"user@emailhost.com", "user@emailhost.com"},
		{" tag%^wit*h &invalid chars", "tagwith invalid chars"},
		{"ótag with unicodé", "tag with unicod"},
		{"value#comment here", "value"},
		{"value# comment here", "value"},
		{"Math is ok: 1+1=2", "Math is ok: 1+1=2"},
	}

	for _, c := range cases {
		s := ssm.SanitizeTag(c.in)
		if s != c.out {
			t.Errorf("Tag sanitization failed. Got '%s' expected '%s'", s, c.out)
		}
	}
}
