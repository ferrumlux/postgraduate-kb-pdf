#!/usr/bin/env python3
"""只读检查逐页稿；报告不是逐图内容验收证明。"""
import difflib
import hashlib
import json
import re
import subprocess
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

WORK = Path(__file__).resolve().parent
ROOT = WORK.parent.parent
PDF_ROOT = ROOT / '01_PDF原版'
TEXT_ROOT = ROOT.parent / 'postgraduate-kb-md' / '02_Markdown提取版'


def broken_local_links(text, base):
    broken = []
    for target in re.findall(r'\]\(([^)]+)\)', text):
        target = target.strip().split(' "', 1)[0]
        if target.startswith('<') and target.endswith('>'):
            target = target[1:-1]
        parsed = urlsplit(target)
        if parsed.scheme or not parsed.path or parsed.path.startswith('/'):
            continue
        if not (base / unquote(parsed.path)).exists():
            broken.append(target)
    return broken


def audit_document(source):
    info = subprocess.run(
        ['pdfinfo', str(source)], check=True, capture_output=True, text=True
    ).stdout
    count = int(re.search(r'^Pages:\s+(\d+)', info, re.M).group(1))
    book = TEXT_ROOT / source.relative_to(PDF_ROOT).with_suffix('')
    files = sorted((book / 'Luna逐页').glob('page-*.md'))
    pages, issues, duplicates, texts, review_candidates = {}, [], [], [], []
    fingerprint = hashlib.sha256()
    previous = None
    for path in files:
        match = re.fullmatch(r'page-(\d+)\.md', path.name)
        if not match:
            issues.append({'file': path.name, 'issue': 'invalid_filename'})
            continue
        number = int(match.group(1))
        if number in pages:
            issues.append({'page': number, 'issue': 'duplicate_page_number'})
        data = path.read_bytes()
        fingerprint.update(path.name.encode() + b'\0' + data + b'\0')
        text = data.decode('utf-8')
        pages[number] = path.name
        if not text.strip():
            issues.append({'page': number, 'issue': 'empty_file'})
        bad = sorted({f'U+{ord(c):04X}' for c in text
                      if unicodedata.category(c) == 'Co' or c == '\ufffd'})
        if bad:
            issues.append({'page': number, 'issue': 'private_or_replacement', 'characters': bad})
        first_heading = re.search(r'^#\s+([^\n]+)', text, re.M)
        heading = first_heading.group(1) if first_heading else ''
        header = re.search(r'(?:物理页\s*|PDF\s*第\s*|page-)(\d+)', heading)
        if not header or int(header.group(1)) != number:
            issues.append({'page': number, 'issue': 'physical_page_header_mismatch'})
        links = re.findall(r'\]\((\.\./(?:页面|images)/[^)]+)\)', text)
        if not links:
            issues.append({'page': number, 'issue': 'missing_source_link'})
        for link in links:
            if not (path.parent / link).exists():
                issues.append({'page': number, 'issue': 'broken_source_link', 'link': link})
        for link in broken_local_links(text, path.parent):
            if link not in links:
                issues.append({'page': number, 'issue': 'broken_local_link', 'link': link})
        own_links = [link for link in links
                     if re.search(r'page-0*' + str(number) + r'\.(?:png|jpg|jpeg)$', link)]
        if links and not own_links:
            issues.append({'page': number, 'issue': 'source_link_page_mismatch'})
        for line in text.splitlines():
            if re.search(r'待补|待转|待校|无法辨|详见原图|见原图|选项.{0,8}续下页|代码.{0,8}续下页', line):
                review_candidates.append({'page': number, 'reason': 'possible_placeholder_or_page_boundary',
                                          'excerpt': line[:240]})
        # 仅用于找候选；数学公式和固定页眉可能自然重复，必须看图判断。
        body = re.sub(r'\[.*?\]\(.*?\)', '', text)
        body = re.sub(r'\s+', '', body)
        if previous and number == previous[0] + 1:
            a = previous[1]
            longest = difflib.SequenceMatcher(None, a, body, autojunk=False).find_longest_match()
            if longest.size >= 160:
                duplicates.append({'pages': [previous[0], number],
                                   'matching_characters': longest.size,
                                   'excerpt': body[longest.b:longest.b + min(180, longest.size)]})
        previous = (number, body)
        texts.append(re.sub(r'(?<=\]\()\.\./', '', text).strip())
    expected = set(range(1, count + 1))
    image_numbers = set()
    for directory in ('images', '页面'):
        for image_path in (book / directory).glob('page-*.*'):
            image_match = re.fullmatch(r'page-(\d+)\.(?:png|jpg|jpeg)', image_path.name)
            if image_match:
                image_numbers.add(int(image_match.group(1)))
    compiled = book / 'Luna全文.md'
    result = {
        'source': str(source.relative_to(PDF_ROOT)), 'total_pages': count,
        'page_files': len(files), 'missing': sorted(expected - pages.keys()),
        'unexpected_pages': sorted(pages.keys() - expected),
        'missing_source_images': sorted(expected - image_numbers),
        'mechanical_issues': issues, 'adjacent_duplicate_candidates': duplicates,
        'content_review_candidates': review_candidates,
        'compiled': compiled.exists(), 'content_verified': False,
        'page_files_sha256': fingerprint.hexdigest(),
    }
    if compiled.exists():
        expected_text = '\n\n---\n\n'.join(texts) + '\n'
        compiled_text = compiled.read_text()
        result['compiled_broken_local_links'] = broken_local_links(compiled_text, book)
        result['compiled_matches_current_pages'] = compiled_text == expected_text
        first_heading = texts[0].splitlines()[0] if texts else ''
        body_start = re.search(r'^' + re.escape(first_heading) + r'$', compiled_text, re.M) if first_heading else None
        result['compiled_page_body_matches_current_pages'] = bool(
            body_start and compiled_text[body_start.start():] == expected_text
        )
        result['compiled_prefix_line_count'] = len(compiled_text[:body_start.start()].splitlines()) if body_start else None
    return result


