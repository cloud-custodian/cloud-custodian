
region=us-east-1
stack_name=custodian-log-exporter
s3_bucket=custodian-log-archive
s3_prefix=build
period=1h

install:
	virtualenv .venv
	.venv/bin/pip install -r requirements.txt
	.venv/bin/pip install awscli boto3 awslogs
	.venv/bin/python setup.py develop

package:
	cp -Rf c7n_logexporter stage
	cp -Rf .venv/lib/python2.7/site-packages/pkg_resources stage
	.venv/bin/pip install -r requirements.txt -t stage --no-deps
	cp config.yml stage
	find stage -name \*.py -delete

clean:
	rm -Rf .venv

destroy:
	.venv/bin/aws cloudformation delete-stack --stack-name $(stack_name)

deploy: package
	AWS_DEFAULT_REGION=$(region) .venv/bin/aws cloudformation package \
		--template-file cfn.yml \
		--s3-bucket $(s3_bucket) \
                --s3-prefix $(s3_prefix) \
		--output-template-file stage/built-api.yml
	AWS_DEFAULT_REGION=$(region) .venv/bin/aws cloudformation deploy \
		--stack-name=$(stack_name) \
		--capabilities CAPABILITY_IAM \
		--template-file stage/built-api.yml
	rm -Rf stage

logs:
	awslogs get -w /aws/lambda/$(shell aws cloudformation describe-stacks --stack-name $(stack_name) --query "Stacks[0].Outputs[?OutputKey==\`Function\`].OutputValue | [0]") \
	-s$(period)

error-logs:
	awslogs get /aws/lambda/$(shell aws cloudformation describe-stacks --stack-name $(stack_name) --query "Stacks[0].Outputs[?OutputKey==\`Function\`].OutputValue | [0]") \
	-s$(period) -f Traceback
