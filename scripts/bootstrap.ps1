<#
.SYNOPSIS
    Holt die externen Abhaengigkeiten nach ref/.

.DESCRIPTION
    Klont Recompiler und Laufzeit auf feste Commits und laedt LLVM mit
    Entwicklungsdateien. Es werden keine Spieldaten geholt.

    Die Commits sind bewusst festgenagelt, damit ein Build reproduzierbar
    bleibt; siehe docs/01-MACHBARKEIT.md, Abschnitt 1.

.PARAMETER SkipLlvm
    LLVM nicht laden (etwa wenn bereits eine passende 19er/20er Installation
    vorliegt, die build.ps1 ueber -LlvmRoot bekommt).
#>
[CmdletBinding()]
param(
    [switch]$SkipLlvm,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$RefRoot = Join-Path $RepoRoot 'ref'

# Geprueft am 2026-09-09. Aktualisierungen bitte zusammen mit der
# Machbarkeitsanalyse nachziehen.
$Dependencies = @(
    @{
        Name = 'DolRecomp'
        Url = 'https://github.com/ExpansionPak/DolRecomp.git'
        Commit = '40637c4683bd2820ac5b23607ee344720beb26df'
        Submodules = $false
    },
    @{
        Name = 'ModernGekko'
        Url = 'https://github.com/ExpansionPak/ModernGekko.git'
        Commit = '5417826c31187d4dadf8588c7aa25bf107782936'
        Submodules = $true
    }
)

# ModernGekko pinnt sein Vendor-Submodul (RecompCore) auf den Branch
# moderngekko-vendor. Dessen GXRuntime steht auf CPU-ABI 3, waehrend
# ModernGekkos eigene Laufzeit ABI 4 verlangt. Ein damit gebautes Spielmodul
# wird beim Start abgewiesen ("native module was rejected: CPU ABI mismatch").
#
# Der Branch moderngekko-runtime traegt GXRuntime mit ABI 4 und dem Feld
# cycle_budget und passt damit zur Laufzeit. Wir setzen das Submodul darauf.
# Siehe docs/02-STATUS.md.
$RecompCoreCommit = 'c6a600eb434056873566ef951d11974619a7ed31'
$RecompCoreBranch = 'moderngekko-runtime'

# DolRecomp akzeptiert ausschliesslich LLVM 19.x oder 20.x.
$LlvmVersion = '20.1.8'
$LlvmUrl = "https://github.com/llvm/llvm-project/releases/download/llvmorg-$LlvmVersion/clang+llvm-$LlvmVersion-x86_64-pc-windows-msvc.tar.xz"

function Get-Repository {
    param([hashtable]$Dependency)

    $target = Join-Path $RefRoot $Dependency.Name
    if ((Test-Path $target) -and -not $Force) {
        Write-Host "$($Dependency.Name): vorhanden, uebersprungen." -ForegroundColor DarkGray
        return
    }
    if (Test-Path $target) { Remove-Item -Recurse -Force $target }

    Write-Host "==> $($Dependency.Name) klonen" -ForegroundColor Cyan
    # Voller Klon, damit der feste Commit sicher enthalten ist.
    & git clone --quiet $Dependency.Url $target
    if ($LASTEXITCODE -ne 0) { throw "Klonen von $($Dependency.Name) fehlgeschlagen." }

    & git -C $target checkout --quiet $Dependency.Commit
    if ($LASTEXITCODE -ne 0) { throw "Commit $($Dependency.Commit) nicht gefunden." }

    if ($Dependency.Submodules) {
        Write-Host "    Submodule (dauert, Dolphin-Baum)" -ForegroundColor DarkGray
        # Der parallele Abruf ist gelegentlich unzuverlaessig; einmal
        # nachfassen bereinigt abgebrochene verschachtelte Module.
        & git -C $target submodule update --init --recursive --depth 1 -j4
        & git -C $target submodule update --init --recursive --depth 1
        if ($LASTEXITCODE -ne 0) { throw "Submodule von $($Dependency.Name) unvollstaendig." }
    }
}

function Get-Llvm {
    $target = Join-Path $RefRoot 'llvm'
    $marker = Join-Path $target 'lib\cmake\llvm\LLVMConfig.cmake'
    if ((Test-Path $marker) -and -not $Force) {
        Write-Host "LLVM: vorhanden, uebersprungen." -ForegroundColor DarkGray
        return
    }

    $archive = Join-Path $RefRoot 'llvm.tar.xz'
    Write-Host "==> LLVM $LlvmVersion laden (rund 940 MB)" -ForegroundColor Cyan
    curl.exe -sL -o $archive $LlvmUrl
    if ($LASTEXITCODE -ne 0) { throw 'Download von LLVM fehlgeschlagen.' }

    Write-Host '    entpacken' -ForegroundColor DarkGray
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    tar.exe -xf $archive -C $target --strip-components=1
    if ($LASTEXITCODE -ne 0) { throw 'Entpacken von LLVM fehlgeschlagen.' }
    Remove-Item $archive -Force

    if (-not (Test-Path $marker)) { throw "LLVM wurde entpackt, aber $marker fehlt." }
    Write-Host "LLVM $LlvmVersion bereit." -ForegroundColor Green
}

function Add-Patches {
    <#
        Das LLVM-Backend des eigenstaendigen DolRecomp (40637c46) nutzt
        __builtin_popcountll und laesst sich damit nicht mit MSVC uebersetzen.

        ModernGekkos eingebettetes DolRecomp-Submodul ist eine aeltere,
        andere Revision (1bec3554) ohne diese Stelle und braucht den Patch
        nicht. Er wird deshalb bewusst nur auf den eigenstaendigen Baum
        angewandt.
    #>
    $patches = @(
        @{
            File = 'dolrecomp-msvc-popcount.patch'
            Target = Join-Path $RefRoot 'DolRecomp'
        },
        # Zwei Luecken im Branch moderngekko-runtime:
        #
        # 1. StaticRecompCore::GetExceptionCheckTarget ist als override
        #    deklariert, obwohl JitBase die Methode nicht kennt und niemand sie
        #    aufruft. MSVC bricht damit ab (C3668). Der Patch entfernt nur das
        #    gegenstandslose override.
        # 2. GXRuntimes cpu.h fehlt der Inline-Wrapper ppc_fp_available_inline,
        #    den DolRecomps Emitter erzeugt. Er wird wortgleich aus
        #    DolRecomp/src/cpu/cpu.h uebernommen (dieselbe Quelle, dasselbe
        #    Repository).
        @{
            File = 'recompcore-abi-gaps.patch'
            Target = Join-Path $RefRoot 'ModernGekko\vendor\dolphin'
        }
    )

    foreach ($entry in $patches) {
        $patch = Join-Path $RepoRoot "patches\$($entry.File)"
        $target = $entry.Target
        if (-not (Test-Path $patch)) { continue }
        if (-not (Test-Path (Join-Path $target '.git'))) { continue }

        # Ein bereits angewandter Patch ist kein Fehler.
        & git -C $target apply --reverse --check $patch 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Patch bereits vorhanden: $($entry.File)" -ForegroundColor DarkGray
            continue
        }

        & git -C $target apply $patch
        if ($LASTEXITCODE -ne 0) { throw "Patch $($entry.File) liess sich nicht anwenden." }
        Write-Host "Patch angewandt: $($entry.File)" -ForegroundColor DarkGray
    }
}

