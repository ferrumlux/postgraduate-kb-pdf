#!/usr/bin/env python3
"""Extract text and page visual references for born-digital exercise PDFs."""
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import hashlib, json, os, subprocess
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / '文本转换'

def one(path):
    pdf = Path(path)
    rel = pdf.relative_to(ROOT)
    directory = OUT / rel.parent / pdf.stem
    imgdir = directory / '页面'
    imgdir.mkdir(parents=True, exist_ok=True)
    info = subprocess.check_output(['pdfinfo',str(pdf)], text=True)
    pages = int(next(x.split(':',1)[1].strip() for x in info.splitlines() if x.startswith('Pages:')))
    # -layout better preserves code indentation, option layout and table alignment.
    data = subprocess.check_output(['pdftotext','-layout','-enc','UTF-8',str(pdf),'-']).decode('utf-8')
    texts = data.split('\f')
    if len(texts) == pages + 1 and not texts[-1].strip(): texts.pop()
    if len(texts) != pages: raise RuntimeError(f'{pdf}: expected {pages} pages, got {len(texts)}')
    subprocess.run(['pdftoppm','-png','-r','150',str(pdf),str(imgdir / 'page')], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    images = sorted(imgdir.glob('page-*.png'))
    if len(images) != pages: raise RuntimeError(f'{pdf}: expected {pages} rendered pages, got {len(images)}')
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    result = [f'# {pdf.stem}\n',f'来源：`{rel}`  \nPDF 物理页数：{pages}  \n源文件 SHA-256：`{digest}`\n',
              '下方文字是未经校对的 PDF 文字层提取结果；页图保留原始页面的视觉信息以供核对。公式、表格、图片及阅读顺序不能保证已被文字准确表达。\n']
    stats=[]
    for idx, (txt, image) in enumerate(zip(texts, images), 1):
        # Fence is longer than any literal backtick sequence in the extracted page.
        import re
        longest = max([len(x) for x in re.findall(r'`+',txt)] or [0])
        fence = '`' * max(3,longest+1)
        result.extend([f'\n## PDF 第 {idx} 页\n',f'![PDF 第 {idx} 页原貌](页面/{image.name})\n',f'{fence}text\n{txt.rstrip()}\n{fence}\n'])
        stats.append({'pdf_page':idx,'text_characters':len(txt.strip()),'image':f'页面/{image.name}'})
    tmp = directory / '正文.md.tmp'
    tmp.write_text('\n'.join(result),encoding='utf-8')
    os.replace(tmp,directory / '正文.md')
    (directory / '元数据.json').write_text(json.dumps({'source':str(rel),'sha256':digest,'page_count':pages,'method':'pdftotext -layout; full page PNG at 150 dpi','pages':stats},ensure_ascii=False,indent=2),encoding='utf-8')
    return str(rel), pages, sum(x['text_characters']==0 for x in stats)

if __name__=='__main__':
    files = sorted(p for p in (ROOT/'王道').glob('*.pdf') if p.stem.endswith(('选择','综合')))
    with ProcessPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(one,str(p)):p for p in files}
        for f in as_completed(futures):
            print(f.result(),flush=True)
