param(
    [int]$FromYear,
    [int]$ToYear,
    [switch]$DryRun,
    [int]$Retry = 3
)

if (-not $PSBoundParameters.ContainsKey('FromYear')) { $FromYear = 2000 }
if (-not $PSBoundParameters.ContainsKey('ToYear')) { $ToYear = 2024 }

$ErrorActionPreference = 'Stop'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

function Ensure-Dirs {
    param([string]$Root)
    $root = (Resolve-Path $Root).Path
    $pdfDir = Join-Path $root 'pdfs_c3414'
    if (!(Test-Path $pdfDir)) { New-Item -ItemType Directory -Path $pdfDir | Out-Null }
    return @{ root = $root; pdfs = $pdfDir }
}

function New-HttpClient {
    try { Add-Type -AssemblyName System.Net.Http } catch {}
    $handler = New-Object System.Net.Http.HttpClientHandler
    $handler.AllowAutoRedirect = $false  # 我们手动处理，便于拿到最终 URL
    try {
        $handler.AutomaticDecompression = [System.Net.DecompressionMethods]::GZip -bor [System.Net.DecompressionMethods]::Deflate -bor [System.Net.DecompressionMethods]::Brotli
    } catch {
        $handler.AutomaticDecompression = [System.Net.DecompressionMethods]::GZip -bor [System.Net.DecompressionMethods]::Deflate
    }
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(60)
    $client.DefaultRequestHeaders.UserAgent.ParseAdd('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36')
    $client.DefaultRequestHeaders.Accept.ParseAdd('application/pdf,application/octet-stream;q=0.9,text/html;q=0.8,*/*;q=0.7')
    return $client
}

function Get-FinalAndBytes {
    param([string]$SeedUrl, [int]$Retry)
    $client = New-HttpClient
    $cur = [Uri]$SeedUrl
    for ($attempt = 0; $attempt -lt $Retry; $attempt++) {
        try {
            for ($i = 0; $i -lt 10; $i++) {
                $req = New-Object System.Net.Http.HttpRequestMessage([System.Net.Http.HttpMethod]::Get, $cur)
                $resp = $client.SendAsync($req, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
                $status = [int]$resp.StatusCode
                if ($status -ge 300 -and $status -lt 400 -and $resp.Headers.Location) {
                    $loc = $resp.Headers.Location
                    if (-not $loc.IsAbsoluteUri) { $cur = New-Object System.Uri($cur, $loc) } else { $cur = $loc }
                    continue
                }
                # 读取内容
                $bytes = $resp.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
                $ctype = ($resp.Content.Headers.ContentType.MediaType) 2>$null
                $isPdfHeader = ($bytes.Length -ge 4 -and [System.Text.Encoding]::ASCII.GetString($bytes,0,4) -eq '%PDF')
                if ($isPdfHeader -or ($ctype -and $ctype -like 'application/pdf*')) {
                    return @($cur.AbsoluteUri, $bytes)
                }
                # HTML 中直接查找 printable_post_collections 直链（绝对或相对）
                $html = try { [System.Text.Encoding]::UTF8.GetString($bytes) } catch { '' }
                $mAbs = [regex]::Match($html, 'https?://[^"''>\s]+/downloads/printable_post_collections/\d+', 'IgnoreCase')
                if ($mAbs.Success) { $cur = [Uri]$mAbs.Value; continue }
                $mRel = [regex]::Match($html, '/downloads/printable_post_collections/\d+', 'IgnoreCase')
                if ($mRel.Success) { $cur = New-Object System.Uri($cur, $mRel.Value); continue }
                # 无法解析成 PDF，返回当前 URL 与字节（可能是 HTML）
                return @($cur.AbsoluteUri, $bytes)
            }
        } catch {
            Start-Sleep -Milliseconds (300 * ($attempt + 1))
        }
    }
    return @($null, $null)
}

function Save-Bytes {
    param([byte[]]$Bytes, [string]$OutPath)
    if ($DryRun) { return }
    [System.IO.File]::WriteAllBytes($OutPath, $Bytes)
}

$dirs = Ensure-Dirs (Split-Path -Parent $MyInvocation.MyCommand.Path)
$csvPath = Join-Path $dirs.root 'amc10_pdfs_c3414.csv'
$results = @()

Write-Host ("Processing AMC 10 c3414 PDFs: {0}..{1}" -f $FromYear, $ToYear) -ForegroundColor Cyan
foreach ($y in $FromYear..$ToYear) {
    $seed = "https://artofproblemsolving.com/community/contest/download/c3414_amc_10/$y"
    $final = $null; $bytes = $null
    $pair = Get-FinalAndBytes -SeedUrl $seed -Retry $Retry
    if ($pair -and $pair.Length -ge 2) { $final = $pair[0]; $bytes = $pair[1] }
    $isPdf = ($bytes -and $bytes.Length -ge 4 -and [System.Text.Encoding]::ASCII.GetString($bytes,0,4) -eq '%PDF')
    $status = if ($final -and $isPdf) { 'ok' } elseif ($final) { 'html_content' } else { 'resolve_failed' }
    $file = Join-Path $dirs.pdfs ("{0}_AMC_10_Problems.pdf" -f $y)
    if ($status -eq 'ok' -and -not $DryRun) {
        try { if (!(Test-Path $file)) { Save-Bytes -Bytes $bytes -OutPath $file } } catch { $status = 'save_failed' }
    }
    $finalOut = if ($null -eq $final) { '' } else { $final }
    $results += [pscustomobject]@{ year = $y; seed_url = $seed; final_url = $finalOut; status = $status; file = $file }
}

$results | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $csvPath
Write-Host "Saved mapping: $csvPath" -ForegroundColor Green
Write-Host "PDFs dir     : $($dirs.pdfs)" -ForegroundColor Green
