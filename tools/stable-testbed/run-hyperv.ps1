$ErrorActionPreference = 'Stop'
python tools/stable-testbed/controller.py --gate hyperv --controller-path tools/stable-testbed/run-hyperv.ps1
if ($LASTEXITCODE -ne 0) { throw "Hyper-V Stable controller failed" }
