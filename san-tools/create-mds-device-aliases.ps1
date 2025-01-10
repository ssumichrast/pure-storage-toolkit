#Requires -Modules PureStoragePowerShellSDK2

<#
    .SYNOPSIS
    Generate MDS Device Alias syntax from a FlashArray

    .DESCRIPTION
    Connects to a Pure Storage FlashArray and generates Cisco MDS syntax that
    can be used to add a FlashArray's FC ports to the device-alias database.

    .PARAMETER FlashArray
    FQDN of the Pure Storage FlashArray device to connect to.

    .EXAMPLE
    .\Get-PureDeviceAlias.ps1 -FlashArray flasharray.domain.lcl

    .NOTES
    Author: Steven Sumichrast <steven.sumichrast@gmail.com>
#>
param(
    [parameter(Mandatory = $true)]
    [string]$FlashArray
)

# Attempt to connect to the FlashArray
try {
    # Obtain Credentials
    Write-Verbose "Obtaining Credentials"
    if (!($credentials)) {
        $credentials = Get-Credential -Message "FlashArray Login"
    }
    Write-Verbose "Credentials Stored"
    Write-Verbose "Attempting to connect to array"
    $pfa = Connect-Pfa2Array -Endpoint $FlashArray -Credential $credentials -IgnoreCertificateError
    Write-Verbose "Connected to array"
	
    # Obtain the array name
    $PFAName = (Get-Pfa2Array -Array $pfa).name.toUpper()
}
catch {
    throw $_
}

# Obtain all of the FA target FC ports
# Note: ideally we would use '-filter "target.wwn"' which would only return FC ports. However, as of 6.8.2 this is bugged. If a FC port is down the array will simply not include it in the returned port list. Not ideal. For now, have to use PowerShell object filtering.
#$output = Get-Pfa2Port -array $pfa -filter "target.wwn" | ForEach-Object -Process {
$output = Get-Pfa2Port -Array $pfa | Where-Object { $_.Wwn } | ForEach-Object -Process {
    [PSCustomObject]@{
        Name   = $_.Name.replace('.', '-')
        WWPN   = $_.Wwn
        # Here we divide the last number of the interface name by 2. If it's evenly divisible then it's an A side port. Otherwise it's B side.
        Fabric = $(if ($_.name.substring($_.name.length - 1) % 2 -eq 0 ) { "A" } else { "B" })
    }
} | Group-Object -Property Fabric

# Disconnect from the array
Disconnect-Pfa2Array -Array $Pfa

Write-Host -ForegroundColor Yellow -Message "$($PFAName) FC Interfaces: Device Alias Entries"

# Iterate over the results to generate the device-alias commands and output to the console
$output | ForEach-Object -Process {
    Write-Host -ForegroundColor Red "Fabric $($_.Name) Device-Alias Entries"
    Write-Host -ForegroundColor Red "--------------------------------------"
    $_.group | ForEach-Object -Process {
        Write-Host "device-alias name $($PFANAME)_$($_.name) pwwn $($_.WWPN)"
    }
    Write-Host ""
	
    Write-Host -ForegroundColor Red "Fabric $($_.Name) Zone Member Entries"
    Write-Host -ForegroundColor Red "--------------------------------------"
    $_.group | ForEach-Object -Process {
        Write-Host "member device-alias $($PFANAME)_$($_.name) target"
    }
    Write-Host ""
}

Write-Host -ForegroundColor Yellow -Message "INSTRUCTIONS:"
Write-Host "Log on to the MDS switch for the corresponding fabric via SSH."
Write-Host "Enter configuration mode: config t"
Write-Host "Enter the device-alias database: device-alias database"
Write-Host "Paste in the device-alias lines for the respective fabric above."
Write-Host "Review the device-alias database changes: device-alias pending-diff"
Write-Host "Commit the device-alias database changes: device-alias commit"
Write-Host "Optionally you can use the output for the member section to paste into a zoneset using Smart Zoning."