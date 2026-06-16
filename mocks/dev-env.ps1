# Sourcing this file in PowerShell sets up Dispatch against local fakes.
# Usage: . .\mocks\dev-env.ps1

$MocksDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $MocksDir
$MocksBin = Join-Path $MocksDir "bin"

function Get-PythonLauncher {
    foreach ($Candidate in @("py", "python", "python3")) {
        $Command = Get-Command $Candidate -ErrorAction SilentlyContinue
        if ($Command) {
            return $Command.Source
        }
    }
    return $null
}

$PythonLauncher = Get-PythonLauncher

# Set environment variables for PowerShell session
$env:DISPATCH_MOCKS_DIR = $MocksDir
if (-not $env:DISPATCH_DATA_ROOT) {
    $env:DISPATCH_DATA_ROOT = Join-Path $env:TEMP "ads_storage\dispatch"
}
if (-not $env:DISPATCH_MOCK_SCENARIO) {
    $env:DISPATCH_MOCK_SCENARIO = "happy_path"
}
if (-not $env:DISPATCH_MOCK_STATE_DIR) {
    $env:DISPATCH_MOCK_STATE_DIR = Join-Path $env:TEMP "dispatch_mock_state"
}
if (-not $env:MAILHOST) {
    $env:MAILHOST = "127.0.0.1:2525"
}
if (-not $env:DISPATCH_SCR_DIR) {
    $env:DISPATCH_SCR_DIR = Join-Path $ProjectDir "scr"
}

# Prepend mocks/bin to the session PATH if not already present
if ($env:PATH -notlike "*$MocksBin*") {
    $env:PATH = "$MocksBin;$env:PATH"
}

# Create required directories
New-Item -ItemType Directory -Force -Path (Join-Path $env:DISPATCH_DATA_ROOT ".dispatch\jobs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $MocksDir "sent_emails") | Out-Null
New-Item -ItemType Directory -Force -Path $env:DISPATCH_MOCK_STATE_DIR | Out-Null

# Compile mock .exe wrappers if they don't exist yet on Windows
$CscPath = "C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
$Exes = @("impala-shell.exe", "klist.exe", "kinit.exe")
$NeedsCompile = $false
foreach ($Exe in $Exes) {
    if (-not (Test-Path (Join-Path $MocksBin $Exe))) {
        $NeedsCompile = $true
    }
}

if ($NeedsCompile -and (Test-Path $CscPath)) {
    Write-Host "Compiling native Windows mock wrappers..." -ForegroundColor Cyan
    if (-not $PythonLauncher) {
        throw "Unable to find a Python launcher for Windows mock wrappers."
    }
    $EscapedPythonLauncher = $PythonLauncher.Replace("\", "\\").Replace('"', '\"')
    $SourceCode = @"
using System;
using System.Diagnostics;
using System.IO;
using System.Text;

class Wrapper {
    static int Main(string[] args) {
        string exePath = typeof(Wrapper).Assembly.Location;
        string exeDir = Path.GetDirectoryName(exePath);
        string exeName = Path.GetFileNameWithoutExtension(exePath);
        
        if (exeName == "kinit") {
            Console.WriteLine("mock kinit accepted");
            return 0;
        }
        
        string scriptName = exeName;
        string scriptPath = Path.Combine(exeDir, scriptName);
        
        // Setup python start info
        ProcessStartInfo startInfo = new ProcessStartInfo();
        startInfo.FileName = "$EscapedPythonLauncher";
        
        // Escape arguments for the command line
        StringBuilder arguments = new StringBuilder();
        arguments.AppendFormat("\"{0}\"", scriptPath);
        foreach (string arg in args) {
            arguments.Append(" ");
            arguments.Append(EscapeArg(arg));
        }
        startInfo.Arguments = arguments.ToString();
        
        startInfo.UseShellExecute = false;
        startInfo.CreateNoWindow = true;
        startInfo.RedirectStandardOutput = true;
        startInfo.RedirectStandardError = true;
        
        using (Process proc = new Process()) {
            proc.StartInfo = startInfo;
            proc.Start();
            string stdout = proc.StandardOutput.ReadToEnd();
            string stderr = proc.StandardError.ReadToEnd();
            proc.WaitForExit();
            if (!string.IsNullOrEmpty(stdout)) {
                Console.Out.Write(stdout);
            }
            if (!string.IsNullOrEmpty(stderr)) {
                Console.Error.Write(stderr);
            }
            return proc.ExitCode;
        }
    }
    
    static string EscapeArg(string arg) {
        if (string.IsNullOrEmpty(arg)) return "\"\"";
        if (arg.Contains("\"")) {
            return "\"" + arg.Replace("\"", "\\\"") + "\"";
        }
        if (arg.Contains(" ") || arg.Contains("|") || arg.Contains(";") || arg.Contains("&")) {
            return "\"" + arg + "\"";
        }
        return arg;
    }
}
"@
    $TempCs = Join-Path $MocksBin "wrapper_temp.cs"
    Set-Content -Path $TempCs -Value $SourceCode
    
    $ImpalaWrapper = Join-Path $MocksBin "impala-shell.exe"
    $KlistWrapper = Join-Path $MocksBin "klist.exe"
    $KinitWrapper = Join-Path $MocksBin "kinit.exe"

    & $CscPath "/out:$ImpalaWrapper" $TempCs | Out-Null
    & $CscPath "/out:$KlistWrapper" $TempCs | Out-Null
    & $CscPath "/out:$KinitWrapper" $TempCs | Out-Null
    
    Remove-Item -Force $TempCs
}

# Start the SMTP mock server if not already running on port 2525
$SmtpRunning = $true
try {
    $SmtpTest = New-Object System.Net.Sockets.TcpClient
    $SmtpTest.Connect("127.0.0.1", 2525)
    $SmtpTest.Close()
} catch {
    $SmtpRunning = $false
}

if (-not $SmtpRunning) {
    if ($PythonLauncher) {
        Write-Host "Starting SMTP mock server..." -ForegroundColor Cyan
        $SmtpScript = Join-Path $MocksDir "smtpd.py"
        $EmailsDir = Join-Path $MocksDir "sent_emails"
        Start-Process $PythonLauncher -ArgumentList "`"$SmtpScript`" `"$EmailsDir`"" -NoNewWindow
    }
}

# Clean-up / restore function
function Restore-Mocks {
    $MocksBin = Join-Path $env:DISPATCH_MOCKS_DIR "bin"
    $Exes = @("impala-shell.exe", "klist.exe", "kinit.exe")
    foreach ($Exe in $Exes) {
        $Path = Join-Path $MocksBin $Exe
        if (Test-Path $Path) {
            Remove-Item -Force $Path
        }
    }
    Write-Host "Windows native mock wrappers removed successfully." -ForegroundColor Green
}

Write-Host "Dispatch PowerShell dev mode enabled:" -ForegroundColor Green
Write-Host "  DISPATCH_DATA_ROOT = $env:DISPATCH_DATA_ROOT"
Write-Host "  DISPATCH_MOCK_SCENARIO = $env:DISPATCH_MOCK_SCENARIO"
Write-Host "  MAILHOST = $env:MAILHOST"
Write-Host "  Run 'Restore-Mocks' to revert temporary Windows fakes." -ForegroundColor Yellow
