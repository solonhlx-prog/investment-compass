import subprocess
import os

html_path = r"D:\BaiduSyncdisk\赛博英雄传\投研罗盘\outputs\project_one_pager_v2.html"
pdf_path = r"D:\BaiduSyncdisk\赛博英雄传\投研罗盘\outputs\project_one_pager_v2.pdf"

chrome_paths = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]

chrome = None
for p in chrome_paths:
    if os.path.exists(p):
        chrome = p
        break

if chrome:
    cmd = [
        chrome,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        f"--print-to-pdf={pdf_path}",
        "--virtual-time-budget=10000",
        "--paper-width=210",
        "--paper-height=297",
        "--margin-top=0",
        "--margin-bottom=0",
        "--margin-left=0",
        "--margin-right=0",
        html_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    print("Chrome exit code:", result.returncode)
    if result.stderr:
        print("Chrome stderr:", result.stderr[:500])
else:
    print("Chrome/Edge not found, trying weasyprint...")
    from weasyprint import HTML
    HTML(html_path).write_pdf(pdf_path)
    print("PDF generated via weasyprint")

print(f"PDF exists: {os.path.exists(pdf_path)}")
if os.path.exists(pdf_path):
    print(f"PDF size: {os.path.getsize(pdf_path)} bytes")
