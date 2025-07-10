<#
.SYNOPSIS
    A PowerShell GUI wrapper for the benchmark_tool.py Python script.

.DESCRIPTION
    This script provides a user-friendly Windows Forms interface to run the benchmark analysis tool.
    It allows users to configure all necessary parameters for both 'rate' and 'share' analysis types,
    select either a CSV or SQL data source, execute the Python script, and view its output in real-time.

.NOTES
    Author: Gemini
    Date:   2024-07-10
    Version: 8.0

    Prerequisites:
    1. PowerShell 5.1 or later.
    2. .NET Framework 4.5 or later.
    3. A Python environment with all dependencies for `benchmark_tool.py` installed (pandas, numpy, pypyodbc, etc.).
    4. The `python` executable must be in your system's PATH environment variable.
    5. This PowerShell script (`.ps1`) and the `benchmark_tool.py` script should be in the same directory.
#>

# --- SCRIPT CONFIGURATION ---
# The path to the Python script. Assumes it's in the same directory as this PS1 file.
$pythonScriptPath = Join-Path $PSScriptRoot "benchmark_tool.py"

# --- GUI SETUP ---

# Load the required Windows Forms assembly
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# --- FORM CREATION ---
$mainForm = New-Object System.Windows.Forms.Form
$mainForm.Text = "Analytics Benchmark Tool"
$mainForm.Size = New-Object System.Drawing.Size(620, 740)
$mainForm.FormBorderStyle = "FixedSingle" # Changed to FixedSingle to prevent resizing
$mainForm.MaximizeBox = $false # Disable the maximize button
$mainForm.StartPosition = "CenterScreen"
$mainForm.Icon = [System.Drawing.Icon]::ExtractAssociatedIcon($PSHOME + "\powershell.exe")


# --- CONTROLS DEFINITION ---

# Main Tab Control
$tabControl = New-Object System.Windows.Forms.TabControl
$tabControl.Dock = "Fill"

# --- Main Analysis Tab ---
$analysisTab = New-Object System.Windows.Forms.TabPage
$analysisTab.Text = "Analysis"
$analysisTab.Padding = New-Object System.Windows.Forms.Padding(10)

# --- Main Layout Panel ---
# Using a TableLayoutPanel for robust control positioning and scaling.
$mainTableLayout = New-Object System.Windows.Forms.TableLayoutPanel
$mainTableLayout.Dock = "Fill"
$mainTableLayout.ColumnCount = 1
$mainTableLayout.RowCount = 5 # 5 rows for the 4 group boxes and the button
$mainTableLayout.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 100)))
$mainTableLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize))) # GroupBox 1
$mainTableLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize))) # GroupBox 2
$mainTableLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize))) # GroupBox 3
$mainTableLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 100))) # Output Box (fills remaining space)
$mainTableLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize))) # Run Button

# --- GroupBox: Analysis Type ---
$gbAnalysisType = New-Object System.Windows.Forms.GroupBox
$gbAnalysisType.Text = "1. Analysis Type"
$gbAnalysisType.Dock = "Fill"
$gbAnalysisType.Padding = New-Object System.Windows.Forms.Padding(10, 5, 10, 10)
$gbAnalysisType.AutoSize = $true

$rbRate = New-Object System.Windows.Forms.RadioButton
$rbRate.Text = "Rate Analysis"
$rbRate.Location = New-Object System.Drawing.Point(20, 25)
$rbRate.Checked = $true # Default selection
$rbRate.AutoSize = $true

$rbShare = New-Object System.Windows.Forms.RadioButton
$rbShare.Text = "Share Analysis"
$rbShare.Location = New-Object System.Drawing.Point(150, 25)
$rbShare.AutoSize = $true

$gbAnalysisType.Controls.AddRange(@($rbRate, $rbShare))

# --- GroupBox: Input Configuration ---
$gbInputConfig = New-Object System.Windows.Forms.GroupBox
$gbInputConfig.Text = "2. Input Configuration"
$gbInputConfig.Dock = "Fill"
$gbInputConfig.Padding = New-Object System.Windows.Forms.Padding(10, 5, 10, 10)
$gbInputConfig.AutoSize = $true

# Data Source Type Radio Buttons
$lblDataSource = New-Object System.Windows.Forms.Label
$lblDataSource.Text = "Data Source:"
$lblDataSource.Location = New-Object System.Drawing.Point(20, 30)
$lblDataSource.AutoSize = $true

