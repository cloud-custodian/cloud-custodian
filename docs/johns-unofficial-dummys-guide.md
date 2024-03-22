John's Unofficial Dummys' Guide to Writing a Cloud Custodian Extension
====
---

This doco is mostly intended to remind the author how this stuff works.

Before you start you'll need an IDE - I use Intellij with the Python plugin.
You'll need to have gone through these 
- https://cloudcustodian.io/docs/contribute.html
- https://cloudcustodian.io/docs/developer/index.html#developer
- https://cloudcustodian.io/docs/aws/contribute.html#adding-new-aws-resources

# Artefacts we'll create to deliver a working Cloud Custodian extension

When writing an extension from scratch then you need to ...

- create an implementation of the extension
- write tests
- register your extension with Cloud Custodian

For the rest of this discussion we'll flesh out the code around a real example; creating an extension for the
VoiceConnector resource of the ChimeSDKVoice service. At some point this resource may really exist as a service in CC
but please don't get confused between this discussion here and any future real implementation; to be clear, at the time
of writing there is no VoiceConnector resource in Cloud Custodian.

The implementation class for a CC extension that targets ChimeSDKVoice would best be placed in a file
called `c7n/resources/chimesdkvoice.py` and the tests for the extension will be placed in `tests/test_chimesdkvoice.py`.

Registering the extension implementation class with CC requires one to annotate the implementation class with an
Identify that we need to choose, and then add a record of that ID to `c7n/resources/resource_map.py`, where that record
maps the chosen ID back to your implementation class.

The implementation class for our VoiceConnector impl will primarily contain some configuration that tells Cloud
Custodian how to connect to the AWS API for ChimeSDKVoice using the Boto3 client SDK. Using the SDK Cloud Custodian can
discover instance of resources and find out their detailed descriptions. In addition, there is sometimes the need to
override features of CC to adapt CC to operate properly with your specific resource type and any such overrides will
live inside your impl class file (should the need arise).

## Gathering the API and data model details needed to build the extension

Since we need to configure the comms between CC and AWS we need to discover and familiarise ourselves with the relevant
AWS APIs and data models. These API's are provided by
the ["Boto3" library](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html) and the API's for each AWS
service are grouped into separate Boto clients and each client has a well-known name documented in the Boto3 pages.

Three main tings we need to discover are ..

- Boto Service name, aka Client name: The name of the Boto3 client that will be used to communicate with the API's of
  the resource you are building an extension for
- Enumerate API: The Boto API that allows CC to enumerate (ie list) all the resources. We need to know the names of the
  parameters to this API call and also the shape of the response from the API.
- Detail API : The Boto API that provides a detailed description of each resource. Again we need to know about the shape
  of the request and responses.

Optional ..

- Cloud Trail Event: If you are planning to make your extension and event based detection then you will also need to
  know the details of the specific AWS cloud trail events that you are going to use as triggers. But we'll come back to
  events much later.

Within Cloud Custodian the API's above are used as follows ...

- The "enumerate" API (also commonly known as "list" API) is generally required by the Cloud Custodian "pull" mode of
  operation. It is needed in order to discover the Id's of the VoiceConnector instances. In "event" mode the Id's of the
  resources will be looked up within the relevant cloud trail event.
- The "detail" API (sometimes know as the "describe" or "get" API) is needed by both the "pull" and "event" modes of
  operation and allow CC to obtain the full details of each VoiceConnector resource so that filters and actions etc can
  be applied to that resource.

The Boto3 documentation provides content that covers all the various API and model information requirements just
outlined above.

- Boto Service Name

The Boto 3 ["services" page](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/index.html)
lists all the supported services and if we scroll down to the ChimeSDKVoice service entry then we find a link  
['Client'](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/chime-sdk-voice.html) that leads
to a page providing details of the ChimeSDKVoice APIs.

On the ChimeSDKVoice client page then we can see a snippet that shows us that the Boto3 API client name is "
chime-sdk-voice".

    import boto3
    client = boto3.client('chime-sdk-voice')

This is the first value we need to make a note of as we'll use it to configure the extension a bit later.

