
bucket = c7n-ssm-build
stack = omnissm-config-subscribe

deploy:
	aws cloudformation package --template-file cfn.yml --s3-bucket $(bucket) --s3-prefix builds --output-template built-template.yml
	aws cloudformation deploy --template-file built-template.yml --stack-name $(stack)
	rm built-template.yml

update:
	zip func.zip ./subscribe.py ./common.py
	aws lambda update-function-code --function-name="omnissm-config-subscribe" --zip-file fileb://func.zip
	rm func.zip


