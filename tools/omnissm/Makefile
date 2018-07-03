.PHONY: build dist build-lambda

bucket=c7n-ssm-build
GCFLAGS="-trimpath $(shell go env GOPATH)/src"
LDFLAGS="-X main.Version=`git rev-parse HEAD`"
functions := $(wildcard functions/*/.)

build:
	@mkdir -p bin
	@go build -gcflags $(GCFLAGS) -ldflags $(LDFLAGS) -o bin/omnissm-agent ./cmd/omnissm-agent
	
build-linux:
	@mkdir -p bin
	@GOOS=linux GOARCH=amd64 go build -gcflags $(GCFLAGS) -ldflags $(LDFLAGS) -o bin/omnissm-agent-linux-amd64 ./cmd/omnissm-agent

build-lambda: $(functions)
$(functions):
	cd $@ && $(MAKE) build

dist: build-linux
	@mkdir -p dist
	@cp bin/omnissm-agent-linux-amd64 dist/omnissm-agent
	@gzip -c dist/omnissm-agent > dist/omnissm-agent-linux-amd64.gz
	@rm -f dist/omnissm-agent

test:
	@go test -v ./pkg/... | grep -v '^\?'

all: build build-lambda

.PHONY: $(functions)