$rbCsv = New-Object System.Windows.Forms.RadioButton
$rbCsv.Text = "CSV File"
$rbCsv.Location = New-Object System.Drawing.Point(130, 28)
$rbCsv.Checked = $true
$rbCsv.AutoSize = $true

$rbSql = New-Object System.Windows.Forms.RadioButton
$rbSql.Text = "SQL Table"
$rbSql.Location = New-Object System.Drawing.Point(230, 28)
$rbSql.AutoSize = $true

# CSV File Controls
$lblCsvFile = New-Object System.Windows.Forms.Label
$lblCsvFile.Text = "File Path:"
$lblCsvFile.Location = New-Object System.Drawing.Point(40, 60)
$lblCsvFile.AutoSize = $true

$txtCsvFile = New-Object System.Windows.Forms.TextBox
$txtCsvFile.Location = New-Object System.Drawing.Point(130, 57)
$txtCsvFile.Size = New-Object System.Drawing.Size(300, 20)

$btnBrowse = New-Object System.Windows.Forms.Button
$btnBrowse.Text = "Browse..."
$btnBrowse.Location = New-Object System.Drawing.Point(440, 55)
$btnBrowse.Size = New-Object System.Drawing.Size(90, 25)

# SQL Table Controls
$lblTableName = New-Object System.Windows.Forms.Label
$lblTableName.Text = "Table Name:"
$lblTableName.Location = New-Object System.Drawing.Point(40, 60)
$lblTableName.AutoSize = $true
$lblTableName.Visible = $false

$txtTableName = New-Object System.Windows.Forms.TextBox
$txtTableName.Location = New-Object System.Drawing.Point(130, 57)
$txtTableName.Size = New-Object System.Drawing.Size(400, 20)
$txtTableName.Visible = $false

# Issuer Name
$lblIssuerName = New-Object System.Windows.Forms.Label
$lblIssuerName.Text = "Issuer Name:"
$lblIssuerName.Location = New-Object System.Drawing.Point(20, 90)
$lblIssuerName.AutoSize = $true

$txtIssuerName = New-Object System.Windows.Forms.TextBox
$txtIssuerName.Location = New-Object System.Drawing.Point(130, 87)
$txtIssuerName.Size = New-Object System.Drawing.Size(400, 20)
$txtIssuerName.Text = "BANCO SANTANDER (BRASIL) S.A." # Default value from README

# Issuer Column
$lblIssuerCol = New-Object System.Windows.Forms.Label
$lblIssuerCol.Text = "Issuer Column:"
$lblIssuerCol.Location = New-Object System.Drawing.Point(20, 120)
$lblIssuerCol.AutoSize = $true

$txtIssuerCol = New-Object System.Windows.Forms.TextBox
$txtIssuerCol.Location = New-Object System.Drawing.Point(130, 117)
$txtIssuerCol.Size = New-Object System.Drawing.Size(200, 20)
$txtIssuerCol.Text = "issuer_name" # Default value

$gbInputConfig.Controls.AddRange(@($lblDataSource, $rbCsv, $rbSql, $lblCsvFile, $txtCsvFile, $btnBrowse, $lblTableName, $txtTableName, $lblIssuerName, $txtIssuerName, $lblIssuerCol, $txtIssuerCol))

# --- GroupBox: Benchmark Parameters ---
$gbParams = New-Object System.Windows.Forms.GroupBox
$gbParams.Text = "3. Benchmark Parameters"
$gbParams.Dock = "Fill"
$gbParams.Padding = New-Object System.Windows.Forms.Padding(10, 5, 10, 10)
$gbParams.AutoSize = $true

# Breaks
$lblBreaks = New-Object System.Windows.Forms.Label
$lblBreaks.Text = "Break Columns:"
$lblBreaks.Location = New-Object System.Drawing.Point(20, 30)
$lblBreaks.AutoSize = $true

$txtBreaks = New-Object System.Windows.Forms.TextBox
$txtBreaks.Location = New-Object System.Drawing.Point(130, 27)
$txtBreaks.Size = New-Object System.Drawing.Size(400, 20)
$txtBreaks.Text = "month_year wallet_flag" # Example value

$lblBreaksHelp = New-Object System.Windows.Forms.Label
$lblBreaksHelp.Text = "(Separate multiple columns with a space)"
$lblBreaksHelp.Location = New-Object System.Drawing.Point(130, 50)
$lblBreaksHelp.ForeColor = "Gray"
$lblBreaksHelp.AutoSize = $true

