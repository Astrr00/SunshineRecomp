<#
.SYNOPSIS
    Baut die Werkzeugkette des Ports unter Windows x86-64.

.DESCRIPTION
    Baut den Recompiler (DolRecomp) und die Laufzeit (ModernGekko) aus den nach
    ref/ geklonten Quellen. Es werden keine Spieldaten benoetigt oder erzeugt.

    Zwei Besonderheiten, die beim ersten Aufsetzen Zeit gekostet haben und
    deshalb hier automatisiert sind:

    1. DolRecomp braucht fuer die ModernGekko-Laufzeit zwingend sein
       LLVM-Backend ("the ModernGekko runtime requires the LLVM backend").
       Akzeptiert wird nur LLVM 19.x oder 20.x.
    2. Der LLVM-Backend-Code nutzt __builtin_popcountll und laesst sich damit
       nicht mit MSVC uebersetzen. DolRecomp wird deshalb mit clang-cl gebaut,
       ModernGekko weiterhin mit MSVC.

.PARAMETER Target
    Was gebaut wird: dolrecomp, moderngekko oder all (Vorgabe).

.PARAMETER LlvmRoot
    Wurzel einer LLVM-19/20-Installation mit Entwicklungsdateien.
    Vorgabe: ref/llvm (siehe scripts/bootstrap.ps1).

.EXAMPLE
    ./scripts/build.ps1 -Target all -Test
#>
[CmdletBinding()]
param(
    [ValidateSet('dolrecomp', 'moderngekko', 'all')]
    [string]$Target = 'all',
    [ValidateSet('Debug', 'Release', 'RelWithDebInfo')]
    [string]$Config = 'Release',
    [string]$LlvmRoot,
    [switch]$Test
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$RefRoot = Join-Path $RepoRoot 'ref'
if (-not $LlvmRoot) { $LlvmRoot = Join-Path $RefRoot 'llvm' }

function Find-VcVars {
    <# Sucht vcvars64.bat ueber vswhere, mit Rueckfall auf alle Installationen. #>
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (Test-Path $vswhere) {
        $preferred = & $vswhere -latest -products * `
            -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
            -property installationPath 2>$null
        foreach ($path in @($preferred) + @(& $vswhere -all -products * -property installationPath 2>$null)) {
            if (-not $path) { continue }
            $candidate = Join-Path $path 'VC\Auxiliary\Build\vcvars64.bat'
            if (Test-Path $candidate) { return $candidate }
        }
    }
    throw "MSVC wurde nicht gefunden. Visual Studio 2022 Build Tools mit der C++-Arbeitslast werden benoetigt."
}

function Invoke-InMsvc {
    param([string]$Command, [string]$What)

    Write-Host "==> $What" -ForegroundColor Cyan
    # vcvars muss im selben cmd-Prozess laufen. Die Ausgabe geht bewusst nach
    # Write-Host, damit sie nicht als Rueckgabewert in die Pipeline geraet.
    & cmd /c "`"$script:VcVars`" >nul 2>&1 && $Command" | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) { throw "$What fehlgeschlagen (Exit-Code $LASTEXITCODE)." }
}

function Get-DiaSdkLibrary {
    <# diaguids.lib der lokalen Visual-Studio-Installation. #>
    $vsRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $script:VcVars))
    $lib = Join-Path $vsRoot 'DIA SDK\lib\amd64\diaguids.lib'
    if (Test-Path $lib) { return $lib }
    return $null
}

function Repair-LlvmDiaPath {
    <#
        Die offiziellen LLVM-Windows-Pakete werden gegen das DIA SDK von
        Visual Studio 2019 Professional gebaut und verdrahten dessen Pfad in
        LLVMExports.cmake. Auf Rechnern ohne diese Installation bricht ninja
        mit "diaguids.lib ... missing and no known rule to make it" ab.
        Wir biegen den Pfad einmalig auf die lokale Installation um.
    #>
    param([string]$Root)

    $exports = Join-Path $Root 'lib\cmake\llvm\LLVMExports.cmake'
    if (-not (Test-Path $exports)) { return }

    $content = Get-Content $exports -Raw
    if ($content -notmatch 'Visual Studio/2019') { return }

    $local = Get-DiaSdkLibrary
    if (-not $local) {
        Write-Warning "LLVM verweist auf das DIA SDK von VS 2019, lokal wurde keines gefunden."
        return
    }

    if (-not (Test-Path "$exports.orig")) { Copy-Item $exports "$exports.orig" }
    $localDir = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $local))
    $patched = $content -replace [regex]::Escape('C:/Program Files (x86)/Microsoft Visual Studio/2019/Professional/DIA SDK'), ($localDir -replace '\\', '/')
    Set-Content -Path $exports -Value $patched -Encoding UTF8
    Write-Host "LLVM: DIA-SDK-Pfad auf die lokale Installation umgebogen." -ForegroundColor DarkGray
}

function Assert-Llvm {
    <# Prueft, dass eine brauchbare LLVM-Version mit Entwicklungsdateien vorliegt. #>
    param([string]$Root)

    $config = Join-Path $Root 'lib\cmake\llvm\LLVMConfig.cmake'
    if (-not (Test-Path $config)) {
        throw "LLVM mit Entwicklungsdateien fehlt unter $Root. " +
              "Bitte zuerst ./scripts/bootstrap.ps1 ausfuehren."
    }

    $llvmConfig = Join-Path $Root 'bin\llvm-config.exe'
    if (Test-Path $llvmConfig) {
        $version = (& $llvmConfig --version).Trim()
        $major = [int]($version -split '\.')[0]
        if ($major -lt 19 -or $major -ge 21) {
            throw "DolRecomp verlangt LLVM 19 oder 20, gefunden $version unter $Root."
        }
        Write-Host "LLVM: $version" -ForegroundColor DarkGray
    }

    Repair-LlvmDiaPath -Root $Root
}

