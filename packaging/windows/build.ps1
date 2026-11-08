# Native x86-64 Windows runner, only after the spec-04A reviewed main freeze.
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot "../.."))
if (-not $env:STUDIO_RELEASE_SHA) { throw "Freeze STUDIO_RELEASE_SHA after PR merge." }
if ((git rev-parse HEAD).Trim() -ne $env:STUDIO_RELEASE_SHA) { throw "Wrong source HEAD." }
if ((git status --porcelain)) { throw "Checkout must be clean." }
if (-not [Environment]::Is64BitProcess) { throw "Windows x86-64 Python required." }
python -m pip install -r packaging/requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw "Toolchain installation failed." }
New-Item -ItemType Directory -Force build/release-wheels, build/source-dist | Out-Null
gh release download v0.1.0a1 --repo darizae/alp-ui --pattern "alp_ui-0.1.0a1-py3-none-any.whl" --dir build/release-wheels
if ($LASTEXITCODE -ne 0) { throw "alp-ui release download failed." }
gh release download v0.3.0 --repo darizae/bioacoustics-dl-toolbox --pattern "bioacoustics_dl_toolbox-0.3.0-py3-none-any.whl" --dir build/release-wheels
if ($LASTEXITCODE -ne 0) { throw "toolbox release download failed." }
python -m pip install --no-deps (Get-ChildItem build/release-wheels/*.whl | ForEach-Object FullName)
if ($LASTEXITCODE -ne 0) { throw "Upstream installation failed." }
python -m build --wheel --outdir build/source-dist
if ($LASTEXITCODE -ne 0) { throw "Studio wheel build failed." }
python -m pip install -c packaging/constraints-native.txt (Get-ChildItem build/source-dist/biocall_studio-0.1.0a1-*.whl | Select-Object -ExpandProperty FullName)
if ($LASTEXITCODE -ne 0) { throw "Studio installation failed." }
python -m pip check
if ($LASTEXITCODE -ne 0) { throw "Dependency conflict." }
python packaging/shared/verify_inputs.py --frozen --wheelhouse build/release-wheels
if ($LASTEXITCODE -ne 0) { throw "Input verification failed." }
python -m pip freeze | Set-Content build/windows-installed-python-freeze.txt
python -m PyInstaller --noconfirm --clean --distpath dist/native-windows --workpath build/pyinstaller-windows packaging/windows/biocall.spec
if ($LASTEXITCODE -ne 0) { throw "Freezer failed." }
$root = "dist/native-windows/BioCall Studio"
foreach ($name in @("BioCall Studio.exe", "BioCall Studio Worker.exe")) {
    if (-not (Test-Path (Join-Path $root $name))) { throw "Missing $name" }
}
$iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue)
if (-not $iscc) { throw "Install Inno Setup 6 and put ISCC.exe on PATH." }
& $iscc.Source packaging/windows/biocall.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup installer compilation failed." }
Get-FileHash -Algorithm SHA256 assets/branding/icons/icon.ico, dist/native-windows-installer/*.exe
Write-Warning "DEVELOPMENT-ONLY until Windows signature, legal review and native installed smoke gates clear."