- Enumerate (or List) API

Generally, the "enumerate" API will be called something like "list_xxxxx". If we look at the ChimeSDKVoice client page,
then we can see there is an API
called [list_voice_connectors](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/chime-sdk-voice/client/list_voice_connectors.html)
that lists the resources we are looking for. The AWS "list" API's will generally not take parameters, or at least any
parameters are generally restricted to how to do paging of results.

The documentation shows us the shape of the response from the list_voice_connector call...

    Response Syntax:
    {
        'VoiceConnectors': [
            {
                'VoiceConnectorId': 'string',
                'AwsRegion': 'us-east-1'|'us-west-2'|'ca-central-1'|'eu-central-1'|'eu-west-1'|'eu-west-2'|'ap-northeast-2'|'ap-northeast-1'|'ap-southeast-1'|'ap-southeast-2',
                'Name': 'string',
                'OutboundHostName': 'string',
                'RequireEncryption': True|False,
                'CreatedTimestamp': datetime(2015, 1, 1),
                'UpdatedTimestamp': datetime(2015, 1, 1),
                'VoiceConnectorArn': 'string'
            },
        ],
        'NextToken': 'string'
    }

The `response syntax` details indicate that the list of resources is contained within a top level field
called `VoiceConnectors` which contains an array. We can see that each element of the array contains some fields like `
VoiceConnectorId", "Name", "VoiceConnectorArn" and "CreatedTimestamp". The names of these specific fields will be needed
later, so take note.

The information we've gathered here will be used to populate the CC configuration item called `enum_spec` that we'll
encounter in a bit more detail shortly.

- Detail API

Generally, the "detail" API's will be named as "describe_xxxxx" or "get_xxxxx". In this instance the client page points
us
towards [get_voice_connector](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/chime-sdk-voice/client/get_voice_connector.html)
as the API to describe an individual voice connector resource in detail.

If we examine the "get" API then we see that a call to this API requires us to pass the Id of the voice connector in an
parameter named "VoiceConnectorId". We need to note the name of this API and this paramter name for later.

Lets take alook at the shape of the response...

    Response Syntax:
    {
        'VoiceConnector': {
            'VoiceConnectorId': 'string',
            'AwsRegion': 'us-east-1'|'us-west-2'|'ca-central-1'|'eu-central-1'|'eu-west-1'|'eu-west-2'|'ap-northeast-2'|'ap-northeast-1'|'ap-southeast-1'|'ap-southeast-2',
            'Name': 'string',
            'OutboundHostName': 'string',
            'RequireEncryption': True|False,
            'CreatedTimestamp': datetime(2015, 1, 1),
            'UpdatedTimestamp': datetime(2015, 1, 1),
            'VoiceConnectorArn': 'string'
        }
    }

Perhaps you'll notice that the shape of the "get_voice_connector" and "list_voice_connector" responses are identical.
This is sometimes the case with the AWS API's but it's not a rule by any means. In any case, CC expects us to define
both these API's in the configuration of any extension, and both API's will be used during execution of CC policies.

The information we've gathered here will be used to populate the CC configuration item called `detail_spec`, more on
that in a moment.

**We will be referring back to the information above frequently in the following discussion.**

## Creating the implementation configuration

Generally, you will start out by extending the base class `QueryResourceManager` which can be found in `c7n/query.py`.

Within your query manager class you need to define a nested class called `resource_type` that itself extends a framework
class called `TypeInfo`.

The `resource_type` nested class provides the necessary CC config for your extension and it's here we'll spent most of
our time figuring out the impl.

So, we'll be looking at the implementation file called `c7n/resources/chimesdkvoice.py` and we'll start with something
like this in that file...

    class VoiceConnector(QueryResourceManager):
    
        # interior class that defines the aws metadata for resource
        class resource_type(TypeInfo):
            ...

Our `resource_type` class has a super class called `Typeinfo` that is defined in `c7n/query.py` and our first job is to
override a load of static fields that are defined in the superclass.

Pause ...: Being an old C++ and Java/Scala programmer I find the idea of `overriding a static field` a disturbing.
My approach would have been to design this framework so that the type info was defined
as a field on the custom QueryResourceManager class and not a bunch of statics on a nested class, but hey-ho. I
think the best idea is not to worry about this strange construct too much and instead think of this pattern as if
the TypeInfo super class is like a prototype for our custom definition. By the way, some supporting evidence that this
pattern is a bit weird is that my IDE Intellij warns me about it, but at least Intellij shows a navigation from my own
class to the these static fields in TypeInfo, but when I open the same code in VSCode it doesn't give any recognition at
all that these parent class static fields exist of that I might be "overriding" them.

Anyway, if you inspect the `TypeInfo` class then you will see a ton of static fields, but you need only a fraction of
these for your impl. I added a ton of doco to the TypeInfo class when I was adding my own AWS Appmesh extension, but
only for those aspects that AWS Appmesh relied on.

My recommendation is to start with this lot ...

    @resources.register('chimesdkvoice-voiceconnector')
    class VoiceConnector(QueryResourceManager):
    
        # interior class that defines the aws metadata for resource
        class resource_type(TypeInfo):
            service     = None

            enum_spec   = None
            detail_spec = None

            id   = None
            name = None
            arn  = None
            date = None

            cfn_type    = None
            config_type = None
    
            universal_taggable = object()

## Registering your extension class

Before we get into what values to provide for those fields there is one more important feature of your
`QueryResourceManager` impl and that is registration. In the snippet above there is the `@resources.register`
annotation which contains a string that will be the Id of your resource extension, in this case I'm choosing the Id
`chimesdkvoice-voiceconnector`. The Id value that you define here will need to be added to the `resource_map.py`
to complete your registration. This id will also appear in any CC policies that are defined using your CC extension, so
choose wisely.

If we open `resource_map.py` we'll see that it contains a dict that has mappings from a name like "aws.*" to a class
name.
So since our extension has the id  `chimesdkvoice-voiceconnector` and is defined in a file called
`c7n/resources/chimesdkvoice.py` then the resource mapping record will be from `aws.chimesdkvoice-voiceconnector`
to `c7n.resources.chimesdkvoice.VoiceConnector`. Once that has been done then your extension registration is complete.

## Configuring the `resource_type` class.

- service

In the data gathering above we've already identified that the Boto3 client name is `chime-sdk-voice` so that's the value
we need to give to `service`.

    @resources.register('chimesdkvoice-voiceconnector')
    class VoiceConnector(QueryResourceManager):
    
        class resource_type(TypeInfo):
            service = "chime-sdk-voice"
            ...

- enum_spec

The enum_spec configures CC's call to the relevant "list" API and in the data gathering above we've already identified
the API call as `list_voice_connectors` and we know that the field in the response that contains all the resources is
called `VoiceConnectors`. So, we can now fill in the details of the enum_spec...

    @resources.register('chimesdkvoice-voiceconnector')
    class VoiceConnector(QueryResourceManager):
    
        class resource_type(TypeInfo):
            service = "chime-sdk-voice"

            # fields are = [ "api name", "parameter name", not used ]
            enum_spec = [ "list_voice_connectors", "VoiceConnectors", None ]

            ...

The third element in the `enum_spec` isn't relevant to us right now and it's purpose is to further tune the call to the
SDK. We aren't using it so we're passing a None as the value.

- detail_spec

We know that the detail function is called "get_voice_connector" and we know that the parameter to this call is named "
VoiceConnectorId".

We also know where to get the value of the VoiceConnectorId from because we saw that within the "list_voice_connectors"
response there is a field in the data called "VoiceConnectorId".

With this information we can extend our implementation.

    @resources.register('chimesdkvoice-voiceconnector')
    class VoiceConnector(QueryResourceManager):
    
        class resource_type(TypeInfo):
            service = "chime-sdk-voice"

            enum_spec = [ "list_voice_connectors", "VoiceConnectors", None ]

            # fields are = [ "api name", "parameter name", "name of the identity field from the list repsonse", not used]
            detail_spec = [ "get_voice_connector", "VoiceConnectorId", "VoiceConnectorId", None]

The next few things that need configuration are:

- id

The "id" config item defines the name of the field in the "enum_spec" response that contains the formal ID of the
resource.

If we refer back to the shape of the response to the "list_voice_connectors" call then we'll recall the that ID of each
resource is defined by a field called `VoiceConnectorId"

