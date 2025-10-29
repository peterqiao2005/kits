param(
    [string]$OnlyBase,       # 如 2005_AMC_10B
    [int]$FromYear,
    [int]$ToYear
)

# 默认参数
if (-not $PSBoundParameters.ContainsKey('FromYear')) { $FromYear = 2000 }
if (-not $PSBoundParameters.ContainsKey('ToYear')) { $ToYear = 2024 }

# 全局错误行为配置
$ErrorActionPreference = 'Stop'

# Ensure TLS 1.2 for HTTPS endpoints
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
} catch {}

function Ensure-Dirs {
    param([string]$Root)
    $out = @{ root = (Resolve-Path $Root).Path }
    $pdfDir = Join-Path $out.root 'pdfs'
    if (!(Test-Path $pdfDir)) { New-Item -ItemType Directory -Path $pdfDir | Out-Null }
    $out['pdfs'] = $pdfDir
    return $out
}

function New-HttpClient {
    try { Add-Type -AssemblyName System.Net.Http } catch {}
    $handler = New-Object System.Net.Http.HttpClientHandler
    try {
        $handler.AutomaticDecompression = [System.Net.DecompressionMethods]::GZip -bor [System.Net.DecompressionMethods]::Deflate -bor [System.Net.DecompressionMethods]::Brotli
    } catch {
        $handler.AutomaticDecompression = [System.Net.DecompressionMethods]::GZip -bor [System.Net.DecompressionMethods]::Deflate
    }
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.DefaultRequestHeaders.UserAgent.ParseAdd('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36')
    $client.DefaultRequestHeaders.Accept.ParseAdd('text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8')
    $client.DefaultRequestHeaders.ConnectionClose = $false
    return $client
}

$script:HttpClient = New-HttpClient

function Get-ContentSafe {
    param([string]$Url)
    try {
        $t = $script:HttpClient.GetAsync($Url)
        $t.Wait()
        $resp = $t.Result
        if (-not $resp.IsSuccessStatusCode) { return $null }
        $t2 = $resp.Content.ReadAsStringAsync()
        $t2.Wait()
        return $t2.Result
    } catch {
        return $null
    }
}

function Parse-IndexForBases {
    param([string]$Html)
    $pattern = [regex]'href="/wiki/index\.php/((20\d{2})_AMC_10(A|B)?)"'
    $bases = @()
    foreach ($m in $pattern.Matches($Html)) {
        $slug = $m.Groups[1].Value
        $year = [int]$m.Groups[2].Value
        if ($year -ge 2000 -and $year -le 2024) {
            $bases += $slug
        }
    }
    $bases | Select-Object -Unique
}

function Find-PdfUrlFromProblemsPage {
    param([string]$Html)
    if (-not $Html) { return $null }
    # Strategy 1: 直接 .pdf 后缀链接
    $m = [regex]::Match($Html, 'href="([^"]+?\.pdf)"', 'IgnoreCase')
    if ($m.Success) {
        $href = $m.Groups[1].Value
        if ($href.StartsWith('//')) { return "https:$href" }
        if ($href.StartsWith('/')) { return "https://artofproblemsolving.com$href" }
        return $href
    }
    # Strategy 2: 锚文本包含 PDF（允许嵌套标签）
    $m2 = [regex]::Match($Html, '<a[^>]+href="([^"]+)"[^>]*>.*?PDF.*?</a>', 'IgnoreCase,Singleline')
    if ($m2.Success) {
        $href = $m2.Groups[1].Value
        if ($href.StartsWith('//')) { return "https:$href" }
        if ($href.StartsWith('/')) { return "https://artofproblemsolving.com$href" }
        return $href
    }
    # Strategy 3: AoPS 社区下载路径
    $m3 = [regex]::Match($Html, 'href="([^"]*?/community/contests/download/[^"]+)"', 'IgnoreCase')
    if ($m3.Success) {
        $href = $m3.Groups[1].Value
        if ($href.StartsWith('//')) { return "https:$href" }
        if ($href.StartsWith('/')) { return "https://artofproblemsolving.com$href" }
        if ($href -notmatch '^https?://') { return "https://artofproblemsolving.com/$href" }
        return $href
    }
    return $null
}

