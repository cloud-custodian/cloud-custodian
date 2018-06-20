.PHONY: build dist
bucket=c7n-ssm-build
GCFLAGS="-trimpath $(shell go env GOPATH)/src"
LDFLAGS="-X main.Version=`git rev-parse HEAD`"

build:
	@mkdir -p bin
	@go build -gcflags $(GCFLAGS) -ldflags $(LDFLAGS) -o bin/omnissm-agent ./cmd/omnissm-agent
	
build-linux:
	@mkdir -p bin
	@GOOS=linux GOARCH=amd64 go build -gcflags $(GCFLAGS) -ldflags $(LDFLAGS) -o bin/omnissm-agent-linux-amd64 ./cmd/omnissm-agent

build-lambda:
	@mkdir -p bin
	@go build -o bin/enrich-registrations ./functions/enrich-registrations
	@go build -o bin/handle-registrations ./functions/handle-registrations
	@go build -o bin/process-config-events ./functions/process-config-events
	@go build -o bin/process-deferred-actions ./functions/process-deferred-actions

dist: build-linux
	@mkdir -p dist
	@cp bin/omnissm-agent-linux-amd64 dist/omnissm-agent
	@gzip -c dist/omnissm-agent > dist/omnissm-agent-linux-amd64.gz
	@rm -f dist/omnissm-agent

test:
	@go test -v ./pkg/... | grep -v '^\?'

all: build build-lambda
