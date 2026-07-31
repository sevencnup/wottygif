$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $repoRoot 'backend'
$frontendRoot = Join-Path $repoRoot 'frontend'
$backendPython = Join-Path $backendRoot '.venv\Scripts\python.exe'
$backendLog = Join-Path $repoRoot 'backend-dev.log'
$backendErrLog = Join-Path $repoRoot 'backend-dev.err.log'
$backendCommand = $null
$backendArguments = @('-m', 'uvicorn', 'app.main:app', '--reload', '--host', '127.0.0.1', '--port', '8000')

if (Test-Path -LiteralPath $backendPython) {
  $backendCommand = $backendPython
} else {
  $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
  $pyCommand = Get-Command py -ErrorAction SilentlyContinue

  if ($pythonCommand) {
    $backendCommand = $pythonCommand.Source
  } elseif ($pyCommand) {
    $backendCommand = $pyCommand.Source
  } else {
    throw "Python was not found. Create backend\\.venv or install Python first."
  }

  Write-Host "backend\\.venv not found. Falling back to system Python: $backendCommand"
}

if (-not (Test-Path -LiteralPath $frontendRoot)) {
  throw "Missing frontend directory at $frontendRoot."
}

$backendProcess = Start-Process `
  -FilePath $backendCommand `
  -ArgumentList $backendArguments `
  -WorkingDirectory $backendRoot `
  -RedirectStandardOutput $backendLog `
  -RedirectStandardError $backendErrLog `
  -PassThru `
  -WindowStyle Hidden

Write-Host "Backend started on http://127.0.0.1:8000 (PID: $($backendProcess.Id))"

try {
  $backendReady = $false

  for ($attempt = 0; $attempt -lt 40; $attempt++) {
    if ($backendProcess.HasExited) {
      break
    }

    try {
      $health = Invoke-RestMethod `
        -Uri 'http://127.0.0.1:8000/api/health' `
        -TimeoutSec 1

      if ($health.status -eq 'ok') {
        $backendReady = $true
        break
      }
    }
    catch {
      Start-Sleep -Milliseconds 250
    }
  }

  if (-not $backendReady) {
    if (Test-Path -LiteralPath $backendErrLog) {
      $backendError = Get-Content -LiteralPath $backendErrLog -Raw
      if ($backendError) {
        Write-Host $backendError -ForegroundColor Red
      }
    }

    throw "Backend failed to become ready. See $backendErrLog"
  }

  Write-Host "Backend is ready."
  Write-Host "Frontend starting on http://127.0.0.1:5173"
  & pnpm --dir $frontendRoot dev
}
finally {
  if ($backendProcess -and -not $backendProcess.HasExited) {
    Stop-Process -Id $backendProcess.Id
    Write-Host "Backend stopped."
  }
}
