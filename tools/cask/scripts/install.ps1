# Copyright 2019 Microsoft Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http:#www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Windows PowerShell Installation Helper for Custodian Cask

# Variables
$url = "https://cloudcustodian.io/downloads/custodian-cask/windows-latest/custodian-cask.exe"

try
{
    # Download
    Invoke-WebRequest -OutFile "$env:LOCALAPPDATA\custodian\custodian-cask.exe" "$url"

    # Add to path
    [Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path", [EnvironmentVariableTarget]::User) + ";$env:LOCALAPPDATA\custodian\", [EnvironmentVariableTarget]::User)

    # Refresh path in current session
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}
catch
{
    echo "Installation failed.  Please file a Github issue if you need help."
    echo $_.Exception|format-list -force
    Break
}
