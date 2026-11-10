"""Package inspectable data/results, excluding models, environments and caches."""
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def package():
    output=ROOT/'output/worksheet_benchmark'
    archive=output/'worksheet_benchmark_v1.zip'
    files=[]
    for folder in [ROOT/'benchmarks/worksheet_v1',output,ROOT/'worksheet_benchmark']:
        files.extend(path for path in folder.rglob('*') if path.is_file()
                     and '__pycache__' not in path.parts and path.suffix not in ['.zip','.pyc'])
    files.extend([ROOT/'requirements-benchmark.txt',ROOT/'tests/test_worksheet_benchmark.py'])
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as target:
        for path in sorted(set(files)):target.write(path,path.relative_to(ROOT))
        target.writestr('START_HERE.txt','Open output/worksheet_benchmark/index.html in your browser. It works offline.\n\nThis package contains evaluation data, source notices, raw results and reference code. To rerun model inference, use the existing Lesson Buddy project with its local MLX environment and cached model weights; weights, environments and the main application are not bundled. It is not a standalone app.\n\nThese are 100 web-source task images, plus 30 synthetic variants of 10 development items; zero real phone photos. Mixed-license material is for noncommercial academic evaluation. Keep attribution and per-case provenance with copies.\n')
    return {'archive':str(archive),'files':len(set(files))+1,'bytes':archive.stat().st_size}

if __name__=='__main__':print(json.dumps(package()))
