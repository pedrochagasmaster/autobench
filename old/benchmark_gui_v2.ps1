<#
.SYNOPSIS
    A PowerShell GUI wrapper for the benchmark_tool.py Python script.

.DESCRIPTION
    This script provides a user-friendly Windows Forms interface to run the benchmark analysis tool.
    It features an advanced, interactive "Break Composer" and a dedicated "Output" tab for clarity.

.NOTES
    Author: Gemini
    Date:   2024-07-10
    Version: 17.0

    Prerequisites:
    1. PowerShell 5.1 or later.
    2. .NET Framework 4.5 or later.
    3. A Python environment with all dependencies for `benchmark_tool.py` installed.
    4. The `py` or `python` executable must be in your system's PATH.
    5. This script, `benchmark_tool.py`, and `presets.json` should be in the same directory.
#>

# --- SCRIPT CONFIGURATION ---
$pythonScriptPath = Join-Path $PSScriptRoot "benchmark_tool.py"
$presetsJsonPath = Join-Path $PSScriptRoot "presets.json"

# --- HELPER FUNCTIONS ---
function Load-Presets {
    $defaultPresets = @("conservative", "standard", "aggressive")
    if (-not (Test-Path $presetsJsonPath)) {
        Write-Warning "presets.json not found. Using default presets."
        return $defaultPresets
    }
    try {
        $presets = Get-Content -Path $presetsJsonPath | ConvertFrom-Json
        if ($presets.presets) {
            return $presets.presets.PSObject.Properties.Name
        } else {
            return $presets.PSObject.Properties.Name
        }
    }
    catch {
        Write-Warning "Failed to parse presets.json. Using default presets. Error: $_"
        return $defaultPresets
    }
}


# --- GUI SETUP ---
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# --- FORM CREATION ---
$mainForm = New-Object System.Windows.Forms.Form
$mainForm.Text = "Analytics Benchmark Tool"
$mainForm.Size = New-Object System.Drawing.Size(640, 840)
$mainForm.FormBorderStyle = "FixedSingle"
$mainForm.MaximizeBox = $false
$mainForm.StartPosition = "CenterScreen"
$mainForm.Icon = [System.Drawing.Icon]::ExtractAssociatedIcon($PSHOME + "\powershell.exe")

# --- CONTROLS DEFINITION ---
$tabControl = New-Object System.Windows.Forms.TabControl
$tabControl.Dock = "Fill"

# --- Main Analysis Tab ---
$analysisTab = New-Object System.Windows.Forms.TabPage
$analysisTab.Text = "Analysis"
$analysisTab.Padding = New-Object System.Windows.Forms.Padding(10)

# --- Main Layout Panel for Analysis Tab ---
$mainTableLayout = New-Object System.Windows.Forms.TableLayoutPanel
$mainTableLayout.Dock = "Fill"
$mainTableLayout.ColumnCount = 1
$mainTableLayout.RowCount = 5 # 4 sections + 1 for the button
$mainTableLayout.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 100)))
$mainTableLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
$mainTableLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
$mainTableLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
$mainTableLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
$mainTableLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize))) # Row for the button

# --- GroupBox: Analysis Type ---
$gbAnalysisType = New-Object System.Windows.Forms.GroupBox
$gbAnalysisType.Text = "1. Analysis Type"
$gbAnalysisType.Dock = "Fill"
$gbAnalysisType.Padding = New-Object System.Windows.Forms.Padding(10, 5, 10, 10)
$gbAnalysisType.AutoSize = $true
$rbRate = New-Object System.Windows.Forms.RadioButton; $rbRate.Text = "Rate Analysis"; $rbRate.Location = "20, 25"; $rbRate.Checked = $true; $rbRate.AutoSize = $true
$rbShare = New-Object System.Windows.Forms.RadioButton; $rbShare.Text = "Share Analysis"; $rbShare.Location = "150, 25"; $rbShare.AutoSize = $true
$gbAnalysisType.Controls.AddRange(@($rbRate, $rbShare))

