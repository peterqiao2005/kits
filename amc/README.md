目的
- 抓取 AoPS Wiki 上 AMC 10（2000–2024，忽略 2025）的试题页面（…_Problems）及其对应的 PDF 下载链接；
- 生成映射表（CSV/JSON），并把所有 PDF 下载到本地。

输出
- 映射表：`amc/amc10_pdfs.csv`、`amc/amc10_pdfs.json`
- PDF 文件：保存到 `amc/pdfs/` 下，文件名如：`2014_AMC_10B_Problems.pdf`

基于固定下载入口（c3414）
- 新脚本：`amc/download_amc10_c3414.ps1`
- 作用：按年份访问 `https://artofproblemsolving.com/community/contest/download/c3414_amc_10/{year}`，
  解析重定向得到最终 PDF 地址并下载到 `amc/pdfs_c3414/`，同时生成 `amc/amc10_pdfs_c3414.csv` 映射表。
- 使用：
  - 仅解析不下载（演练）：
    `powershell -NoProfile -ExecutionPolicy Bypass -File amc/download_amc10_c3414.ps1 -FromYear 2000 -ToYear 2000 -DryRun`
  - 全量下载（2000–2024）：
    `powershell -NoProfile -ExecutionPolicy Bypass -File amc/download_amc10_c3414.ps1`
  - 指定范围下载：
    `powershell -NoProfile -ExecutionPolicy Bypass -File amc/download_amc10_c3414.ps1 -FromYear 2010 -ToYear 2015`

快速使用（推荐：PowerShell，无需 Python）
1) 打开 PowerShell（允许脚本执行）
2) 在仓库根目录执行：
   `powershell -NoProfile -ExecutionPolicy Bypass -File amc/scrape_amc10_pdfs.ps1`

备用方案（Python）
1) 安装依赖：`pip install requests beautifulsoup4`
2) 运行脚本：`python amc/scrape_amc10_pdfs.py`

实现要点
- 先访问索引页：`https://artofproblemsolving.com/wiki/index.php/AMC_10_Problems_and_Solutions`
- 提取形如 `20xx_AMC_10`, `20xx_AMC_10A`, `20xx_AMC_10B` 的链接（2000–2024）；
- 拼接 `…_Problems` 页面；
- 在每个 Problems 页面中查找 PDF 链接（直链 .pdf 或文本为 “PDF” 的链接）；
- 生成映射并下载。

注意
- 如果某年不存在 A/B 则索引页不会出现，对应就不会被收录；
- 个别页面可能没有 PDF 链接，会标记为 `pdf_missing`；
- 网络或 TLS 受限时，PowerShell 脚本已强制 TLS1.2，并设置了浏览器 UA。
