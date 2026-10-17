# P4 启动脚本（PowerShell）
# 用法：
#   .\run.ps1                 # 打开界面
#   .\run.ps1 --check         # 跑自检
#   .\run.ps1 --smoke _smoke\a.ps
#
# 如果系统禁止执行脚本，可临时用：
#   powershell -ExecutionPolicy Bypass -File .\run.ps1 --check

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    & $python.Source main.py @args
    exit $LASTEXITCODE
}

# 没有 python 命令时，试试 Windows 自带的 py 启动器
$launcher = Get-Command py -ErrorAction SilentlyContinue
if ($launcher) {
    & $launcher.Source -3 main.py @args
    exit $LASTEXITCODE
}

Write-Host "[ERROR] 找不到 python。请安装 Python 3.10+ 并加入 PATH。" -ForegroundColor Red
exit 1
