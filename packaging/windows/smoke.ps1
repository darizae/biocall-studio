# Run after a genuine Inno Setup installation outside the checkout.
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot "../.."))
$installed = if ($args.Count -gt 0) { $args[0] } else { Join-Path $env:ProgramFiles "BioCall Studio" }
if (-not (Test-Path (Join-Path $installed "BioCall Studio Worker.exe"))) {
    throw "Install BioCall Studio with Inno Setup before running the native smoke."
}
python packaging/shared/native_smoke.py --gui (Join-Path $installed "BioCall Studio.exe") --worker (Join-Path $installed "BioCall Studio Worker.exe")
if ($LASTEXITCODE -ne 0) { throw "Native installed-binary smoke failed." }
