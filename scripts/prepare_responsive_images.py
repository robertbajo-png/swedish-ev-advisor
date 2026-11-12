"""Create smaller format/size derivatives of exact, hash-verified licensed model photos."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    assets = json.loads((ROOT / 'src/image-rights.json').read_text(encoding='utf-8'))['assets']
    manifest = ROOT / 'src/image-variants.json'
    cached = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {}
    output = {}
    total_original = total_small = 0
    for asset in assets:
        if asset.get('status') != 'documented':
            raise ValueError('Undocumented original image')
        source = ROOT / 'public' / asset['asset_url'].lstrip('/')
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != asset['content_sha256']:
            raise ValueError('Licensed original image changed')
        previous = cached.get(asset['asset_url'])
        if previous and previous.get('source_sha256') == asset['content_sha256']:
            expected_widths = sorted({min(previous['width'], size) for size in (480, 800, 1280)})
            valid = [row['width'] for row in previous['variants']] == expected_widths
            for row in previous['variants']:
                target = ROOT / 'public' / row['url'].lstrip('/')
                valid = valid and row['url'].startswith('/media/responsive/') and target.is_file() and not target.is_symlink()
                if valid:
                    content = target.read_bytes()
                    valid = content[8:12] == b'WEBP' and hashlib.sha256(content).hexdigest() == row['sha256']
            if valid:
                output[asset['asset_url']] = previous
                total_original += len(raw)
                total_small += (ROOT / 'public' / previous['variants'][0]['url'].lstrip('/')).stat().st_size
                continue
        with Image.open(source) as original:
            image = ImageOps.exif_transpose(original).convert('RGB')
            width, height = image.size
            variants = []
            for target_width in sorted({min(width, size) for size in (480, 800, 1280)}):
                path = '/media/responsive/' + source.stem + '-' + str(target_width) + '.webp'
                target = ROOT / 'public' / path.lstrip('/')
                if args.write:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    resized = image.resize((target_width, round(height * target_width / width)), Image.Resampling.LANCZOS)
                    resized.save(target, 'WEBP', quality=80, method=6)
                variants.append({'url': path, 'width': target_width, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
            output[asset['asset_url']] = {'width': width, 'height': height, 'source_sha256': asset['content_sha256'], 'variants': variants}
            total_original += len(raw)
            total_small += (ROOT / 'public' / variants[0]['url'].lstrip('/')).stat().st_size
    if args.write:
        (ROOT / 'src/image-variants.json').write_text(json.dumps(output, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'exact_models': len(output), 'original_bytes': total_original, 'mobile_derivative_bytes': total_small, 'originals_unchanged': True}))


if __name__ == '__main__':
    main()
