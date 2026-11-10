"""Fetch only the explicitly curated, public source list. Never crawl a website."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache/worksheet_sources'
SOURCES = json.loads(Path(__file__).with_name('sources.json').read_text())

def download():
    CACHE.mkdir(parents=True, exist_ok=True)
    receipts = {}
    for key, source in SOURCES.items():
        target = CACHE / source['file']
        if not target.exists():
            temporary = target.with_suffix(target.suffix + '.partial')
            request = urllib.request.Request(source['url'], headers={'User-Agent':'LessonBuddyAcademicBenchmark/1'})
            with urllib.request.urlopen(request, timeout=60) as response, temporary.open('wb') as out:
                total = 0
                while block := response.read(1024 * 1024):
                    total += len(block)
                    if total > 40_000_000:
                        raise ValueError('A curated source exceeded the download size limit.')
                    out.write(block)
            header = temporary.open('rb').read(8)
            if target.suffix == '.pdf' and not header.startswith(b'%PDF-'):
                raise ValueError(f'{key}: source redirected to non-PDF content; no valid source was replaced.')
            if target.suffix == '.zip' and not header.startswith(b'PK'):
                raise ValueError(f'{key}: source did not return an archive.')
            temporary.replace(target)
        if target.suffix == '.zip':
            folder = target.with_suffix('')
            folder.mkdir(exist_ok=True)
            with zipfile.ZipFile(target) as archive:
                items = [item for item in archive.infolist() if item.filename.endswith('.pdf')]
                if len(items) > 200 or sum(item.file_size for item in items) > 150_000_000:
                    raise ValueError('Unexpected source archive expansion.')
                names = set()
                for item in items:
                    name = Path(item.filename).name
                    if name in names or item.file_size > 20_000_000:
                        raise ValueError('Unexpected PDF member in source archive.')
                    names.add(name)
                    data = archive.read(item)
                    if not data.startswith(b'%PDF-'):
                        raise ValueError('The source archive member is not a PDF.')
                    (folder / name).write_bytes(data)
        elif not target.read_bytes().startswith(b'%PDF-'):
            raise ValueError(f'Curated source {key} did not return a PDF.')
        receipts[key] = {**source, 'sha256':hashlib.file_digest(target.open('rb'),'sha256').hexdigest(), 'bytes':target.stat().st_size}
        print(key, 'ready', flush=True)
    (CACHE / 'source_receipts.json').write_text(json.dumps(receipts, indent=2) + '\n')
    return receipts

if __name__ == '__main__':
    download()
