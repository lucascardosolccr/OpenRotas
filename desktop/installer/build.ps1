# ============================================================================
#  OpenRotas Desktop — build reproduzível do instalador (Windows PowerShell).
#  Processo (§36): limpa -> valida -> empacota (PyInstaller onedir) -> gera instalador
#  (Inno Setup) -> valida integridade. Rode da pasta  desktop\  :
#      cd desktop
#      powershell -ExecutionPolicy Bypass -File installer\build.ps1
# ============================================================================
$ErrorActionPreference = "Stop"
$ROOT   = Split-Path -Parent $PSScriptRoot      # ...\desktop
$REPO   = Split-Path -Parent $ROOT              # ...\OpenRotas
$VENV   = Join-Path $REPO "venv\Scripts"
Write-Host "[build] repo=$REPO"

# 1) limpar builds anteriores
Write-Host "[build] limpando build/ anterior..."
Remove-Item -Recurse -Force (Join-Path $ROOT "build") -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force (Join-Path $ROOT "installer\dist_installer") -ErrorAction SilentlyContinue

# 2) validar dependências
if (-not (Test-Path (Join-Path $VENV "python.exe"))) {
  Write-Host "[build] criando venv e instalando dependencias..."
  & py -3.12 -m venv (Join-Path $REPO "venv")
  & (Join-Path $VENV "python.exe") -m pip install --upgrade pip
  & (Join-Path $VENV "python.exe") -m pip install -r (Join-Path $ROOT "requirements-desktop.txt")
}

# 2.5) gerar o ícone do app/instalador (§38) — best-effort; segue sem ele se Pillow faltar.
Write-Host "[build] gerando icone (openrotas.ico)..."
& (Join-Path $VENV "python.exe") (Join-Path $ROOT "installer\make_icon.py") (Join-Path $ROOT "installer\openrotas.ico")

# 3) empacotar (PyInstaller onedir) — saída em desktop\build\dist\OpenRotas\
Write-Host "[build] empacotando com PyInstaller (onedir)..."
Push-Location $ROOT
& (Join-Path $VENV "pyinstaller.exe") "packaging\launcher.spec" --noconfirm `
    --distpath "build\dist" --workpath "build\work"
Pop-Location

$exe = Join-Path $ROOT "build\dist\OpenRotas\OpenRotas.exe"
if (-not (Test-Path $exe)) { throw "[build] FALHA: $exe nao foi gerado." }

# 4) teste de integridade do bundle (roda o diagnostico do proprio exe)
Write-Host "[build] validando integridade do bundle..."
& $exe "--diagnostico" "--silencioso"
if ($LASTEXITCODE -ne 0) { Write-Warning "[build] diagnostico apontou itens faltando (ver saida)." }

# 5) gerar o instalador (Inno Setup). Requer o ISCC.exe instalado.
$iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (Test-Path $iscc) {
  # Versão do instalador = desktop_config.APP_VERSION (fonte única — §19/§38).
  $ver = & (Join-Path $VENV "python.exe") -c "import sys; sys.path.insert(0,'app'); import desktop_config as c; print(c.APP_VERSION)"
  if (-not $ver) { $ver = "0.1.0" }
  Write-Host "[build] gerando instalador com Inno Setup (versao $ver)..."
  Push-Location $ROOT
  & $iscc "/DAppVersion=$ver" "installer\openrotas.iss"
  Pop-Location
  Write-Host "[build] OK -> desktop\installer\dist_installer\OpenRotas Setup.exe"
} else {
  Write-Warning "[build] Inno Setup nao encontrado. Instale em https://jrsoftware.org/isdl.php e rode de novo."
  Write-Host    "[build] O bundle onedir ja esta pronto em: $($ROOT)\build\dist\OpenRotas\"
}
