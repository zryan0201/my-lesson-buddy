"""Render the exact same authored text with local neural and optional Mac voices."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lesson_video.neural_audio import NeuralNarrator
from lesson_video.audio import synthesize

TEXT = ("Hi, math explorers! Let's help our buddy collect the popsicles. "
        "We have five already. Here come two more! Six... seven. "
        "Five plus two makes seven! Your turn. Can you show me how you know?")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-classic', action='store_true')
    args = parser.parse_args()
    destination = ROOT / 'output/natural_voice'
    destination.mkdir(parents=True, exist_ok=True)
    narrator = NeuralNarrator(ROOT / '.cache/kokoro', ROOT / '.cache/neural_comparison')
    metadata = {'text':TEXT, 'paid_api_requests':0, 'clips':{}}
    metadata['clips']['natural'] = narrator.synthesize(TEXT, destination / 'natural_narrator.wav', speed=.86)
    if args.with_classic:
        metadata['clips']['classic'] = synthesize(TEXT, destination / 'classic_narrator.wav',
                                                 'Samantha', 145, cache_dir=ROOT / '.cache/classic_comparison')
    (destination / 'comparison.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps({name:{key:value for key,value in data.items() if key in ['path','duration','peak_dbfs','clipped_samples']}
                      for name,data in metadata['clips'].items()}, indent=2))

if __name__ == '__main__':
    main()
