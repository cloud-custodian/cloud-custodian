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
$base = "$env:LOCALAPPDATA\custodian"

try
{
    # Ensure folder
    md -Force $base | Out-Null

    # Download
    Invoke-WebRequest -OutFile "$base\custodian-cask.exe" "$url"

    # Add to path
    if($env:Path -like "*$base*") {
        Write-Host "Not modifying path because it appears to already contain Cask."
    }
    else {
        [Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path", [EnvironmentVariableTarget]::User) + ";$base\", [EnvironmentVariableTarget]::User)
        Write-Host "Path updated to contain: $base"
    }

    # Refresh path in current session
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

    Write-Host "Cask installed to $base and environment refreshed.`nTry running 'custodian-cask schema'."
}
catch
{
    echo "Installation failed.  Please file a Github issue if you need help."
    echo $_.Exception|format-list -force
    Break
}
