bucket = c7n-ssm-build
stack = omnissm

build:
	@GOOS=linux GOARCH=amd64 go build -o main *.go
	@zip main.zip main config.yaml

clean:
	@rm -f main main.zip built-template.yml

deploy: build
	aws cloudformation package --template-file cfn.yml --s3-bucket $(bucket) --s3-prefix builds --output-template built-template.yml
	aws cloudformation deploy --template-file built-template.yml --stack-name $(stack)
	$(MAKE) clean

delete:
	aws cloudformation delete-stack --stack-name=$(stack)

update: build
	aws lambda update-function-code --function-name="omnissm-reconciler" --zip-file fileb://main.zip
	$(MAKE) clean