# --- GroupBox: Input Configuration ---
$gbInputConfig = New-Object System.Windows.Forms.GroupBox
$gbInputConfig.Text = "2. Input Configuration"
$gbInputConfig.Dock = "Fill"
$gbInputConfig.Padding = New-Object System.Windows.Forms.Padding(10, 5, 10, 10)
$gbInputConfig.AutoSize = $true
$lblDataSource = New-Object System.Windows.Forms.Label; $lblDataSource.Text = "Data Source:"; $lblDataSource.Location = "20, 30"; $lblDataSource.AutoSize = $true
$rbCsv = New-Object System.Windows.Forms.RadioButton; $rbCsv.Text = "CSV File"; $rbCsv.Location = "130, 28"; $rbCsv.Checked = $true; $rbCsv.AutoSize = $true
$rbSql = New-Object System.Windows.Forms.RadioButton; $rbSql.Text = "SQL Table"; $rbSql.Location = "230, 28"; $rbSql.AutoSize = $true
$lblCsvFile = New-Object System.Windows.Forms.Label; $lblCsvFile.Text = "File Path:"; $lblCsvFile.Location = "40, 60"; $lblCsvFile.AutoSize = $true
$txtCsvFile = New-Object System.Windows.Forms.TextBox; $txtCsvFile.Location = "130, 57"; $txtCsvFile.Size = "300, 20"
$btnBrowse = New-Object System.Windows.Forms.Button; $btnBrowse.Text = "Browse..."; $btnBrowse.Location = "440, 55"; $btnBrowse.Size = "90, 25"
$lblTableName = New-Object System.Windows.Forms.Label; $lblTableName.Text = "Table Name:"; $lblTableName.Location = "40, 60"; $lblTableName.AutoSize = $true; $lblTableName.Visible = $false
$txtTableName = New-Object System.Windows.Forms.TextBox; $txtTableName.Location = "130, 57"; $txtTableName.Size = "400, 20"; $txtTableName.Visible = $false
$lblIssuerName = New-Object System.Windows.Forms.Label; $lblIssuerName.Text = "Issuer Name:"; $lblIssuerName.Location = "20, 90"; $lblIssuerName.AutoSize = $true
$txtIssuerName = New-Object System.Windows.Forms.TextBox; $txtIssuerName.Location = "130, 87"; $txtIssuerName.Size = "420, 20"; $txtIssuerName.Text = "BANCO SANTANDER (BRASIL) S.A."
$lblIssuerCol = New-Object System.Windows.Forms.Label; $lblIssuerCol.Text = "Issuer Column:"; $lblIssuerCol.Location = "20, 120"; $lblIssuerCol.AutoSize = $true
$txtIssuerCol = New-Object System.Windows.Forms.TextBox; $txtIssuerCol.Location = "130, 117"; $txtIssuerCol.Size = "200, 20"; $txtIssuerCol.Text = "issuer_name"
$btnGetColumns = New-Object System.Windows.Forms.Button; $btnGetColumns.Text = "Get Columns from File"; $btnGetColumns.Location = "350, 115"; $btnGetColumns.Size = "180, 25"; $btnGetColumns.Enabled = $false
$gbInputConfig.Controls.AddRange(@($lblDataSource, $rbCsv, $rbSql, $lblCsvFile, $txtCsvFile, $btnBrowse, $lblTableName, $txtTableName, $lblIssuerName, $txtIssuerName, $lblIssuerCol, $txtIssuerCol, $btnGetColumns))

