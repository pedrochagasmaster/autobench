# Benchmark Tool GUI
# PowerShell GUI interface for benchmark_tool.py

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# Create the main form
$form = New-Object System.Windows.Forms.Form
$form.Text = "Analytics Benchmark Tool"
$form.Size = New-Object System.Drawing.Size(800, 700)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false

# Create controls
$lblTitle = New-Object System.Windows.Forms.Label
$lblTitle.Text = "Analytics Benchmark Tool"
$lblTitle.Font = New-Object System.Drawing.Font("Arial", 16, [System.Drawing.FontStyle]::Bold)
$lblTitle.Location = New-Object System.Drawing.Point(20, 20)
$lblTitle.Size = New-Object System.Drawing.Size(300, 30)
$form.Controls.Add($lblTitle)

# Analysis Type
$lblAnalysisType = New-Object System.Windows.Forms.Label
$lblAnalysisType.Text = "Analysis Type:"
$lblAnalysisType.Location = New-Object System.Drawing.Point(20, 70)
$lblAnalysisType.Size = New-Object System.Drawing.Size(100, 20)
$form.Controls.Add($lblAnalysisType)

$cmbAnalysisType = New-Object System.Windows.Forms.ComboBox
$cmbAnalysisType.Location = New-Object System.Drawing.Point(130, 70)
$cmbAnalysisType.Size = New-Object System.Drawing.Size(150, 20)
$cmbAnalysisType.Items.AddRange(@("rate", "share", "legacy"))
$cmbAnalysisType.SelectedIndex = 0
$form.Controls.Add($cmbAnalysisType)

# CSV File
$lblCsvFile = New-Object System.Windows.Forms.Label
$lblCsvFile.Text = "CSV File:"
$lblCsvFile.Location = New-Object System.Drawing.Point(20, 110)
$lblCsvFile.Size = New-Object System.Drawing.Size(100, 20)
$form.Controls.Add($lblCsvFile)

$txtCsvFile = New-Object System.Windows.Forms.TextBox
$txtCsvFile.Location = New-Object System.Drawing.Point(130, 110)
$txtCsvFile.Size = New-Object System.Drawing.Size(400, 20)
$form.Controls.Add($txtCsvFile)

$btnBrowseCsv = New-Object System.Windows.Forms.Button
$btnBrowseCsv.Text = "Browse"
$btnBrowseCsv.Location = New-Object System.Drawing.Point(540, 110)
$btnBrowseCsv.Size = New-Object System.Drawing.Size(80, 23)
$btnBrowseCsv.Add_Click({
    $openFileDialog = New-Object System.Windows.Forms.OpenFileDialog
    $openFileDialog.Filter = "CSV files (*.csv)|*.csv|All files (*.*)|*.*"
    $openFileDialog.Title = "Select CSV File"
    if ($openFileDialog.ShowDialog() -eq "OK") {
        $txtCsvFile.Text = $openFileDialog.FileName
    }
})
$form.Controls.Add($btnBrowseCsv)

# Issuer Name
$lblIssuer = New-Object System.Windows.Forms.Label
$lblIssuer.Text = "Issuer Name:"
$lblIssuer.Location = New-Object System.Drawing.Point(20, 150)
$lblIssuer.Size = New-Object System.Drawing.Size(100, 20)
$form.Controls.Add($lblIssuer)

$txtIssuer = New-Object System.Windows.Forms.TextBox
$txtIssuer.Location = New-Object System.Drawing.Point(130, 150)
$txtIssuer.Size = New-Object System.Drawing.Size(400, 20)
$txtIssuer.Text = "BANCO SANTANDER (BRASIL) S.A."
$form.Controls.Add($txtIssuer)

# Issuer Column
$lblIssuerCol = New-Object System.Windows.Forms.Label
$lblIssuerCol.Text = "Issuer Column:"
$lblIssuerCol.Location = New-Object System.Drawing.Point(20, 190)
$lblIssuerCol.Size = New-Object System.Drawing.Size(100, 20)
$form.Controls.Add($lblIssuerCol)

$txtIssuerCol = New-Object System.Windows.Forms.TextBox
$txtIssuerCol.Location = New-Object System.Drawing.Point(130, 190)
$txtIssuerCol.Size = New-Object System.Drawing.Size(150, 20)
$txtIssuerCol.Text = "issuer_name"
$form.Controls.Add($txtIssuerCol)

# Participants
$lblParticipants = New-Object System.Windows.Forms.Label
$lblParticipants.Text = "Participants:"
$lblParticipants.Location = New-Object System.Drawing.Point(20, 230)
$lblParticipants.Size = New-Object System.Drawing.Size(100, 20)
$form.Controls.Add($lblParticipants)

