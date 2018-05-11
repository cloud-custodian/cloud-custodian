.PHONY: build dist
bucket=c7n-ssm-build

build:
	@mkdir -p bin
	@go build -o bin/omnissm ./cmd/omnissm

dist:
	@mkdir -p dist
	@GOOS=linux GOARCH=amd64 go build -o dist/omnissm ./cmd/omnissm
	@gzip -c dist/omnissm > dist/omnissm-linux-amd64.gz
	@rm -f dist/omnissm