# --- GroupBox: Break Composer ---
$gbBreaks = New-Object System.Windows.Forms.GroupBox
$gbBreaks.Text = "3. Break Composer"
$gbBreaks.Dock = "Fill"
$gbBreaks.Padding = New-Object System.Windows.Forms.Padding(10, 5, 10, 10)
$gbBreaks.AutoSize = $true
$rbSingleBreak = New-Object System.Windows.Forms.RadioButton; $rbSingleBreak.Text = "Single Column Break"; $rbSingleBreak.Location = "20, 25"; $rbSingleBreak.Checked = $true; $rbSingleBreak.AutoSize = $true
$rbCombinedBreak = New-Object System.Windows.Forms.RadioButton; $rbCombinedBreak.Text = "Combined Break (col1:col2)"; $rbCombinedBreak.Location = "200, 25"; $rbCombinedBreak.AutoSize = $true
$lblCol1 = New-Object System.Windows.Forms.Label; $lblCol1.Text = "Column:"; $lblCol1.Location = "40, 55"; $lblCol1.AutoSize = $true
$cmbCol1 = New-Object System.Windows.Forms.ComboBox; $cmbCol1.Location = "110, 52"; $cmbCol1.Size = "180, 21"; $cmbCol1.DropDownStyle = "DropDownList"; $cmbCol1.Enabled = $false
$lblCol2 = New-Object System.Windows.Forms.Label; $lblCol2.Text = "Column 2:"; $lblCol2.Location = "300, 55"; $lblCol2.AutoSize = $true; $lblCol2.Visible = $false
$cmbCol2 = New-Object System.Windows.Forms.ComboBox; $cmbCol2.Location = "370, 52"; $cmbCol2.Size = "180, 21"; $cmbCol2.DropDownStyle = "DropDownList"; $cmbCol2.Visible = $false
$lblPreview = New-Object System.Windows.Forms.Label; $lblPreview.Text = "Preview: "; $lblPreview.Location = "40, 85"; $lblPreview.AutoSize = $true; $lblPreview.Font = New-Object System.Drawing.Font("Segoe UI", 8, [System.Drawing.FontStyle]::Italic)
$btnAddBreak = New-Object System.Windows.Forms.Button; $btnAddBreak.Text = "Add Break >>"; $btnAddBreak.Location = "450, 80"; $btnAddBreak.Size = "100, 30"; $btnAddBreak.Enabled = $false
$lblDefinedBreaks = New-Object System.Windows.Forms.Label; $lblDefinedBreaks.Text = "Defined Breaks for Analysis:"; $lblDefinedBreaks.Location = "20, 115"; $lblDefinedBreaks.AutoSize = $true
$lbDefinedBreaks = New-Object System.Windows.Forms.ListBox; $lbDefinedBreaks.Location = "20, 135"; $lbDefinedBreaks.Size = "530, 95"
$btnRemoveBreak = New-Object System.Windows.Forms.Button; $btnRemoveBreak.Text = "Remove Selected"; $btnRemoveBreak.Location = "430, 235"; $btnRemoveBreak.Size = "120, 25"
$gbBreaks.Controls.AddRange(@($rbSingleBreak, $rbCombinedBreak, $lblCol1, $cmbCol1, $lblCol2, $cmbCol2, $lblPreview, $btnAddBreak, $lblDefinedBreaks, $lbDefinedBreaks, $btnRemoveBreak))

# --- GroupBox: Benchmark Parameters ---
$gbParams = New-Object System.Windows.Forms.GroupBox
$gbParams.Text = "4. Benchmark Parameters"
$gbParams.Dock = "Fill"
$gbParams.Padding = New-Object System.Windows.Forms.Padding(10, 5, 10, 10)
$gbParams.AutoSize = $true
$lblParticipants = New-Object System.Windows.Forms.Label; $lblParticipants.Text = "Participants:"; $lblParticipants.Location = "20, 30"; $lblParticipants.AutoSize = $true
$numParticipants = New-Object System.Windows.Forms.NumericUpDown; $numParticipants.Location = "130, 28"; $numParticipants.Size = "80, 20"; $numParticipants.Minimum = 2; $numParticipants.Maximum = 20; $numParticipants.Value = 4
$lblMaxPercent = New-Object System.Windows.Forms.Label; $lblMaxPercent.Text = "Max Percent:"; $lblMaxPercent.Location = "250, 30"; $lblMaxPercent.AutoSize = $true
$numMaxPercent = New-Object System.Windows.Forms.NumericUpDown; $numMaxPercent.Location = "350, 28"; $numMaxPercent.Size = "80, 20"; $numMaxPercent.Minimum = 10; $numMaxPercent.Maximum = 100; $numMaxPercent.Value = 35
$lblCombinations = New-Object System.Windows.Forms.Label; $lblCombinations.Text = "Combinations:"; $lblCombinations.Location = "20, 65"; $lblCombinations.AutoSize = $true
$txtCombinations = New-Object System.Windows.Forms.TextBox; $txtCombinations.Location = "130, 62"; $txtCombinations.Size = "200, 20"; $txtCombinations.Text = "5 1 2"
$lblPresets = New-Object System.Windows.Forms.Label; $lblPresets.Text = "Or use Preset:"; $lblPresets.Location = "350, 65"; $lblPresets.AutoSize = $true
$cmbPresets = New-Object System.Windows.Forms.ComboBox; $cmbPresets.Location = "440, 62"; $cmbPresets.Size = "110, 21"; $cmbPresets.DropDownStyle = "DropDownList"
$presetList = New-Object System.Collections.Generic.List[string]; $presetList.Add("(Manual)"); Load-Presets | ForEach-Object { $presetList.Add([string]$_) }; $cmbPresets.Items.AddRange($presetList.ToArray()); $cmbPresets.SelectedIndex = 0
$gbParams.Controls.AddRange(@($lblParticipants, $numParticipants, $lblMaxPercent, $numMaxPercent, $lblCombinations, $txtCombinations, $lblPresets, $cmbPresets))

