function-name=process-config-events
config-file=../config.yaml

build:
	@GOOS=linux GOARCH=amd64 go build -o main *.go
	@zip main.zip main $(config-file)

update: build
	aws lambda update-function-code --function-name=omnissm-$(function-name) --zip-file fileb://main.zip
	$(MAKE) clean

clean:
	@rm -f main main.zip built-template.yaml
