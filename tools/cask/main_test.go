// Copyright 2019 Microsoft Corporation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package main

import (
	"path/filepath"
	"reflect"
	"testing"
)

func TestGenerateBinds(t *testing.T) {
	tests := []struct {
		name     string
		args     []string
		wantArgs []string
	}{
		{name: "one",
			args:     []string{"run", "-s", ".", "main.go"},
			wantArgs: []string{"run", "-s", "/home/custodian/.", "/home/custodian/main.go"},
		},
		{name: "two",
			args: []string{"run", "-s", ".", "main.go", "main.go"},
			wantArgs: []string{"run", "-s", "/home/custodian/.",
				"/home/custodian/main.go", "/home/custodian/main.go"},
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			generateBinds(tt.args)
			if !reflect.DeepEqual(tt.args, tt.wantArgs) {
				t.Errorf("GenerateBinds() = %v, want %v", tt.args, tt.wantArgs)
			}
		})
	}
}

func TestProcessOutputArgs(t *testing.T) {
	pwd, _ := filepath.Abs(".")

	tests := []struct {
		name string
		args []string
		want []string
	}{
		{name: "short_space",
			args: []string{"run", "-s", ".", "foo.yaml"},
			want: []string{"run", "-s", pwd, "foo.yaml"}},

		{name: "short_equal",
			args: []string{"run", "-s=.", "foo.yaml"},
			want: []string{"run", "-s", pwd, "foo.yaml"}},

		{name: "long_space",
			args: []string{"run", "--output-dir", ".", "foo.yaml"},
			want: []string{"run", "--output-dir", pwd, "foo.yaml"}},

		{name: "long_equal",
			args: []string{"run", "--output-dir=.", "foo.yaml"},
			want: []string{"run", "-s", pwd, "foo.yaml"}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			processOutputArgs(&tt.args)
			if !reflect.DeepEqual(tt.args, tt.want) {
				t.Errorf("ProcessOutputArgs() = %v, want %v", tt.args, tt.want)
			}
		})
	}
}

func Test_isPath(t *testing.T) {
	tests := []struct {
		name string
		arg  string
		want bool
	}{
		{name: "flag", arg: "-s", want: false},
		{name: "not exist", arg: "not_real_file.yaml", want: false},
		{name: "schema", arg: "schema", want: false},
		{name: "cd", arg: ".", want: true},
		{name: "parent", arg: "../", want: true},
		{name: "file", arg: "main.go", want: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := isPath(tt.arg); got != tt.want {
				t.Errorf("isPath() = %v, want %v", got, tt.want)
			}
		})
	}
}