# --- Run Button ---
$btnRun = New-Object System.Windows.Forms.Button
$btnRun.Text = "Run Analysis"; $btnRun.Size = "120, 30"; $btnRun.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold); $btnRun.BackColor = "LawnGreen"
$btnRun.Anchor = "None" # Anchor must be None for TableLayoutPanel to center it

# Add GroupBoxes and Button to the TableLayoutPanel
$mainTableLayout.Controls.Add($gbAnalysisType, 0, 0)
$mainTableLayout.Controls.Add($gbInputConfig, 0, 1)
$mainTableLayout.Controls.Add($gbBreaks, 0, 2)
$mainTableLayout.Controls.Add($gbParams, 0, 3)
$mainTableLayout.Controls.Add($btnRun, 0, 4)

$analysisTab.Controls.Add($mainTableLayout)

# --- Help Tab ---
$helpTab = New-Object System.Windows.Forms.TabPage; $helpTab.Text = "Help"; $helpTab.Padding = New-Object System.Windows.Forms.Padding(10)
$txtHelp = New-Object System.Windows.Forms.RichTextBox; $txtHelp.Dock = "Fill"; $txtHelp.ReadOnly = $true; $txtHelp.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$txtHelp.Text = @"
Analytics Benchmark Tool GUI

How to Use:
1.  On the 'Analysis' tab, configure your run.
2.  Select Analysis Type: 'Rate' or 'Share'.
3.  Input Configuration:
    -   Select Data Source: 'CSV' or 'SQL'.
    -   If CSV, browse for the file, then click 'Get Columns from File'.
4.  Break Composer:
    -   Choose 'Single' or 'Combined' break type.
    -   Select column(s) from the dropdowns.
    -   Click 'Add Break >>' to add it to the 'Defined Breaks' list.
5.  Benchmark Parameters:
    -   Set parameters manually or choose a preset.
6.  Click 'Run Analysis'.
7.  Switch to the 'Output' tab to view the live execution log.
"@
$helpTab.Controls.Add($txtHelp)

# --- Output Tab ---
$outputTab = New-Object System.Windows.Forms.TabPage
$outputTab.Text = "Output"
$outputTab.Padding = New-Object System.Windows.Forms.Padding(10)

$txtOutput = New-Object System.Windows.Forms.RichTextBox
$txtOutput.Dock = "Fill"; $txtOutput.ReadOnly = $true; $txtOutput.Font = New-Object System.Drawing.Font("Consolas", 9); $txtOutput.BackColor = "Black"; $txtOutput.ForeColor = "White"
$outputTab.Controls.Add($txtOutput)

# Add tabs to the tab control
$tabControl.TabPages.AddRange(@($analysisTab, $helpTab, $outputTab))

# --- Status Bar ---
$statusBar = New-Object System.Windows.Forms.StatusBar; $statusBar.Text = "Ready"

$mainForm.Controls.AddRange(@($tabControl, $statusBar))


# --- EVENT HANDLERS ---
$UpdatePreview = {
    $previewText = "Preview: "
    if ($rbSingleBreak.Checked) {
        if ($cmbCol1.SelectedItem) { $previewText += $cmbCol1.SelectedItem }
    } else {
        if ($cmbCol1.SelectedItem -and $cmbCol2.SelectedItem) {
            if ($cmbCol1.SelectedItem -ne $cmbCol2.SelectedItem) {
                $previewText += "$($cmbCol1.SelectedItem):$($cmbCol2.SelectedItem)"
            } else {
                $previewText += " (columns must be different)"
            }
        }
    }
    $lblPreview.Text = $previewText
}

