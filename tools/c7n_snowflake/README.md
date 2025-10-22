# c7n_snowflake
A Snowflake provider for Cloud Custodian

## Installation
Follow the steps in the Cloud Custodian README to get started:

tl;dr:

```shell
make install
```

Login to Snowflake and make note of the following:
1. Snowflake Username
2. Snowflake Account ID
3. Snowflake API Key

Set the following environment variables:

```shell
export SNOWFLAKE_USERNAME=$USERNAME
export SNOWFLAKE_ACCOUNT=$ACCOUNTID
export SNOWFLAKE_API_KEY=$SNOWFLAKE_API_KEY
```

If you want to use a role for your custodian policies, you can
create a role in Snowflake called `C7N`:

```sql
CREATE ROLE IF NOT EXISTS C7N
```

Grant yourself acccess to use that role:

```sql
GRANT ROLE c7n to USER $USERNAME
```

Then, export the role as an environment variable:

```shell
export SNOWFLAKE_ROLE=C7N
```

Next, make sure you have appropriate network access to run Cutodian policies. You
will need to ensure that your IP address is allowed to execute against your Snowflake
account. You can check these settings in Admin -> Security -> Network Policies in
the Snowflake console.

### Tags

Tags in Snowflake must be associated to a database and a schema. To retrieve
tags make sure you have a database and schema set up to manage your tags. In
this example, we will create a database called C7N that will contain your
tags, using the public schema.

```sql
CREATE DATABASE C7N;
```

Next, if you want to retrieve tags from your Snowflake resources and
grant that role access to your Tag database.

```sql
GRANT USAGE ON DATABASE C7N TO ROLE C7N
GRANT USAGE ON SCHEMA IDENTIFIER('"C7N"."PUBLIC"') TO ROLE IDENTIFIER('"C7N"')
GRANT CREATE TAG ON FUTURE SCHEMAS IN DATABASE IDENTIFIER('"C7N"') TO ROLE IDENTIFIER('"C7N"')
```

Tags must be first created in Snowflake before added to resources. you can allow
Custodian to create those tags on your behalf.

```sql
GRANT CREATE TAG ON SCHEMA c7n.public TO ROLE c7n
```

For Cloud Custodian to look up tags, set the following environment variable:

```sql
export SNOWFLAKE_TAG_DATABASE=$TAG_DATABASE
```

### Action Permissions

The ability to take action on resources (e.g. modify) may depend on a per resource
basis. Thus, you will need to enable permissions on each individual resource
like so:

```sql
GRANT MODIFY ON WAREHOUSE $WAREHOUSE TO ROLE C7N
```