- name

Likewise we saw that the "name" of the voice connector resource can be obtained from the "Name" field contained in the "
list_voice_connectors" response.

- arn

We saw above that the ARN of the voice connector resource is conveyed in the "VoiceConnectorArn" field of the "
list_voice_connectors" response.

- date

The created date for the voice connector is ret in the "CreatedTimestamp" field of the "list_voice_connectors" response.

**With all the above known we can update our implementation**...

    @resources.register('chimesdkvoice-voiceconnector')
    class VoiceConnector(QueryResourceManager):
    
        class resource_type(TypeInfo):
            service = "chime-sdk-voice"

            enum_spec   = [ "list_voice_connectors", "VoiceConnectors", None ]
            detail_spec = [ "get_voice_connector", "VoiceConnectorId", "VoiceConnectorId", None]

            id   = "VoiceConnectorId"
            name = "Name"
            arn  = "VoiceConnectorArn"
            date = "CreatedTimestamp"

- cfn_type and config_type

cfn_type and config_type are required in some cases and not in others.

If the resource type that you are working with is known to AWS Config then we need to provide a value for
the `config_type` field that provides the AWS Config name for this resource type.
If the resource isn't known to AWS Config then this can be omitted entirely or set to None

If the resource type is known to AWS Cloud Formation then the AWS Cloud Formation name for this resource type must be
filled in via the `cfn_type` config item.

