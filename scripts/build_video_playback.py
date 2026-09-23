#!/usr/bin/env python3
"""Build browser-independent image playback assets (requires ffmpeg and Pillow)."""
from pathlib import Path
import json
import subprocess
import tempfile

from PIL import Image


def main():
    assets = Path(__file__).resolve().parents[1] / 'site' / 'assets'
    for name in ('overview', 'exploration'):
        source = assets / (name + '.mp4')
        metadata = json.loads(subprocess.check_output([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_streams',
            '-of', 'json', str(source),
        ]))['streams'][0]
        width = 960
        height = round(int(metadata['height']) * width / int(metadata['width']) / 2) * 2
        duration = float(metadata['duration'])
        output = assets / 'playback' / name
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as temporary:
            subprocess.run([
                'ffmpeg', '-y', '-v', 'error', '-i', str(source), '-an',
                '-vf', f'fps=12,scale={width}:{height},tile=4x4', '-q:v', '6',
                '-map_metadata', '-1', '-threads', '3',
                str(Path(temporary) / '%04d.jpg'),
            ], check=True)
            sheets = []
            for path in sorted(Path(temporary).glob('*.jpg')):
                target = output / path.with_suffix('.webp').name
                with Image.open(path) as image:
                    image.save(target, format='WEBP', quality=70, method=4)
                sheets.append(target.name)
        manifest = dict(width=width, height=height, fps=12, columns=4, rows=4,
                        frames=round(duration * 12), duration=duration, sheets=sheets)
        (output / 'manifest.json').write_text(json.dumps(manifest, separators=(',', ':')) + '\n')
        print(f'{name}: {len(sheets)} sheets, {duration:.3f} seconds')


if __name__ == '__main__':
    main()
