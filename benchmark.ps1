<#
.SYNOPSIS
    A PowerShell GUI wrapper for the AAnF_Benchmark_Tool.py Python script.
.DESCRIPTION
    This script provides a user-friendly graphical interface to set parameters
    and execute the AAnF_Benchmark_Tool.py script. It captures and displays
    the output from the Python script in real-time.
.NOTES
    - Requires PowerShell 5.1 or later.
    - The Python script 'AAnF_Benchmark_Tool.py' must be in the same directory as this PowerShell script.
    - Python must be installed and accessible via the system's PATH.
#>

# --- ASSEMBLY AND FORM SETUP ---
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# Create the main form
$main_form = New-Object System.Windows.Forms.Form
$main_form.Text = "AAnF Benchmark Tool GUI"
$main_form.Size = New-Object System.Drawing.Size(600, 700)
$main_form.StartPosition = "CenterScreen"
$main_form.FormBorderStyle = 'FixedDialog'
$main_form.MaximizeBox = $false

# --- FONT AND CONTROL SETUP ---
$font = New-Object System.Drawing.Font("Segoe UI", 10)
$main_form.Font = $font

# --- FUNCTION TO ADD CONTROLS ---
# Helper function to reduce boilerplate code when adding controls.
function Add-Control {
    param(
        [string]$Type,
        [string]$Text,
        [int]$X,
        [int]$Y,
        [int]$Width,
        [int]$Height,
        [System.Windows.Forms.Control]$Parent = $main_form
    )
    $control = New-Object "System.Windows.Forms.$Type"
    $control.Text = $Text
    $control.Location = New-Object System.Drawing.Point($X, $Y)
    $control.Size = New-Object System.Drawing.Size($Width, $Height)
    $Parent.Controls.Add($control)
    return $control
}

# --- GUI CONTROLS ---

# 1. Data Source Group
$dataSource_group = Add-Control -Type "GroupBox" -Text "Data Source" -X 15 -Y 15 -Width 555 -Height 120

$type_label = Add-Control -Type "Label" -Text "Source Type:" -X 20 -Y 30 -Width 120 -Height 25 -Parent $dataSource_group

$csv_radio = Add-Control -Type "RadioButton" -Text "CSV" -X 150 -Y 30 -Width 60 -Height 25 -Parent $dataSource_group
$csv_radio.Checked = $true

$sql_radio = Add-Control -Type "RadioButton" -Text "SQL" -X 220 -Y 30 -Width 60 -Height 25 -Parent $dataSource_group

$csvFile_label = Add-Control -Type "Label" -Text "CSV File:" -X 20 -Y 65 -Width 120 -Height 25 -Parent $dataSource_group
$csvFile_textBox = Add-Control -Type "TextBox" -Text "" -X 150 -Y 65 -Width 280 -Height 25 -Parent $dataSource_group
$csvFile_browseButton = Add-Control -Type "Button" -Text "Browse..." -X 440 -Y 64 -Width 90 -Height 28 -Parent $dataSource_group

$tableName_label = Add-Control -Type "Label" -Text "SQL Table Name:" -X 20 -Y 65 -Width 120 -Height 25 -Parent $dataSource_group
$tableName_textBox = Add-Control -Type "TextBox" -Text "" -X 150 -Y 65 -Width 280 -Height 25 -Parent $dataSource_group

# 2. Column Names Group
$columns_group = Add-Control -Type "GroupBox" -Text "Column Names" -X 15 -Y 145 -Width 555 -Height 100

$apprAmount_label = Add-Control -Type "Label" -Text "Approved Amount:" -X 20 -Y 30 -Width 140 -Height 25 -Parent $columns_group
$apprAmount_textBox = Add-Control -Type "TextBox" -Text "appr_amount" -X 170 -Y 30 -Width 200 -Height 25 -Parent $columns_group