$numParticipants = New-Object System.Windows.Forms.NumericUpDown
$numParticipants.Location = New-Object System.Drawing.Point(130, 230)
$numParticipants.Size = New-Object System.Drawing.Size(80, 20)
$numParticipants.Minimum = 1
$numParticipants.Maximum = 20
$numParticipants.Value = 4
$form.Controls.Add($numParticipants)

# Max Percent
$lblMaxPercent = New-Object System.Windows.Forms.Label
$lblMaxPercent.Text = "Max Percent:"
$lblMaxPercent.Location = New-Object System.Drawing.Point(220, 230)
$lblMaxPercent.Size = New-Object System.Drawing.Size(100, 20)
$form.Controls.Add($lblMaxPercent)

$numMaxPercent = New-Object System.Windows.Forms.NumericUpDown
$numMaxPercent.Location = New-Object System.Drawing.Point(330, 230)
$numMaxPercent.Size = New-Object System.Drawing.Size(80, 20)
$numMaxPercent.Minimum = 1
$numMaxPercent.Maximum = 100
$numMaxPercent.Value = 35
$form.Controls.Add($numMaxPercent)

# Preset
$lblPreset = New-Object System.Windows.Forms.Label
$lblPreset.Text = "Preset:"
$lblPreset.Location = New-Object System.Drawing.Point(20, 270)
$lblPreset.Size = New-Object System.Drawing.Size(100, 20)
$form.Controls.Add($lblPreset)

$cmbPreset = New-Object System.Windows.Forms.ComboBox
$cmbPreset.Location = New-Object System.Drawing.Point(130, 270)
$cmbPreset.Size = New-Object System.Drawing.Size(150, 20)
$cmbPreset.Items.Add("None")
$cmbPreset.SelectedIndex = 0
$form.Controls.Add($cmbPreset)

# Load presets from JSON file
$btnLoadPresets = New-Object System.Windows.Forms.Button
$btnLoadPresets.Text = "Load Presets"
$btnLoadPresets.Location = New-Object System.Drawing.Point(290, 270)
$btnLoadPresets.Size = New-Object System.Drawing.Size(80, 23)
$btnLoadPresets.Add_Click({
    if (Test-Path "presets.json") {
        try {
            $presets = Get-Content "presets.json" | ConvertFrom-Json
            $cmbPreset.Items.Clear()
            $cmbPreset.Items.Add("None")
            foreach ($presetName in $presets.PSObject.Properties.Name) {
                $cmbPreset.Items.Add($presetName)
            }
            $cmbPreset.SelectedIndex = 0
            [System.Windows.Forms.MessageBox]::Show("Presets loaded successfully!", "Success", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information)
        }
        catch {
            [System.Windows.Forms.MessageBox]::Show("Error loading presets: $($_.Exception.Message)", "Error", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)
        }
    }
    else {
        [System.Windows.Forms.MessageBox]::Show("presets.json not found!", "Warning", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning)
    }
})
$form.Controls.Add($btnLoadPresets)

# Breaks
$lblBreaks = New-Object System.Windows.Forms.Label
$lblBreaks.Text = "Breaks (one per line):"
$lblBreaks.Location = New-Object System.Drawing.Point(20, 310)
$lblBreaks.Size = New-Object System.Drawing.Size(150, 20)
$form.Controls.Add($lblBreaks)

$txtBreaks = New-Object System.Windows.Forms.TextBox
$txtBreaks.Location = New-Object System.Drawing.Point(20, 330)
$txtBreaks.Size = New-Object System.Drawing.Size(400, 80)
$txtBreaks.Multiline = $true
$txtBreaks.ScrollBars = "Vertical"
$txtBreaks.Text = "wallet_flag`nmonth_year`nsuper_industry_name_grouped"
$form.Controls.Add($txtBreaks)

# Combinations
$lblCombinations = New-Object System.Windows.Forms.Label
$lblCombinations.Text = "Combinations (space-separated):"
$lblCombinations.Location = New-Object System.Drawing.Point(20, 430)
$lblCombinations.Size = New-Object System.Drawing.Size(200, 20)
$form.Controls.Add($lblCombinations)

$txtCombinations = New-Object System.Windows.Forms.TextBox
$txtCombinations.Location = New-Object System.Drawing.Point(20, 450)
$txtCombinations.Size = New-Object System.Drawing.Size(200, 20)
$txtCombinations.Text = "5 1 2"
$form.Controls.Add($txtCombinations)