$toggleDataSourceControls = {
    $isCsv = $rbCsv.Checked
    $lblCsvFile.Visible = $isCsv; $txtCsvFile.Visible = $isCsv; $btnBrowse.Visible = $isCsv; $btnGetColumns.Visible = $isCsv
    $lblTableName.Visible = !$isCsv; $txtTableName.Visible = !$isCsv
    if (!$isCsv) { $cmbCol1.Items.Clear(); $cmbCol2.Items.Clear(); $cmbCol1.Enabled = $false; $cmbCol2.Enabled = $false; $btnAddBreak.Enabled = $false }
}
$rbCsv.Add_CheckedChanged($toggleDataSourceControls); $rbSql.Add_CheckedChanged($toggleDataSourceControls)

$txtCsvFile.Add_TextChanged({ $btnGetColumns.Enabled = (Test-Path $txtCsvFile.Text -PathType Leaf) })

$btnBrowse.Add_Click({
    $openFileDialog = New-Object System.Windows.Forms.OpenFileDialog; $openFileDialog.Filter = "CSV Files (*.csv)|*.csv|All Files (*.*)|*.*"
    if ($openFileDialog.ShowDialog() -eq "OK") { $txtCsvFile.Text = $openFileDialog.FileName }
})

$btnGetColumns.Add_Click({
    try {
        $header = (Get-Content -Path $txtCsvFile.Text -TotalCount 1).Split(',')
        $cmbCol1.Items.Clear(); $cmbCol2.Items.Clear()
        $header | ForEach-Object { $cmbCol1.Items.Add($_); $cmbCol2.Items.Add($_) }
        $cmbCol1.Enabled = $true; $cmbCol2.Enabled = $true; $btnAddBreak.Enabled = $true
        [System.Windows.Forms.MessageBox]::Show("Columns loaded successfully.", "Success", "OK", "Information")
    } catch {
        [System.Windows.Forms.MessageBox]::Show("Failed to read columns from CSV file. Please ensure it is a valid, comma-separated file.`n`nError: $($_.Exception.Message)", "File Read Error", "OK", "Error")
    }
})

$toggleBreakType = {
    $isSingle = $rbSingleBreak.Checked
    $lblCol1.Text = if ($isSingle) { "Column:" } else { "Column 1:" }
    $lblCol2.Visible = !$isSingle; $cmbCol2.Visible = !$isSingle
    $UpdatePreview.Invoke()
}
$rbSingleBreak.Add_CheckedChanged($toggleBreakType); $rbCombinedBreak.Add_CheckedChanged($toggleBreakType)

$cmbCol1.Add_SelectedIndexChanged($UpdatePreview); $cmbCol2.Add_SelectedIndexChanged($UpdatePreview)

$btnAddBreak.Add_Click({
    $breakToAdd = $lblPreview.Text.Replace("Preview: ", "").Trim()
    if ($breakToAdd -and -not $breakToAdd.Contains("(") -and -not $lbDefinedBreaks.Items.Contains($breakToAdd)) {
        $lbDefinedBreaks.Items.Add($breakToAdd)
    }
})

$btnRemoveBreak.Add_Click({ if ($lbDefinedBreaks.SelectedItem) { $lbDefinedBreaks.Items.Remove($lbDefinedBreaks.SelectedItem) } })

$cmbPresets.Add_SelectedIndexChanged({
    $isManual = ($cmbPresets.SelectedItem -eq "(Manual)")
    $txtCombinations.Enabled = $isManual; $numParticipants.Enabled = $isManual; $numMaxPercent.Enabled = $isManual
})

