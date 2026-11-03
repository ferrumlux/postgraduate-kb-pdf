#!/usr/bin/env python3
"""Extract per-page visual references from the eight image-only PDFs.
Requires poppler (pdfimages, pdfinfo, pdftoppm). Original full-page images are
losslessly decoded to PNG; pages with unexpected objects/masks are rendered.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import argparse, hashlib, json, os, re, shutil, subprocess, tempfile

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / '文本转换'
PDFS = [ROOT / '王道' / (x + '.pdf') for x in ('DS', 'OS', '计组', '计网')]
PDFS += sorted((ROOT / '王道' / '答案页整理').glob('*.pdf'))
# pdfimages-generated 1443x2011 opaque gray mask, independently inspected.
OPAQUE_MASK_SHA256 = 'bb0df934a9e1b61999e6c1f14899d1f8c6f94089222d0d4a152d6e7b977d604b'

def cmd(*args):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout

def process(pdf):
    rel = pdf.relative_to(ROOT)
    dest = OUT / rel.parent / rel.stem / 'images'
    dest.mkdir(parents=True, exist_ok=True)
    info = cmd('pdfinfo', str(pdf))
    count = int(re.search(r'^Pages:\s*(\d+)', info, re.M).group(1))
    rows = cmd('pdfimages', '-list', str(pdf)).splitlines()[2:]
    entries = {}
    for row in rows:
        fields = row.split()
        if len(fields) < 12: continue
        page, num = int(fields[0]), int(fields[1])
        entries.setdefault(page, []).append({'num': num, 'type': fields[2], 'width': int(fields[3]), 'height': int(fields[4])})
    with tempfile.TemporaryDirectory(prefix='.page-extract-', dir=dest.parent) as td:
        temp = Path(td)
        subprocess.run(['pdfimages', '-png', str(pdf), str(temp / 'raw')], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        pages = []
        for page in range(1, count + 1):
            output = dest / f'page-{page:04}.png'
            items = entries.get(page, [])
            method = 'rendered-192dpi'
            if len(items) == 2 and items[0]['type'] == 'image' and items[1]['type'] == 'smask' and (items[0]['width'], items[0]['height']) == (1443, 2011):
                image = temp / f'raw-{items[0]["num"]:03}.png'
                mask = temp / f'raw-{items[1]["num"]:03}.png'
                if image.exists() and mask.exists() and hashlib.sha256(mask.read_bytes()).hexdigest() == OPAQUE_MASK_SHA256:
                    os.replace(image, output)
                    method = 'original-image-lossless-png'
            if method == 'rendered-192dpi':
                prefix = temp / 'rendered'
                subprocess.run(['pdftoppm', '-f', str(page), '-l', str(page), '-r', '192', '-png', '-singlefile', str(pdf), str(prefix)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                os.replace(prefix.with_suffix('.png'), output)
            pages.append({'pdf_page': page, 'file': output.name, 'method': method})
        (dest / 'manifest.json').write_text(json.dumps({'source': str(rel), 'page_count': count, 'pages': pages}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{rel}: {count} pages; {sum(p["method"] == "rendered-192dpi" for p in pages)} rendered', flush=True)
    return len(pages)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=3)
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(process, pdf) for pdf in PDFS]
        for future in as_completed(futures): future.result()

if __name__ == '__main__': main()