# Participants
$lblParticipants = New-Object System.Windows.Forms.Label
$lblParticipants.Text = "Participants:"
$lblParticipants.Location = New-Object System.Drawing.Point(20, 80)
$lblParticipants.AutoSize = $true

$numParticipants = New-Object System.Windows.Forms.NumericUpDown
$numParticipants.Location = New-Object System.Drawing.Point(130, 78)
$numParticipants.Size = New-Object System.Drawing.Size(80, 20)
$numParticipants.Minimum = 2
$numParticipants.Maximum = 20
$numParticipants.Value = 4 # Default value

# Max Percent
$lblMaxPercent = New-Object System.Windows.Forms.Label
$lblMaxPercent.Text = "Max Percent:"
$lblMaxPercent.Location = New-Object System.Drawing.Point(250, 80)
$lblMaxPercent.AutoSize = $true

$numMaxPercent = New-Object System.Windows.Forms.NumericUpDown
$numMaxPercent.Location = New-Object System.Drawing.Point(350, 78)
$numMaxPercent.Size = New-Object System.Drawing.Size(80, 20)
$numMaxPercent.Minimum = 10
$numMaxPercent.Maximum = 100
$numMaxPercent.Value = 35 # Default value

# Combinations
$lblCombinations = New-Object System.Windows.Forms.Label
$lblCombinations.Text = "Combinations:"
$lblCombinations.Location = New-Object System.Drawing.Point(20, 115)
$lblCombinations.AutoSize = $true

$txtCombinations = New-Object System.Windows.Forms.TextBox
$txtCombinations.Location = New-Object System.Drawing.Point(130, 112)
$txtCombinations.Size = New-Object System.Drawing.Size(200, 20)
$txtCombinations.Text = "5 1 2" # Default value

# Presets
$lblPresets = New-Object System.Windows.Forms.Label
$lblPresets.Text = "Or use Preset:"
$lblPresets.Location = New-Object System.Drawing.Point(350, 115)
$lblPresets.AutoSize = $true

$cmbPresets = New-Object System.Windows.Forms.ComboBox
$cmbPresets.Location = New-Object System.Drawing.Point(440, 112)
$cmbPresets.Size = New-Object System.Drawing.Size(110, 21)
$cmbPresets.DropDownStyle = "DropDownList"
$cmbPresets.Items.AddRange(@("", "conservative", "standard", "aggressive")) # Add a blank default

$gbParams.Controls.AddRange(@($lblBreaks, $txtBreaks, $lblBreaksHelp, $lblParticipants, $numParticipants, $lblMaxPercent, $numMaxPercent, $lblCombinations, $txtCombinations, $lblPresets, $cmbPresets))

# --- GroupBox: Execution & Output ---
$gbOutput = New-Object System.Windows.Forms.GroupBox
$gbOutput.Text = "4. Execution & Output"
$gbOutput.Dock = "Fill"
$gbOutput.Padding = New-Object System.Windows.Forms.Padding(10, 5, 10, 10)

$txtOutput = New-Object System.Windows.Forms.RichTextBox
$txtOutput.Dock = "Fill"
$txtOutput.ReadOnly = $true
$txtOutput.Font = New-Object System.Drawing.Font("Consolas", 9)
$txtOutput.BackColor = "Black"
$txtOutput.ForeColor = "White"

$gbOutput.Controls.Add($txtOutput)

# --- Run Button ---
$btnRun = New-Object System.Windows.Forms.Button
$btnRun.Text = "Run Analysis"
$btnRun.Size = New-Object System.Drawing.Size(120, 30)
$btnRun.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$btnRun.BackColor = "LawnGreen"
$btnRun.Anchor = "None" # Anchor must be None for TableLayoutPanel to center it

# Add GroupBoxes and Button to the TableLayoutPanel
$mainTableLayout.Controls.Add($gbAnalysisType, 0, 0)
$mainTableLayout.Controls.Add($gbInputConfig, 0, 1)
$mainTableLayout.Controls.Add($gbParams, 0, 2)
$mainTableLayout.Controls.Add($gbOutput, 0, 3)
$mainTableLayout.Controls.Add($btnRun, 0, 4)

# Add the main layout panel to the tab
$analysisTab.Controls.Add($mainTableLayout)

# --- Status Bar ---
$statusBar = New-Object System.Windows.Forms.StatusBar
$statusBar.Text = "Ready"