$apprTxns_label = Add-Control -Type "Label" -Text "Approved Transactions:" -X 20 -Y 65 -Width 140 -Height 25 -Parent $columns_group
$apprTxns_textBox = Add-Control -Type "TextBox" -Text "appr_txns" -X 170 -Y 65 -Width 200 -Height 25 -Parent $columns_group

# 3. Analysis Definition Group
$analysis_group = Add-Control -Type "GroupBox" -Text "Analysis Definition" -X 15 -Y 255 -Width 555 -Height 200

$breakDef_label = Add-Control -Type "Label" -Text "Break Definitions (Required):" -X 20 -Y 30 -Width 200 -Height 25 -Parent $analysis_group
$breakDef_listBox = Add-Control -Type "ListBox" -Text "" -X 20 -Y 55 -Width 250 -Height 130 -Parent $analysis_group
$breakDef_listBox.SelectionMode = "MultiExtended"

$newBreak_textBox = Add-Control -Type "TextBox" -Text "" -X 280 -Y 55 -Width 150 -Height 25 -Parent $analysis_group
$addBreak_button = Add-Control -Type "Button" -Text "Add" -X 440 -Y 54 -Width 90 -Height 28 -Parent $analysis_group
$removeBreak_button = Add-Control -Type "Button" -Text "Remove" -X 440 -Y 88 -Width 90 -Height 28 -Parent $analysis_group

$combPriority_label = Add-Control -Type "Label" -Text "Combination Priority:" -X 280 -Y 125 -Width 150 -Height 25 -Parent $analysis_group
$combPriority_textBox = Add-Control -Type "TextBox" -Text "1 2 3 4 5" -X 280 -Y 150 -Width 250 -Height 25 -Parent $analysis_group

# 4. Execution and Output
$run_button = Add-Control -Type "Button" -Text "Run Analysis" -X 15 -Y 465 -Width 555 -Height 40
$run_button.Font = New-Object System.Drawing.Font("Segoe UI", 12, [System.Drawing.FontStyle]::Bold)
$run_button.BackColor = [System.Drawing.Color]::LightGreen

$output_label = Add-Control -Type "Label" -Text "Output Log:" -X 15 -Y 515 -Width 100 -Height 25
$output_textBox = Add-Control -Type "TextBox" -Text "" -X 15 -Y 540 -Width 555 -Height 100
$output_textBox.Multiline = $true
$output_textBox.ScrollBars = "Vertical"
$output_textBox.ReadOnly = $true
$output_textBox.Font = New-Object System.Drawing.Font("Consolas", 9)

# --- EVENT HANDLERS ---

# Toggle visibility of source inputs based on radio button selection
$toggleSourceInputs = {
    if ($csv_radio.Checked) {
        $csvFile_label.Visible = $true
        $csvFile_textBox.Visible = $true
        $csvFile_browseButton.Visible = $true
        $tableName_label.Visible = $false
        $tableName_textBox.Visible = $false
    } else {
        $csvFile_label.Visible = $false
        $csvFile_textBox.Visible = $false
        $csvFile_browseButton.Visible = $false
        $tableName_label.Visible = $true
        $tableName_textBox.Visible = $true
    }
}
$csv_radio.add_CheckedChanged($toggleSourceInputs)
$sql_radio.add_CheckedChanged($toggleSourceInputs)
# Initial call to set the correct state
& $toggleSourceInputs

# Browse for CSV file button
$csvFile_browseButton.add_Click({
    $openFileDialog = New-Object System.Windows.Forms.OpenFileDialog
    $openFileDialog.Filter = "CSV Files (*.csv)|*.csv|All Files (*.*)|*.*"
    if ($openFileDialog.ShowDialog() -eq "OK") {
        $csvFile_textBox.Text = $openFileDialog.FileName
    }
})

# Add/Remove Break Definition buttons
$addBreak_button.add_Click({
    if (-not [string]::IsNullOrWhiteSpace($newBreak_textBox.Text)) {
        [void]$breakDef_listBox.Items.Add($newBreak_textBox.Text)
        $newBreak_textBox.Clear()
        $newBreak_textBox.Focus()
    }
})