# Output
$lblOutput = New-Object System.Windows.Forms.Label
$lblOutput.Text = "Output:"
$lblOutput.Location = New-Object System.Drawing.Point(20, 490)
$lblOutput.Size = New-Object System.Drawing.Size(100, 20)
$form.Controls.Add($lblOutput)

$txtOutput = New-Object System.Windows.Forms.TextBox
$txtOutput.Location = New-Object System.Drawing.Point(20, 510)
$txtOutput.Size = New-Object System.Drawing.Size(600, 80)
$txtOutput.Multiline = $true
$txtOutput.ScrollBars = "Vertical"
$txtOutput.ReadOnly = $true
$txtOutput.BackColor = [System.Drawing.Color]::LightGray
$form.Controls.Add($txtOutput)

# Buttons
$btnRun = New-Object System.Windows.Forms.Button
$btnRun.Text = "Run Analysis"
$btnRun.Location = New-Object System.Drawing.Point(20, 610)
$btnRun.Size = New-Object System.Drawing.Size(120, 30)
$btnRun.BackColor = [System.Drawing.Color]::LightGreen
$form.Controls.Add($btnRun)

$btnClear = New-Object System.Windows.Forms.Button
$btnClear.Text = "Clear Output"
$btnClear.Location = New-Object System.Drawing.Point(150, 610)
$btnClear.Size = New-Object System.Drawing.Size(100, 30)
$form.Controls.Add($btnClear)

$btnExit = New-Object System.Windows.Forms.Button
$btnExit.Text = "Exit"
$btnExit.Location = New-Object System.Drawing.Point(260, 610)
$btnExit.Size = New-Object System.Drawing.Size(80, 30)
$form.Controls.Add($btnExit)

# Event handlers
$btnClear.Add_Click({
    $txtOutput.Text = ""
})

$btnExit.Add_Click({
    $form.Close()
})

$btnRun.Add_Click({
    # Validate inputs
    if ([string]::IsNullOrWhiteSpace($txtCsvFile.Text)) {
        [System.Windows.Forms.MessageBox]::Show("Please select a CSV file!", "Validation Error", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)
        return
    }
    
    if ([string]::IsNullOrWhiteSpace($txtIssuer.Text)) {
        [System.Windows.Forms.MessageBox]::Show("Please enter an issuer name!", "Validation Error", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)
        return
    }
    
    if ([string]::IsNullOrWhiteSpace($txtBreaks.Text)) {
        [System.Windows.Forms.MessageBox]::Show("Please enter at least one break!", "Validation Error", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)
        return
    }
    
    # Build command
    $command = "py benchmark_tool.py"
    $command += " $($cmbAnalysisType.SelectedItem)"
    $command += " --csv `"$($txtCsvFile.Text)`""
    $command += " --issuer `"$($txtIssuer.Text)`""
    $command += " --issuer-col $($txtIssuerCol.Text)"
    $command += " --participants $($numParticipants.Value)"
    $command += " --max-percent $($numMaxPercent.Value)"
    
    # Add preset if selected
    if ($cmbPreset.SelectedItem -ne "None") {
        $command += " --preset $($cmbPreset.SelectedItem)"
    }
    
    # Add breaks
    $breaks = $txtBreaks.Text -split "`r?`n" | Where-Object { ![string]::IsNullOrWhiteSpace($_) }
    foreach ($break in $breaks) {
        $command += " --break $break"
    }
    
    # Add combinations
    $command += " --combinations $($txtCombinations.Text)"
    
    # Display command
    $txtOutput.AppendText("Command: $command`n`n")
    $txtOutput.AppendText("Running analysis...`n")
    $txtOutput.ScrollToCaret()
    
    # Run the command
    try {
        $result = Invoke-Expression $command 2>&1
        $txtOutput.AppendText("Output:`n$result`n")
        $txtOutput.AppendText("`nAnalysis completed!`n")
    }
    catch {
        $txtOutput.AppendText("Error: $($_.Exception.Message)`n")
    }
    
    $txtOutput.ScrollToCaret()
})

# Load presets on startup
if (Test-Path "presets.json") {
    try {
        $presets = Get-Content "presets.json" | ConvertFrom-Json
        $cmbPreset.Items.Clear()
        $cmbPreset.Items.Add("None")
        foreach ($presetName in $presets.PSObject.Properties.Name) {
            $cmbPreset.Items.Add($presetName)
        }
        $cmbPreset.SelectedIndex = 0
    }
    catch {
        # Silently fail if presets can't be loaded
    }
}

# Show the form
$form.ShowDialog()
