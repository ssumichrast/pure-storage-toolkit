#Requires -Modules PureStoragePowerShellSDK

<#
    .SYNOPSIS
    Generate MDS Device Alias syntax from a FlashArray

    .DESCRIPTION
    Connects to a Pure Storage FlashArray and generates Cisco MDS syntax that
    can be used to add a FlashArray's FC ports to the device-alias database.

    .PARAMETER FlashArray
    FQDN of the Pure Storage FlashArray device to connect to.

    .PARAMETER AllPorts
    Using this switch will have the script return all ports regardless of their
    link state.

    .EXAMPLE
    .\Get-PureDeviceAlias.ps1 -FlashArray flasharray.domain.lcl

    .NOTES
    Author: Steven Sumichrast <steven.sumichrast@gmail.com>
#>
param(
    [parameter(Mandatory = $true)]
    [string]$FlashArray,
    [switch]$AllPorts
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
    $pfa = New-PfaArray -EndPoint $FlashArray -Credentials $credentials -HttpTimeOutInMilliSeconds 120000 -IgnoreCertificateError
    Write-Verbose "Connected to array"
}
catch {
    throw $_
}

# Get the array hostname
$PFAName = (Get-PfaArrayAttributes -Array $pfa).array_name

# Gather the HBA WWPN's off the FlashArray.
# If user passed -allports parameter obtain all of the ports regardless of state
# Otherwise, only grab ports reporting connected
$PFAPorts = if ($AllPorts) {
    Write-Verbose " Obtaining all PFA Ports"
    Get-PfaArrayPorts -Array $Pfa
}
else {
    Write-Verbose " Obtaining online PFA Ports"
    Get-PfaArrayPorts -Array $Pfa | ForEach-Object -Process {
        if ((Get-PfaHardwareAttributes -Array $pfa -Name $_.Name).speed -gt 0) {
            return $_
        }
    }
}

# Obtain the "A" side ports (Even number FC ports)
Write-Host -ForegroundColor Red "A-Fabric Ports"
$PFAPorts | Where-Object { $_.name.substring($_.name.length - 1) % 2 -eq 0 } | ForEach-Object -Process {
    $wwn = $_.wwn
    $Port = @{
        Name = $_.Name
        WWPN = (0..7 | ForEach-Object { $wwn.Substring($_ * 2, 2) }) -join ':'
    }
    Write-Host "device-alias name $($PFAName.toUpper())_$(($Port.Name).replace('.','-')) pwwn $($Port.WWPN)"
}
Write-Host ""

# Obtain the "B" side ports (Odd number FC ports)
Write-Host -ForegroundColor Red "B-Fabric Ports"
$PFAPorts | Where-Object { $_.name.substring($_.name.length - 1) % 2 -eq 1 } | ForEach-Object -Process {
    $wwn = $_.wwn
    $Port = @{
        Name = $_.Name
        WWPN = (0..7 | ForEach-Object { $wwn.Substring($_ * 2, 2) }) -join ':'
    }
    Write-Host "device-alias name $($PFAName.toUpper())_$(($Port.Name).replace('.','-')) pwwn $($Port.WWPN)"
}
# Disconnect from the array
Disconnect-PfaArray -Array $Pfa