# --- Help Tab ---
$helpTab = New-Object System.Windows.Forms.TabPage
$helpTab.Text = "Help"
$helpTab.Padding = New-Object System.Windows.Forms.Padding(10)

$txtHelp = New-Object System.Windows.Forms.RichTextBox
$txtHelp.Dock = "Fill"
$txtHelp.ReadOnly = $true
$txtHelp.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$txtHelp.Text = @"
Analytics Benchmark Tool GUI

This interface helps you run the `benchmark_tool.py` script without using the command line.

How to Use:
1.  Select Analysis Type: Choose between 'Rate' or 'Share' analysis.

2.  Input Configuration:
    -   Data Source: Select 'CSV File' or 'SQL Table'.
    -   If CSV: Click 'Browse' to select your input data file.
    -   If SQL: Enter the name of the database table. The script is pre-configured to connect to a specific database (Impala DSN).
    -   Issuer Name: Enter the exact name of the institution you are analyzing.
    -   Issuer Column: Specify the column name that contains the issuer names.

3.  Benchmark Parameters:
    -   You can either fill in the parameters manually OR select a preset. Selecting a preset will override the manual values for Participants, Max Percent, and Combinations when the script is run.
    -   Break Columns: Enter one or more column names to use for breaking down the analysis. Separate them with spaces (e.g., `month_year industry`).
    -   Participants: The number of peers to include in each benchmark group.
    -   Max Percent: The maximum percentage a single peer can represent in a group's total volume (a privacy rule).
    -   Combinations: The priority order for trying different peer group combinations.

4.  Execution & Output:
    -   Click 'Run Analysis' to start the process.
    -   The button will be disabled while the script runs.
    -   The black box will show the real-time output from the Python script.
    -   When finished, the script will produce an Excel file and a log file in the same directory.
"@

$helpTab.Controls.Add($txtHelp)

# Add tabs to the tab control
$tabControl.TabPages.AddRange(@($analysisTab, $helpTab))

# Add all controls to the main form
$mainForm.Controls.AddRange(@($tabControl, $statusBar))


# --- EVENT HANDLERS ---

# Function to toggle data source controls
$toggleDataSourceControls = {
    if ($rbCsv.Checked) {
        $lblCsvFile.Visible = $true
        $txtCsvFile.Visible = $true
        $btnBrowse.Visible = $true
        $lblTableName.Visible = $false
        $txtTableName.Visible = $false
    } else { # SQL is checked
        $lblCsvFile.Visible = $false
        $txtCsvFile.Visible = $false
        $btnBrowse.Visible = $false
        $lblTableName.Visible = $true
        $txtTableName.Visible = $true
    }
}

# Add event handlers for radio buttons
$rbCsv.Add_CheckedChanged($toggleDataSourceControls)
$rbSql.Add_CheckedChanged($toggleDataSourceControls)

# Browse Button Click Event
$btnBrowse.Add_Click({
    $openFileDialog = New-Object System.Windows.Forms.OpenFileDialog
    $openFileDialog.Filter = "CSV Files (*.csv)|*.csv|All Files (*.*)|*.*"
    $openFileDialog.Title = "Select a CSV File"
    if ($openFileDialog.ShowDialog() -eq "OK") {
        $txtCsvFile.Text = $openFileDialog.FileName
    }
})

# Preset ComboBox Selection Change Event
$cmbPresets.Add_SelectedIndexChanged({
    if ($cmbPresets.SelectedItem -ne "") {
        # If a preset is selected, disable manual parameter fields
        $txtCombinations.Enabled = $false
        $numParticipants.Enabled = $false
        $numMaxPercent.Enabled = $false
    } else {
        # If no preset is selected, enable manual fields
        $txtCombinations.Enabled = $true
        $numParticipants.Enabled = $true
        $numMaxPercent.Enabled = $true
    }
})