$removeBreak_button.add_Click({
    $selectedItems = $breakDef_listBox.SelectedItems | ForEach-Object { $_ } # Clone the collection
    foreach ($item in $selectedItems) {
        [void]$breakDef_listBox.Items.Remove($item)
    }
})


# Run Analysis button
$run_button.add_Click({
    # --- UI State and Validation ---
    $run_button.Enabled = $false
    $run_button.Text = "Running..."
    $output_textBox.Clear()
    $main_form.Update()

    # Validation
    if ($csv_radio.Checked -and [string]::IsNullOrWhiteSpace($csvFile_textBox.Text)) {
        [System.Windows.Forms.MessageBox]::Show("Please select a CSV file.", "Input Error", "OK", "Error")
        $run_button.Enabled = $true
        $run_button.Text = "Run Analysis"
        return
    }
    if ($sql_radio.Checked -and [string]::IsNullOrWhiteSpace($tableName_textBox.Text)) {
        [System.Windows.Forms.MessageBox]::Show("Please enter a SQL table name.", "Input Error", "OK", "Error")
        $run_button.Enabled = $true
        $run_button.Text = "Run Analysis"
        return
    }
    if ($breakDef_listBox.Items.Count -eq 0) {
        [System.Windows.Forms.MessageBox]::Show("At least one break definition is required.", "Input Error", "OK", "Error")
        $run_button.Enabled = $true
        $run_button.Text = "Run Analysis"
        return
    }

    # --- Build Argument List for Python Script ---
    $scriptPath = Join-Path $PSScriptRoot "AAnF_Benchmark_Tool.py"
    $argList = New-Object System.Collections.Generic.List[string]

    # Source Type
    $argList.Add("--type")
    if ($csv_radio.Checked) {
        $argList.Add("csv")
        $argList.Add("--csv-file")
        $argList.Add($csvFile_textBox.Text)
    } else {
        $argList.Add("sql")
        $argList.Add("--table-name")
        $argList.Add($tableName_textBox.Text)
    }

    # Column Names
    $argList.Add("--appr-amount-col")
    $argList.Add($apprAmount_textBox.Text)
    $argList.Add("--appr-txns-col")
    $argList.Add($apprTxns_textBox.Text)

    # Break Definitions
    foreach ($item in $breakDef_listBox.Items) {
        $argList.Add("--break-def")
        $argList.Add($item)
    }

    # Combination Priority
    $argList.Add("--comb-priority")
    $combPriority_textBox.Text.Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries) | ForEach-Object {
        $argList.Add($_)
    }

    # --- Execute Python Script ---
    $output_textBox.AppendText("Starting analysis...`r`n")
    $output_textBox.AppendText("Command: python.exe `"$scriptPath`" $($argList -join ' ')`r`n`r`n")
    
    # Using Start-Job to run asynchronously and keep the GUI responsive
    $job = Start-Job -ScriptBlock {
        param($scriptPath, $argList)
        # Use try/catch to handle errors like python not being found
        try {
            # We redirect stderr to stdout (2>&1) to capture all output in one stream.
            python.exe $scriptPath $argList 2>&1
        } catch {
            Write-Output "ERROR: Failed to execute Python script."
            Write-Output $_.Exception.Message
        }
    } -ArgumentList $scriptPath, $argList

    # Poll the job for output
    while ($job.State -eq 'Running') {
        Receive-Job -Job $job | ForEach-Object {
            $output_textBox.AppendText("$_`r`n")
        }
        Start-Sleep -Milliseconds 200
    }

    # Get any final output
    Receive-Job -Job $job | ForEach-Object {
        $output_textBox.AppendText("$_`r`n")
    }
    
    $output_textBox.AppendText("`r`nAnalysis finished.")
    Remove-Job -Job $job

    # --- Reset UI State ---
    $run_button.Enabled = $true
    $run_button.Text = "Run Analysis"
})


# --- SHOW FORM ---
[void]$main_form.ShowDialog()

# --- CLEANUP ---
$main_form.Dispose()
