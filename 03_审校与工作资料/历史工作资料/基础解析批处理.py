#!/usr/bin/env python3
"""本地 MinerU 基础模型的可恢复对照稿；不是最终质量版本。"""
import json, os, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
BASE=ROOT/'文本转换'
files=[ROOT/'王道'/f'{name}.pdf' for name in ['DS','OS','计组','计网']]+[ROOT/'王道'/'答案页整理'/f'{name}答案页.pdf' for name in ['DS','OS','计组','计网']]
env=dict(os.environ, MINERU_MODEL_SMALL_BACKEND='onnx', MINERU_MODEL_SOURCE='local')
for pdf in files:
    folder=BASE/pdf.relative_to(ROOT).with_suffix('')
    out=folder/'基础解析.zip'
    if out.exists():
        p=subprocess.run(['unzip','-tqq',str(out)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if p.returncode==0:
            print(f'SKIP {pdf}',flush=True); continue
    temp=folder/'基础解析.进行中.zip'
    log=folder/'基础解析.log'
    print(f'START {pdf}',flush=True)
    with log.open('w',encoding='utf-8') as stream:
        result=subprocess.run(['/tmp/mineru-venv/bin/mineru-kit','parse',str(pdf),'-o',str(temp),'--tier','basic','--format','zip','--ocr-mode','ocr'],env=env,stdout=stream,stderr=subprocess.STDOUT)
    if result.returncode or not temp.exists() or subprocess.run(['unzip','-tqq',str(temp)]).returncode:
        print(f'FAILED {pdf}, code={result.returncode}',flush=True); continue
    os.replace(temp,out)
    print(f'DONE {pdf}',flush=True)
