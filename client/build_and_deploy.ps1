# 1. Setup Paths
$pythonScript = "H:\mydocs\OfficeMessenger\messaging-app\client\message_client.py"
$localOutputDir = "H:\mydocs\OfficeMessenger\messaging-app\client\output"
$networkDestination = "N:\OfficeMessenger"
$versionFile = "H:\mydocs\OfficeMessenger\messaging-app\client\file_version_info.txt"
$venvActivate = ".\venv\Scripts\Activate.ps1"
$compiler = ".\venv\Scripts\pyinstaller.exe"

# 2. Activate Virtual Environment
if (Test-Path $venvActivate) {
    Write-Host "Activating Virtual Environment..." -ForegroundColor Cyan
    . $venvActivate
} else {
    Write-Host "Error: Virtual environment not found at $venvActivate" -ForegroundColor Red
    exit
}

# 3. Auto-Increment Version Number (Updated for StringStruct)
$versionContent = Get-Content $versionFile -Raw
if ($versionContent -match "FileVersion', u'(\d+)\.(\d+)\.(\d+)'") {
    $major = $Matches[1]
    $minor = $Matches[2]
    $patch = [int]$Matches[3] + 1
    $newVersion = "$major.$minor.$patch"
    
    # Update StringStruct lines
    $versionContent = $versionContent -replace "FileVersion', u'\d+\.\d+\.\d+'", "FileVersion', u'$newVersion'"
    $versionContent = $versionContent -replace "ProductVersion', u'\d+\.\d+\.\d+'", "ProductVersion', u'$newVersion'"
    
    # Update binary tuples
    $versionContent = $versionContent -replace "filevers=\(\d+,\s*\d+,\s*\d+,\s*0\)", "filevers=($major, $minor, $patch, 0)"
    $versionContent = $versionContent -replace "prodvers=\(\d+,\s*\d+,\s*\d+,\s*0\)", "prodvers=($major, $minor, $patch, 0)"
    
    $versionContent | Set-Content $versionFile -NoNewline
    Write-Host "Version bumped to $newVersion" -ForegroundColor Cyan
}

# 4. Run Compilation
Write-Host "Compiling OfficeMessenger $newVersion..." -ForegroundColor Yellow
& $compiler --onefile --noconsole --clean --version-file "$versionFile" --distpath "$localOutputDir" "$pythonScript"

# 5. Deployment & Cleanup
if ($LASTEXITCODE -eq 0) {
    Copy-Item -Path "$localOutputDir\message_client.exe" -Destination "$networkDestination\message_client.exe" -Force
    
    # Clean up PyInstaller temporary files
    Write-Host "Cleaning up build artifacts..." -ForegroundColor Gray
    if (Test-Path ".\build") { Remove-Item -Path ".\build" -Recurse -Force }
    if (Test-Path ".\message_client.spec") { Remove-Item -Path ".\message_client.spec" -Force }

    # Fixed Windows Notification
    $msg = "OfficeMessenger $newVersion deployed to N: drive"
    
    # This long command creates a temporary tray icon just to show the balloon tip
    powershell -Command "[reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null; `$notify = new-object system.windows.forms.notifyicon; `$notify.icon = [system.drawing.icon]::extractassociatedicon((get-process -id `$pid).path); `$notify.visible = `$true; `$notify.ShowBalloonTip(5000, 'Build Success', '$msg', [system.windows.forms.tooltipicon]::Info)"
    
    Write-Host "Successfully deployed $newVersion!" -ForegroundColor Green
} else {
    Write-Host "Build Failed!" -ForegroundColor Red
}