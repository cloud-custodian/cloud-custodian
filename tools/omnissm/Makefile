.PHONY: build dist
bucket=c7n-ssm-build
LDFLAGS="-X main.Version=`git rev-parse HEAD`"

build:
	@mkdir -p bin
	@go build -ldflags $(LDFLAGS) -o bin/omnissm ./cmd/omnissm
	
build-linux:
	@mkdir -p bin
	@GOOS=linux GOARCH=amd64 go build -ldflags $(LDFLAGS) -o bin/omnissm-linux-amd64 ./cmd/omnissm

build-lambda:
	@mkdir -p bin
	@go build -o bin/register ./functions/register
	@go build -o bin/subscribe ./functions/subscribe

dist: build-linux
	@mkdir -p dist
	@cp bin/omnissm-linux-amd64 dist/omnissm
	@gzip -c dist/omnissm > dist/omnissm-linux-amd64.gz
	@rm -f dist/omnissm

test:
	@go test -v ./pkg/... | grep -v '^\?'

all: build build-lambda