$btnRun.Add_Click({
    # --- Validation ---
    if ($rbCsv.Checked -and -not (Test-Path -Path $txtCsvFile.Text -PathType Leaf)) { [System.Windows.Forms.MessageBox]::Show("Please select a valid CSV file.", "Input Error"); return }
    if ($rbSql.Checked -and [string]::IsNullOrWhiteSpace($txtTableName.Text)) { [System.Windows.Forms.MessageBox]::Show("Please enter a SQL Table Name.", "Input Error"); return }
    if ([string]::IsNullOrWhiteSpace($txtIssuerName.Text)) { [System.Windows.Forms.MessageBox]::Show("Please enter an Issuer Name.", "Input Error"); return }
    if ($lbDefinedBreaks.Items.Count -eq 0) { [System.Windows.Forms.MessageBox]::Show("Please define at least one break for the analysis.", "Input Error"); return }

    # --- Build the Command ---
    $argumentList = New-Object System.Collections.Generic.List[string]
    $definedBreaks = $lbDefinedBreaks.Items
    
    if ($rbCsv.Checked) {
        $command = if ($rbRate.Checked) { "rate" } else { "share" }
        $argumentList.Add($pythonScriptPath); $argumentList.Add($command)
        $argumentList.Add("--csv"); $argumentList.Add($txtCsvFile.Text)
        $argumentList.Add("--issuer"); $argumentList.Add($txtIssuerName.Text)
        $argumentList.Add("--issuer-col"); $argumentList.Add($txtIssuerCol.Text)
        $argumentList.Add("--break"); $definedBreaks | ForEach-Object { $argumentList.Add($_) }
    } else {
        $command = "legacy"
        $argumentList.Add($pythonScriptPath); $argumentList.Add($command)
        $argumentList.Add("--type"); $argumentList.Add("sql")
        $argumentList.Add("--table-name"); $argumentList.Add($txtTableName.Text)
        $argumentList.Add("--issuer-name"); $argumentList.Add($txtIssuerName.Text)
        $argumentList.Add("--issuer-column"); $argumentList.Add($txtIssuerCol.Text)
        $definedBreaks | ForEach-Object { $argumentList.Add("--break-def"); $argumentList.Add($_) }
    }

    if ($cmbPresets.SelectedItem -ne "(Manual)") {
        $argumentList.Add("--preset"); $argumentList.Add($cmbPresets.SelectedItem)
    } else {
        if ($rbCsv.Checked) {
             $argumentList.Add("--participants"); $argumentList.Add($numParticipants.Value)
             $argumentList.Add("--max-percent"); $argumentList.Add($numMaxPercent.Value)
             $argumentList.Add("--combinations"); $txtCombinations.Text.Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries) | ForEach-Object { $argumentList.Add($_) }
        } else {
             $argumentList.Add("--num-participants"); $argumentList.Add($numParticipants.Value)
             $argumentList.Add("--max-percentage"); $argumentList.Add($numMaxPercent.Value)
             $argumentList.Add("--comb-priority"); $txtCombinations.Text.Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries) | ForEach-Object { $argumentList.Add($_) }
        }
    }

    # --- Execute the Script ---
    $argumentString = ($argumentList | ForEach-Object { '"' + $_.Replace('"', '`"') + '"' }) -join ' '
    $pythonExecutable = "py"

    $txtOutput.Clear()
    $txtOutput.AppendText("Starting analysis...`n`n")
    $txtOutput.AppendText("Executing: $pythonExecutable $argumentString`n")
    $txtOutput.AppendText("--------------------------------------------------`n")
    
    $tabControl.SelectedTab = $outputTab
    $statusBar.Text = "Running... Please wait."; $btnRun.Enabled = $false; $mainForm.Cursor = [System.Windows.Forms.Cursors]::WaitCursor; $mainForm.Refresh()

    $process = Start-Process $pythonExecutable -ArgumentList $argumentString -NoNewWindow -PassThru -RedirectStandardOutput "$PSScriptRoot\stdout.log" -RedirectStandardError "$PSScriptRoot\stderr.log" -Wait
    
    $stdout = Get-Content "$PSScriptRoot\stdout.log" -ErrorAction SilentlyContinue
    $stderr = Get-Content "$PSScriptRoot\stderr.log" -ErrorAction SilentlyContinue
    
    $txtOutput.AppendText($stdout -join "`n")
    
    if ($stderr) {
        $txtOutput.SelectionColor = "Red"; $txtOutput.AppendText("`n`n--- ERRORS ---`n"); $txtOutput.AppendText($stderr -join "`n")
    }
    
    $txtOutput.AppendText("`n--------------------------------------------------`n")
    if ($process.ExitCode -eq 0) {
        $txtOutput.SelectionColor = "LawnGreen"; $txtOutput.AppendText("Analysis completed successfully."); $statusBar.Text = "Finished successfully."
    } else {
        $txtOutput.SelectionColor = "Red"; $txtOutput.AppendText("Analysis finished with errors. See output above."); $statusBar.Text = "Finished with errors."
    }

    Remove-Item "$PSScriptRoot\stdout.log", "$PSScriptRoot\stderr.log" -ErrorAction SilentlyContinue

    $btnRun.Enabled = $true; $mainForm.Cursor = [System.Windows.Forms.Cursors]::Default
})

# --- SHOW THE FORM ---
$mainForm.ShowDialog() | Out-Null