def main():
    documents = [audit_document(p) for p in sorted((PDF_ROOT / '王道').rglob('*.pdf'))]
    # 哈希只用于发现批次报告之后的文件变化，不证明报告的内容准确。
    ledger = WORK / '本会话批次记录.jsonl'
    if ledger.exists():
        latest = {}
        for line in ledger.read_text().splitlines():
            event = json.loads(line)
            for page in event['pages']:
                latest[(event['source'], page['physical_page'])] = (event, page)
        for document in documents:
            current, changed = [], []
            for (source, number), (event, page) in latest.items():
                if source != document['source']:
                    continue
                legacy = Path(page['file'])
                path = TEXT_ROOT / legacy.relative_to('文本转换') if legacy.parts[0] == '文本转换' else ROOT / legacy
                if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == page['sha256']:
                    current.append({'page': number, 'stage': event['stage'], 'evidence': event['evidence']})
                else:
                    changed.append(number)
            document['batch_records_matching_current_files'] = current
            document['pages_changed_since_latest_batch_record'] = sorted(changed)
    report = {
        'generated_at': datetime.now().astimezone().isoformat(),
        'notice': '仅检查当前文件状态，所有内容仍须逐原图核对；重复候选不可自动删除。并行写入期间为非事务快照。',
        'documents': documents,
    }
    target = WORK / '当前文件审计.json'
    temporary = target.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(target)
    for d in documents:
        print(f"{d['source']}: {d['page_files']}/{d['total_pages']}; "
              f"机械问题 {len(d['mechanical_issues'])}; 相邻重复候选 {len(d['adjacent_duplicate_candidates'])}")
    print('文件合计:', sum(d['page_files'] for d in documents), '/', sum(d['total_pages'] for d in documents))


if __name__ == '__main__':
    main()