function Set-RecompCoreRevision {
    <# Setzt das Vendor-Submodul auf die zur Laufzeit passende ABI (siehe oben). #>
    $vendor = Join-Path $RefRoot 'ModernGekko\vendor\dolphin'
    if (-not (Test-Path (Join-Path $vendor '.git'))) { return }

    $current = (& git -C $vendor rev-parse HEAD).Trim()
    if ($current -eq $RecompCoreCommit) {
        Write-Host 'RecompCore: bereits auf der passenden Revision.' -ForegroundColor DarkGray
        return
    }

    Write-Host "==> RecompCore auf $RecompCoreBranch setzen" -ForegroundColor Cyan
    & git -C $vendor fetch --depth 1 origin "${RecompCoreBranch}:refs/remotes/origin/$RecompCoreBranch"
    if ($LASTEXITCODE -ne 0) { throw "Branch $RecompCoreBranch konnte nicht geholt werden." }

    & git -C $vendor checkout --quiet --detach $RecompCoreCommit
    if ($LASTEXITCODE -ne 0) { throw "RecompCore-Commit $RecompCoreCommit nicht gefunden." }

    & git -C $vendor submodule update --init --recursive --depth 1 -j4
    & git -C $vendor submodule update --init --recursive --depth 1
    if ($LASTEXITCODE -ne 0) { throw 'Submodule von RecompCore unvollstaendig.' }

    $abi = Select-String -Path (Join-Path $vendor 'GXRuntime\include\core\cpu.h') `
                         -Pattern 'GXRUNTIME_CPU_ABI_VERSION\s+(\d+)u' | Select-Object -First 1
    if ($abi) { Write-Host "  GXRuntime CPU-ABI: $($abi.Matches[0].Groups[1].Value)" -ForegroundColor DarkGray }
}

New-Item -ItemType Directory -Force -Path $RefRoot | Out-Null
foreach ($dependency in $Dependencies) { Get-Repository -Dependency $dependency }
Set-RecompCoreRevision
Add-Patches
if (-not $SkipLlvm) { Get-Llvm }

Write-Host ''
Write-Host 'Abhaengigkeiten bereit. Weiter mit: ./scripts/build.ps1 -Target all' -ForegroundColor Green