So, if look for "Voice Connector" in
the [cloud formation resource type list](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html)
and the [AWS config type list](https://docs.aws.amazon.com/config/latest/developerguide/resource-config-reference.html)
then we'll find nothing, so the correct setting for these two CC config values is None.

    @resources.register('chimesdkvoice-voiceconnector')
    class VoiceConnector(QueryResourceManager):
    
        class resource_type(TypeInfo):
            service = "chime-sdk-voice"

            enum_spec   = [ "list_voice_connectors", "VoiceConnectors", None ]
            detail_spec = [ "get_voice_connector", "VoiceConnectorId", "VoiceConnectorId", None]

            id   = "VoiceConnectorId"
            name = "Name"
            arn  = "VoiceConnectorArn"
            date = "CreatedTimestamp"

            cfn_type    = None
            config_type = None

- universal_taggable

This value controls whether Cloud Custodian will attempt to fetch the tags for the Voice Connector resources and attach
these tags to the data model for the resources. The reason we probably want this tag collection to occur is to enable
users of our extension to create policies that can filter resources according to these tags.

The correct value if we want automatic tag collection to occur is  "object()". The full set of valid values for this
config item are `"True|False|object()"`, but I won't go into any further details other than to refer you to the
documentation I placed in the TypeInfo class that explains more.

**With that we csn finalise our extension impl as** ...

    @resources.register('chimesdkvoice-voiceconnector')
    class VoiceConnector(QueryResourceManager):
    
        class resource_type(TypeInfo):
            service = "chime-sdk-voice"

            enum_spec   = [ "list_voice_connectors", "VoiceConnectors", None ]
            detail_spec = [ "get_voice_connector", "VoiceConnectorId", "VoiceConnectorId", None]

            id   = "VoiceConnectorId"
            name = "Name"
            arn  = "VoiceConnectorArn"
            date = "CreatedTimestamp"

            cfn_type    = None
            config_type = None

            universal_taggable = object()

## More info

Take a look at any notes I've left in the TypeInfo class and also in `appmesh.py` and it's test class `test_appmesh.py`

# Creating a Policy using the extension 

Let's imagine that we the implementation above has been installed in CC and we want to create a Cloud Custodian policy that detects
instances of VoiceConnector where encryption is turned off. 

We know that we used the name `aws.chimesdkvoice-voiceconnector` as the identifier for your extension in `resource_map.py`
and we need to use that ID in the CC policy file. Additionally, our research above found that the VoiceConnector 
specification has an encryption on/off flag called `RequireEncryption`. If we want to match this flag against a True/False
value then we need to use a Cloud Custodian `value` filter (see the Cloud Custodian docs).

A policy file that brings all these factors together would look like this...

    # vc_policy.yml
    policies:
    - name: my-voice-policy
      resource: aws.chimesdkvoice-voiceconnector
      filters:
      - type: value
        key: RequireEncryption
        op: eq
        value: False

The CC extension testing pattern is one where we use a policy to test the extension so why not use this exact policy as the 
basis of our test cases.

# Testing

To be honest, we can't know if the configuration above is actually viable at this point and we need to do some testing to prove this.

Of course we could simply install the extension in a CC instance and manually test it, but that's not how we roll is it!
We believe in writing automated regression tests.

Ideally, we'd have written the tests first - but there was a load to explain above about basic AWS and Cloud Custodian concepts
and how these concepts relate to each other. So, instead we've written the implementation first to allow us to discuss those ideas 
along the way. When it comes to further enhancements, or a second or third resource type, then perhaps we could use TDD instead.

## Designing our test case

The model information we collected above looks like this ...

    'VoiceConnectorId': 'string',
    'AwsRegion': 'us-east-1'|'us-west-2'|'ca-central-1'|'eu-central-1'|'eu-west-1'|'eu-west-2'|'ap-northeast-2'|'ap-northeast-1'|'ap-southeast-1'|'ap-southeast-2',
    'Name': 'string',
    'OutboundHostName': 'string',
    'RequireEncryption': True|False,
    'CreatedTimestamp': datetime(2015, 1, 1),
    'UpdatedTimestamp': datetime(2015, 1, 1),
    'VoiceConnectorArn': 'string'

A reasonable test case for our extension would be one that proves that 
- we can find VoiceConnectors based on the value of one of its properties above, and 
- when a match occurs then the expected full resource description is returned to the user

To achieve this test we can create a data test fixture with two instances of the voice connector resource 
each with a distinct specification and where one instance has encryption turned on, and the other instance turned off. 

The test case must select only the instance where encryption is turned on, and the extension must return 
a resource spec that matches the one we've setup in the test fixture. 

## Setting up the test data fixture

The CC testing pattern uses a library called [Placebo](https://github.com/garnaat/placebo) that replaces the real Boto
API and provides a method to mock up responses to the calls your extension will make to the Boto API. 
To provide the mock responses you need to create a series of files with specific names that match the name of the 
api your extension is accessing and a sequence number 1,2,3..N that identifies the order in which these files
should be returned by the mock. 

Whilst it's possible to create these mock response files by hand ot would be tedious.
Luckily Placebo provides a means to generate these files by running your extension against the real AWS and capturing
the API responses into these files as mock data to enable the tests to run off-line. 

The approach is to temporarily create instances of the relevant resources in AWS and then have CC run our test case
but in a special mode where it captures the API responses. 

## Testing "pull" mode

Our initial test case will be as follows...

    class TestAppmeshMesh(BaseTest):
      def test_appmesh(self):
         
          # standard test runner ...
          # session_factory = self.replay_flight_data('test_chimesdkvoice_voiceconnector')
      
          # test data recording runner ...
          session_factory = self.record_flight_data('test_chimesdkvoice_voiceconnector')
          
          p = self.load_policy(
              {
                  "name": "my-voice-policy",
                  "resource": "aws.chimesdkvoice-voiceconnector",
                  'filters': [
                    {
                        "type": "value",
                        "key": "RequireEncryption",
                        "op": "eq",
                        "value": "False"
                    }
                  ],
              },
              session_factory=session_factory,
          )
  
          resources = p.run()

          print(str(reources))  

We can see above that we are using the policy that we defined earlier. 

Towards the top we see `self.record_flight_data('test_chimesdkvoice_voiceconnector')` which specifies the use 
of `record_flight_data` which will cause test execution to record the responses from AWS in a test data directory 
called `tests/data/placebo/test_chimesdkvoice_voiceconnector`. 

Finally, towards the bottom we see `resources = p.run()` which is where we are actually running the test
framework and collecting the files. 

We then print out the specifications of any resources that were returned by CC.

Now go into AWS and create a pair of resources called `MyVCEncrypted` and `MyVCUnencrypted`, the first one
with encryption turned on and the other with encryption turned off, and then add a tag "MayTag=MyValue" to each resource. 

IF you then run the test above then we'll see the following files created in the Placebo test data directory 

- chimesdkvoice.ListVoiceConnectors_1.json
- chimesdkvoice.GetVoiceConnector_1.json
- chimesdkvoice.GetVoiceConnector_2.json
- tagging.GetResources_1.json

These are the 4 calls that were made. The file name is formed from a combination of the service name, the API name and the 
sequence number of the call.

If we look into the files then we can see the captured responses. The "List" file will contain an array of two voice connectors
and each of the "GetVoice" files will contain the complete description of one of the VoiceConnectors, and finally the 
"GetResources" file contains any tags that were attached by you to the test resources that you created in AWS. 

Unless we added tags to the VoiceConnectors then the tagging file will be empty and in this case we need to go back into 
AWS and add a tag to each resource and then rerun the test. We can then check that the GetResource file now contains 
the tags you added. We need the resources to have tags because we want our test to verify that any tags are correctly 
retrieved and we'll add assertions to the test for this check.  

Our test printed out the resources that were returned by the framework and we need to check this response and verify that
it contains the correct values, including the tags you added.

If you are happy with the shape of the response, the full description is there and the tags too, then you should follow that 
pattern in `test_appmesh.py` and add an assertion for this response as a regression test. 

Add something like this as the assertion, filling out all the fields in the data structure ...

    self.assertEqual(
      [
        {'Tags': [{'Key': 'MyTag', 'Value': 'MyValue'}],
        'c7n:MatchedFilters': ['RequireEncryption'],
        'Name': 'MyVCEencrypted',        
        'VoiceConenctorArn': 'arn:aws:XXXXX TODO TODO',
        ..... etc
      ],
      resources,
    )

As per `test_appmesh.py` the next assertion should be one for the `get_arns` function and if you look at the `test_appmesh.py` 
then hopefully it is self explanatory.

Finally, I recommend that you add an assertion that verifies the calls, including parameter values, that are made by your plugin. 
To achieve this we need to modify the test to capture the calls that are being made by CC. We can achieve this using the
`ApiCallCaptor` utility; apply it as shonn below ...

      captor = ApiCallCaptor.start_capture()
      resources = p.run()

We can now add a final assertion to the bottom of our test case. This will make a strong assertion on the specific
calls made by CC.

      self.assertEqual(
          [
              {'operation': 'ListVoiceConnectors', 'params': {}, 'service': 'chimesdkvoice'},
              {'operation': 'GetVoiceConnector', 'params': {'VoiceConnectorId': 'TODO!!!'}, 'service': 'chimesdkvoice'},
              {'operation': 'GetVoiceConnector', 'params': {'VoiceConnectorId': 'TODO!!!'}, 'service': 'chimesdkvoice'},
              {
                  'operation': 'GetResources',
                  'params': {
                      'ResourceARNList': [
                          'arn:aws:XXX TODO TODO',
                          'arn:aws:XXX TODO TODO',
                      ]
                  },
                  'service': 'resourcegroupstaggingapi',
              },
          ],
          captor.calls,
      )

## Push your changes to Cloud Custodian GitHub.com

As per the Cloud Custodian developer documentation mentioned right at the top of this page, you need to 
setup you dev end and have these two command pass cleanly before requesting a PR back to the main branch of the product.

    make lint
    make test


If we've gotten this far and can run the tests and it all passes, then you are in great shape and should consider
asking for a review and advice on a pull request; even if you aren't fully finished.

We will extend the test to cover "Event" mode, but there is benefit in pushing this MVP and hopefully getting some
review feedback from the maintainers of CC.


# Adding Event support 

TODO 
 
========================= END ========================
