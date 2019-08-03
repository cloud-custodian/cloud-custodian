# Variables
#
# per standard make convention, override as key=value pairs when invoking
# ie. $ make metrics period=1d
stack_name = "sphere7-dev"
config = "config.yml"
s3_bucket = "sphere11-dev-us-west-2"
s3_prefix = "deploy"
period = "15m"
region = "us-west-2"

install:
	virtualenv -p python2.7 .venv
	source .venv/bin/activate && pip install -r requirements.txt
	.venv/bin/python setup.py develop

clean:
	rm -Rf .venv

destroy:
	.venv/bin/aws cloudformation delete-stack --stack-name $(stack_name)

package:
	cp -Rf c7n_sphere11 stage
	cp -Rf .venv/lib/python2.7/site-packages/pkg_resources stage
	.venv/bin/python c7n_sphere11/admin.py format_json --config=config.yml > stage/config.json
	# using custom branch build
	#.venv/bin/pip install -f dist -i dist --no-deps -t stage c7n
	.venv/bin/pip install -r requirements-gw.txt -t stage --no-deps
	find stage -name \*.pyc -delete

update-code: package
	cd stage && zip -q -r ../func.zip *
	AWS_DEFAULT_REGION=$(region) aws lambda update-function-code \
		--function-name $(shell aws cloudformation describe-stacks --stack-name $(stack_name) --query Stacks[0].Outputs[0].OutputValue) \
		--zip-file fileb://func.zip \
		--publish
	rm -Rf stage

deploy: package
	AWS_DEFAULT_REGION=$(region) .venv/bin/aws cloudformation package \
		--template-file cfn/api.yml \
		--s3-bucket $(s3_bucket) \
                --s3-prefix $(s3_prefix) \
		--output-template-file stage/built-api.yml
	AWS_DEFAULT_REGION=$(region) .venv/bin/aws cloudformation deploy \
		--stack-name=$(stack_name) \
		--capabilities CAPABILITY_IAM \
		--template-file stage/built-api.yml
	rm -Rf stage

check:
	SPHERE11_API=$(shell AWS_DEFAULT_REGION=$(region) aws cloudformation describe-stacks --stack-name $(stack_name) --query "Stacks[0].Outputs[?OutputKey==\`Url\`].OutputValue | [0]") \
	python -m c7n_sphere11.admin check

logs:
	awslogs get -w /aws/lambda/$(shell aws cloudformation describe-stacks --stack-name $(stack_name) --query "Stacks[0].Outputs[?OutputKey==\`Function\`].OutputValue | [0]") \
	-s$(period)

error-logs:
	awslogs get /aws/lambda/$(shell aws cloudformation describe-stacks --stack-name $(stack_name) --query "Stacks[0].Outputs[?OutputKey==\`Function\`].OutputValue | [0]") \
	-s$(period) -f Traceback



# App Specific Stuff

delta:
	SPHERE11_API=$(shell aws cloudformation describe-stacks --stack-name $(stack_name) --query "Stacks[0].Outputs[?OutputKey==\`Url\`].OutputValue | [0]") \
	python -m c7n_sphere11.admin delta

flush:
	python -m c7n_sphere11.admin flush_pending \
	--function=$(shell aws cloudformation describe-stacks --stack-name $(stack_name) --query "Stacks[0].Outputs[?OutputKey==\`Function\`].OutputValue | [0]")

metrics:
	python -m c7n_sphere11.admin metrics \
	--function=$(shell aws cloudformation describe-stacks --stack-name $(stack_name) --query "Stacks[0].Outputs[?OutputKey==\`Function\`].OutputValue | [0]") \
	--api=sphere11 \
	--start=$(period)

endpoint:
	aws cloudformation describe-stacks --stack-name $(stack_name) --query "Stacks[0].Outputs[?OutputKey==\`Url\`].OutputValue | [0]")


local:
	python -m c7n_sphere11.admin local


# Policy commands require AWS env with target account active
policy-logs:
	awslogs get /aws/lambda/custodian-sg-fast-revert -s$(period) --no-color

policy-vpc-logs:
	awslogs get -w /aws/lambda/custodian-sg-locked-vpc-sg-create -s$(period) --no-color


policy-error-logs:
	awslogs get /aws/lambda/custodian-sg-fast-revert -s$(period) --no-color -s$(period) -f Traceback
	awslogs get /aws/lambda/custodian-sg-locked-vpc-sg-create -s$(period) --no-color -s$(period) -f Traceback
