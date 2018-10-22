## Storage Queue Binding Support for Azure Functions

Azure functions storage queue binding support requires installing the dotnet storage queue extension. In order to publish this with the function the dlls need to be added locally. This directory contains the necessary files for the binding support to be published with the Azure Function.

To update the files ensure [dotnet is installed](https://www.microsoft.com/net/download) on your local machine. Then run the following command from the root directory:

`dotnet build tools/c7n_azure/c7n_azure/function_binding_resources/extensions.csproj --configuration Release --output bin`
 