# Run Button Click Event
$btnRun.Add_Click({
    # --- Validation ---
    if ($rbCsv.Checked -and -not (Test-Path -Path $txtCsvFile.Text -PathType Leaf)) {
        [System.Windows.Forms.MessageBox]::Show("Please select a valid CSV file.", "Input Error", "OK", "Error")
        return
    }
    if ($rbSql.Checked -and [string]::IsNullOrWhiteSpace($txtTableName.Text)) {
        [System.Windows.Forms.MessageBox]::Show("Please enter a SQL Table Name.", "Input Error", "OK", "Error")
        return
    }
    if ([string]::IsNullOrWhiteSpace($txtIssuerName.Text)) {
        [System.Windows.Forms.MessageBox]::Show("Please enter an Issuer Name.", "Input Error", "OK", "Error")
        return
    }
    if ([string]::IsNullOrWhiteSpace($txtBreaks.Text)) {
        [System.Windows.Forms.MessageBox]::Show("Please enter at least one Break Column.", "Input Error", "OK", "Error")
        return
    }

    # --- Build the Command ---
    $arguments = @()
    
    if ($rbCsv.Checked) {
        # Build the simplified 'rate' or 'share' command for CSV
        $command = if ($rbRate.Checked) { "rate" } else { "share" }
        $arguments = @(
            "'$pythonScriptPath'",
            $command,
            "--csv", "'$($txtCsvFile.Text)'",
            "--issuer", "'$($txtIssuerName.Text)'",
            "--issuer-col", "'$($txtIssuerCol.Text)'",
            "--break", $txtBreaks.Text.Split(' ')
        )
    } else { # SQL is checked
        # Build the 'legacy' command for SQL
        $command = "legacy"
        $arguments = @(
            "'$pythonScriptPath'",
            $command,
            "--type", "sql",
            "--table-name", "'$($txtTableName.Text)'",
            "--issuer-name", "'$($txtIssuerName.Text)'",
            "--issuer-column", "'$($txtIssuerCol.Text)'"
        )
        # The --break-def argument in legacy mode accepts multiple entries
        $txtBreaks.Text.Split(' ') | ForEach-Object { $arguments += @("--break-def", $_) }
    }

    # Add shared parameters (presets or manual)
    if ($cmbPresets.SelectedItem -ne "") {
        $arguments += @("--preset", $cmbPresets.SelectedItem)
    } else {
        if ($rbCsv.Checked) {
             $arguments += @(
                "--participants", $numParticipants.Value,
                "--max-percent", $numMaxPercent.Value,
                "--combinations", $txtCombinations.Text.Split(' ')
            )
        } else { # Legacy command has different names for these args
             $arguments += @(
                "--num-participants", $numParticipants.Value,
                "--max-percentage", $numMaxPercent.Value,
                "--comb-priority", $txtCombinations.Text.Split(' ')
            )
        }
    }

    # --- Execute the Script ---
    $txtOutput.Clear()
    $txtOutput.AppendText("Starting analysis...`n`n")
    $txtOutput.AppendText("Executing: python $($arguments -join ' ')`n")
    $txtOutput.AppendText("--------------------------------------------------`n")
    
    $statusBar.Text = "Running... Please wait."
    $btnRun.Enabled = $false
    $mainForm.Cursor = [System.Windows.Forms.Cursors]::WaitCursor
    $mainForm.Refresh()

    # Use Start-Process to run the python script and redirect output
    $process = Start-Process python -ArgumentList $arguments -NoNewWindow -PassThru -RedirectStandardOutput "$PSScriptRoot\stdout.log" -RedirectStandardError "$PSScriptRoot\stderr.log" -Wait
    
    # Read output and error logs and display them
    $stdout = Get-Content "$PSScriptRoot\stdout.log" -ErrorAction SilentlyContinue
    $stderr = Get-Content "$PSScriptRoot\stderr.log" -ErrorAction SilentlyContinue
    
    $txtOutput.AppendText($stdout -join "`n")
    
    if ($stderr) {
        $txtOutput.SelectionColor = "Red"
        $txtOutput.AppendText("`n`n--- ERRORS ---`n")
        $txtOutput.AppendText($stderr -join "`n")
    }
    
    $txtOutput.AppendText("`n--------------------------------------------------`n")
    if ($process.ExitCode -eq 0) {
        $txtOutput.SelectionColor = "LawnGreen"
        $txtOutput.AppendText("Analysis completed successfully.")
        $statusBar.Text = "Finished successfully."
    } else {
        $txtOutput.SelectionColor = "Red"
        $txtOutput.AppendText("Analysis finished with errors. See output above.")
        $statusBar.Text = "Finished with errors."
    }

    # Clean up log files
    Remove-Item "$PSScriptRoot\stdout.log", "$PSScriptRoot\stderr.log" -ErrorAction SilentlyContinue

    # Re-enable controls
    $btnRun.Enabled = $true
    $mainForm.Cursor = [System.Windows.Forms.Cursors]::Default
})


# --- SHOW THE FORM ---
# This will display the form and wait for the user to close it.
$mainForm.ShowDialog() | Out-Null