function Assert-Source {
    param([string]$Path, [string]$Name, [string]$Url)
    if (-not (Test-Path (Join-Path $Path 'CMakeLists.txt'))) {
        throw "$Name fehlt unter $Path. Erwartet wird ein Klon von $Url"
    }
}

$script:VcVars = Find-VcVars
Write-Host "MSVC-Umgebung: $script:VcVars" -ForegroundColor DarkGray

if ($Target -in @('dolrecomp', 'all')) {
    $src = Join-Path $RefRoot 'DolRecomp'
    Assert-Source $src 'DolRecomp' 'https://github.com/ExpansionPak/DolRecomp'
    Assert-Llvm -Root $LlvmRoot

    # clang-cl statt MSVC: Der LLVM-Backend-Code nutzt GCC/Clang-Builtins.
    $clangCl = (Join-Path $LlvmRoot 'bin\clang-cl.exe') -replace '\\', '/'
    if (-not (Test-Path $clangCl)) { throw "clang-cl.exe fehlt unter $LlvmRoot\bin." }

    $build = Join-Path $src 'build-llvm'
    $options = @(
        "-DCMAKE_BUILD_TYPE=$Config",
        '-DDOLRECOMP_ENABLE_LLVM=ON',
        "-DLLVM_DIR=`"$(($LlvmRoot -replace '\\','/'))/lib/cmake/llvm`"",
        "-DCMAKE_C_COMPILER=`"$clangCl`"",
        "-DCMAKE_CXX_COMPILER=`"$clangCl`""
    ) -join ' '

    Invoke-InMsvc "cmake -S `"$src`" -B `"$build`" -G Ninja $options" 'DolRecomp konfigurieren'
    Invoke-InMsvc "cmake --build `"$build`"" 'DolRecomp bauen'
    if ($Test) { Invoke-InMsvc "ctest --test-dir `"$build`" --output-on-failure" 'DolRecomp testen' }

    $exe = Join-Path $build 'dolrecomp.exe'
    if (-not (Test-Path $exe)) { throw 'dolrecomp.exe wurde nicht erzeugt.' }
    Write-Host "Recompiler: $exe" -ForegroundColor Green
}

if ($Target -in @('moderngekko', 'all')) {
    $src = Join-Path $RefRoot 'ModernGekko'
    Assert-Source $src 'ModernGekko' 'https://github.com/ExpansionPak/ModernGekko'

    $build = Join-Path $src 'build'

    # Der Baum baut mit /WX (fest in vendor/dolphin/CMakeLists.txt).
    # RelocationAliases.cpp des Branches moderngekko-runtime nutzt
    # std::atomic_store_explicit fuer shared_ptr, das MSVC unter C++20 als
    # veraltet meldet (STL4029). Das von Microsoft dafuer vorgesehene Makro
    # unterdrueckt genau diese Verwarnung.
    #
    # CMAKE_CXX_FLAGS ersetzt die Vorgabe, statt sie zu ergaenzen -- ohne das
    # mitgefuehrte /EHsc scheitert sonst <chrono> an C4530.
    $silence = '/DWIN32 /D_WINDOWS /EHsc ' +
               '/D_SILENCE_CXX20_OLD_SHARED_PTR_ATOMIC_SUPPORT_DEPRECATION_WARNING'

    # GameCube-Controllerprofile statt Wii-Remote: Sunshine ist ein GC-Titel.
    # Das Disc-Werkzeug wird fuer die Umwandlung RVZ -> ISO gebraucht.
    $options = @(
        "-DCMAKE_BUILD_TYPE=$Config",
        '-DMODERNGEKKO_GAMECUBE_CONTROLLERS=ON',
        '-DMODERNGEKKO_FRONTEND_NAME=SunshineRecomp',
        '-DMODERNGEKKO_USER_DIRECTORY_NAME=SunshineRecomp',
        '-DMODERNGEKKO_REQUIRED_DISC_ID=GMSE01',
        '-DMODERNGEKKO_REQUIRED_DOL_SHA256=13934c863d649b1ddca1ca4d7748f49d28a571685cbee5fb1542545c32869955',
        '-DMODERNGEKKO_ENABLE_DISC_TOOL=ON',
        "-DCMAKE_CXX_FLAGS=`"$silence`""
    ) -join ' '

    Invoke-InMsvc "cmake -S `"$src`" -B `"$build`" -G Ninja $options" 'ModernGekko konfigurieren'
    Invoke-InMsvc "cmake --build `"$build`"" 'ModernGekko bauen'
    # dolphin-tool haengt nicht am Standardziel und wird separat gebaut.
    Invoke-InMsvc "cmake --build `"$build`" --target dolphin-tool" 'Disc-Werkzeug bauen'
    if ($Test) { Invoke-InMsvc "ctest --test-dir `"$build`" --output-on-failure -j4" 'ModernGekko testen' }
    Write-Host 'Laufzeit gebaut.' -ForegroundColor Green
}

Write-Host 'Fertig.' -ForegroundColor Green
