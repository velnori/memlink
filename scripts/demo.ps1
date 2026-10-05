param(
    [Parameter(Mandatory = $true)][string]$OutputDirectory,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
& $Python -m memlink.demo --out $OutputDirectory
if ($LASTEXITCODE -ne 0) { throw "Synthetic demo failed: exit $LASTEXITCODE" }
