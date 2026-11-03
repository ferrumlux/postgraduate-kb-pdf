#!/usr/bin/env python3
"""Aggregate complete pages; pass book directory and expected PDF page count."""
import re, sys, unicodedata
from pathlib import Path
book=Path(sys.argv[1]); count=int(sys.argv[2]); pages=book/'Luna逐页'
files=sorted(pages.glob('page-*.md'))
expected=list(range(1,count+1)); present=[int(p.stem.split('-')[1]) for p in files]
if present!=expected: raise SystemExit(f'Incomplete: {len(present)}/{count}; missing: {sorted(set(expected)-set(present))}')
texts=[]
for p in files:
    s=p.read_text(encoding='utf-8')
    bad=sorted({f'U+{ord(c):04X}' for c in s if unicodedata.category(c)=='Co' or c=='\ufffd'})
    if bad: raise SystemExit(f'{p}: unexpected private/replacement chars: {bad}')
    links=re.findall(r'\]\((\.\./(?:页面|images)/[^)]+)\)',s)
    if not links or any(not (p.parent / link).exists() for link in links):
        raise SystemExit(f'{p}: image links missing or invalid')
    # 全文位于逐页目录的上一级；所有以 ../ 开头的 Markdown 链接都需
    # 移除一层父目录，包含指向其他资料的跨目录原图链接。
    texts.append(re.sub(r'(?<=\]\()\.\./', '', s).strip())
target=book/'Luna全文.md'; tmp=target.with_suffix('.md.tmp')
tmp.write_text('\n\n---\n\n'.join(texts)+'\n',encoding='utf-8'); tmp.replace(target)
print(f'{target}: {count} pages; page links and private/replacement characters checked')