$INDEX_URL = 'https://artofproblemsolving.com/wiki/index.php/AMC_10_Problems_and_Solutions'
$WIKI_BASE = 'https://artofproblemsolving.com/wiki/index.php/'

$dirs = Ensure-Dirs (Split-Path -Parent $MyInvocation.MyCommand.Path)

# 方案A：直接访问索引并解析（优先）
Write-Host "Fetching index..." -ForegroundColor Cyan
$bases = @()
$onlyMode = $false
if ($OnlyBase) {
    $bases = @($OnlyBase)
    $onlyMode = $true
}
if (-not $onlyMode) {
    $indexHtml = Get-ContentSafe $INDEX_URL
    if ($indexHtml) {
        $bases = Parse-IndexForBases $indexHtml
        Write-Host "Found $($bases.Count) entries on index." -ForegroundColor Cyan
    }
}

# 方案B：如果索引获取失败或数量异常，按年份生成候选（2000–2024，含无后缀/A/B）
if (-not $onlyMode -and (-not $indexHtml -or $bases.Count -lt 10)) {
    Write-Host "Index unavailable or sparse, generating candidates by year..." -ForegroundColor Yellow
    $tmp = @()
    foreach ($y in $FromYear..$ToYear) {
        $tmp += "${y}_AMC_10"
        $tmp += "${y}_AMC_10A"
        $tmp += "${y}_AMC_10B"
    }
    $bases = $tmp
}

$entries = @()
foreach ($base in $bases) {
    $problemsSlug = "${base}_Problems"
    $problemsUrl = "$WIKI_BASE$problemsSlug"
    $problemsHtml = Get-ContentSafe $problemsUrl

    $yearMatch = [regex]::Match($base, '^(20\d{2})_AMC_10(A|B)?$')
    $year = if ($yearMatch.Success) { [int]$yearMatch.Groups[1].Value } else { 0 }
    $series = if ($yearMatch.Success) { "10$($yearMatch.Groups[2].Value)" } else { '10' }

    if (-not $problemsHtml) {
        $entries += [pscustomobject]@{
            year = $year; series = $series; base_slug = $base;
            problems_url = $problemsUrl; pdf_url = $null; status = 'problems_page_missing'
        }
        continue
    }

    $pdfUrl = Find-PdfUrlFromProblemsPage $problemsHtml
    $status = if ($pdfUrl) { 'ok' } else { 'pdf_missing' }
    $entries += [pscustomobject]@{
        year = $year; series = $series; base_slug = $base;
        problems_url = $problemsUrl; pdf_url = $pdfUrl; status = $status
    }
}

# Write CSV and JSON
$csvPath = Join-Path $dirs.root 'amc10_pdfs.csv'
$jsonPath = Join-Path $dirs.root 'amc10_pdfs.json'
$entries | Sort-Object year, series | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $csvPath
$entries | Sort-Object year, series | ConvertTo-Json -Depth 4 | Set-Content -Path $jsonPath -Encoding UTF8

Write-Host "Saved mapping:" -ForegroundColor Green
Write-Host "  CSV  : $csvPath"
Write-Host "  JSON : $jsonPath"

# Download PDFs
Write-Host "Downloading PDFs..." -ForegroundColor Cyan
foreach ($e in $entries) {
    if (-not $e.pdf_url) { continue }
    $fileName = "{0}_Problems.pdf" -f $e.base_slug
    $outPath = Join-Path $dirs.pdfs $fileName
    if (Test-Path $outPath -PathType Leaf) { continue }
    try {
        Invoke-WebRequest -Uri $e.pdf_url -OutFile $outPath -UseBasicParsing -TimeoutSec 60
        Start-Sleep -Milliseconds 200
    } catch {
        # Skip failures and continue
    }
}

$ok = ($entries | Where-Object { $_.status -eq 'ok' }).Count
$missPdf = ($entries | Where-Object { $_.status -eq 'pdf_missing' }).Count
$missPage = ($entries | Where-Object { $_.status -eq 'problems_page_missing' }).Count
Write-Host ("Done. Total: {0} | PDFs: {1} | PDF missing: {2} | Page missing: {3}" -f $entries.Count, $ok, $missPdf, $missPage) -ForegroundColor Green
Write-Host ("PDFs dir: {0}" -f $dirs.pdfs)
