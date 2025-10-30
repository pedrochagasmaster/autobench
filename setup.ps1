# Setup script for Privacy-Compliant Benchmarking Tool
# Run this script to set up the tool and verify installation

Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 79) -ForegroundColor Cyan
Write-Host "Privacy-Compliant Benchmarking Tool - Setup" -ForegroundColor Cyan
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 79) -ForegroundColor Cyan
Write-Host ""

# Check Python installation
Write-Host "Checking Python installation..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "  Found: $pythonVersion" -ForegroundColor Green
    
    # Check if Python 3.8+
    if ($pythonVersion -match "Python 3\.([0-9]+)") {
        $minorVersion = [int]$matches[1]
        if ($minorVersion -lt 8) {
            Write-Host "  Warning: Python 3.8 or higher is recommended" -ForegroundColor Yellow
        }
    }
} catch {
    Write-Host "  ERROR: Python not found. Please install Python 3.8 or higher." -ForegroundColor Red
    exit 1
}

Write-Host ""

# Check pip
Write-Host "Checking pip..." -ForegroundColor Yellow
try {
    $pipVersion = pip --version 2>&1
    Write-Host "  Found: $pipVersion" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: pip not found. Please install pip." -ForegroundColor Red
    exit 1
}

Write-Host ""

# Install dependencies
Write-Host "Installing dependencies..." -ForegroundColor Yellow
Write-Host "  This may take a few minutes..." -ForegroundColor Gray

try {
    pip install -r requirements.txt
    Write-Host "  Dependencies installed successfully!" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: Failed to install dependencies" -ForegroundColor Red
    Write-Host "  Try manually: pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Create directories if they don't exist
Write-Host "Setting up directories..." -ForegroundColor Yellow

$directories = @("examples", "output", "logs")

foreach ($dir in $directories) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
        Write-Host "  Created: $dir/" -ForegroundColor Green
    } else {
        Write-Host "  Exists: $dir/" -ForegroundColor Gray
    }
}

Write-Host ""

# Run tests
Write-Host "Running installation tests..." -ForegroundColor Yellow
Write-Host ""

try {
    python test_installation.py
    $testResult = $LASTEXITCODE
} catch {
    Write-Host "  ERROR: Could not run tests" -ForegroundColor Red
    $testResult = 1
}

Write-Host ""

# Summary
if ($testResult -eq 0) {
    Write-Host "=" -NoNewline -ForegroundColor Green
    Write-Host ("=" * 79) -ForegroundColor Green
    Write-Host "Setup Complete!" -ForegroundColor Green
    Write-Host "=" -NoNewline -ForegroundColor Green
    Write-Host ("=" * 79) -ForegroundColor Green
    Write-Host ""
    Write-Host "Quick Start:" -ForegroundColor Cyan
    Write-Host "  1. Read the quick start guide: QUICKSTART.md" -ForegroundColor White
    Write-Host "  2. List available presets:" -ForegroundColor White
    Write-Host "     python benchmark_cli.py list-presets" -ForegroundColor Gray
    Write-Host "  3. Run a sample analysis:" -ForegroundColor White
    Write-Host "     python benchmark_cli.py rate --csv examples\sample_full_schema.csv --entity Bank_A --dimension region" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Documentation:" -ForegroundColor Cyan
    Write-Host "  - QUICKSTART.md       : Quick start guide" -ForegroundColor White
    Write-Host "  - README_CLI.md       : Complete CLI reference" -ForegroundColor White
    Write-Host "  - TECHNICAL_SPECIFICATION.md : Technical details" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host "=" -NoNewline -ForegroundColor Red
    Write-Host ("=" * 79) -ForegroundColor Red
    Write-Host "Setup Incomplete" -ForegroundColor Red
    Write-Host "=" -NoNewline -ForegroundColor Red
    Write-Host ("=" * 79) -ForegroundColor Red
    Write-Host ""
    Write-Host "Some tests failed. Please check the output above." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To troubleshoot:" -ForegroundColor Cyan
    Write-Host "  1. Ensure all dependencies installed: pip install -r requirements.txt" -ForegroundColor White
    Write-Host "  2. Check Python version: python --version (need 3.8+)" -ForegroundColor White
    Write-Host "  3. Re-run setup: .\setup.ps1" -ForegroundColor White
    Write-Host ""
}

Write-Host "For help, run: python benchmark_cli.py --help" -ForegroundColor Cyan
Write-Host ""
