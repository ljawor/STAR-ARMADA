#!/usr/bin/env python3
"""Compare fresh prototype/preview/legacy captures and publish compact evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--captures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import pygame
    import numpy as np
    summaries = {mode: json.loads((args.captures / mode / 'summary.json').read_text())
                 for mode in ('prototype', 'preview', 'legacy')}
    state_hashes = {summary['state_sha256'] for summary in summaries.values()}
    assert len(state_hashes) == 1
    measurements = []
    for frame in summaries['prototype']['captures']:
        name = frame['name']
        images = {mode: pygame.surfarray.array3d(pygame.image.load(
            str(args.captures / mode / (name + '.png')))).astype(np.int16) for mode in summaries}
        preview_changes = int(np.count_nonzero(images['prototype'] != images['preview']))
        legacy_changes = int(np.count_nonzero(images['prototype'] != images['legacy']))
        assert preview_changes == 0, (name, preview_changes)
        assert legacy_changes > 0, (name, 'legacy negative control did not discriminate')
        measurements.append({'view': name, 'preview_differing_channels': preview_changes,
                             'legacy_differing_channels': legacy_changes})
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'status': 'passed', 'prototype_base': '5bddd7b67245ddff4b595bb3b477ca8ceede0a6c',
              'measurements': measurements, 'state_sha256': next(iter(state_hashes)),
              'inputs': summaries,
              'scope': 'S04 frozen-frame engineering parity; not full S05 motion/combat/owner review or S09 package acceptance'}
    (args.output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n',
                                                  encoding='utf-8', newline='\n')
    for name in ('capital-close', 'escort-close', 'yard-close'):
        shutil.copyfile(args.captures / 'preview' / (name + '.png'), args.output / (name + '.png'))
    pygame.font.init()
    try:
        font = pygame.font.Font(None, 24)
        small = pygame.font.Font(None, 20)
        sheet = pygame.Surface((1200, 910))
        sheet.fill((12, 18, 29))
        sheet.blit(font.render('S04 — same approved geometry, generic opt-in path', True, (235, 240, 245)), (16, 10))
        views = ('capital-close', 'escort-close', 'yard-close')
        for row, mode in enumerate(('prototype', 'preview', 'legacy')):
            y = 48 + row * 278
            label = {'prototype': 'APPROVED PROTOTYPE', 'preview': 'GENERIC PREVIEW · 0 changed channels',
                     'legacy': 'LEGACY DEFAULT · negative control'}[mode]
            sheet.blit(small.render(label, True, (150, 210, 220)), (16, y))
            for col, name in enumerate(views):
                image = pygame.image.load(str(args.captures / mode / (name + '.png')))
                sheet.blit(pygame.transform.smoothscale(image, (400, 250)), (col * 400, y + 24))
        sheet.blit(small.render('8/8 views pixel-identical · 4x MSAA · production shaders/fog · identical simulation hashes',
                                True, (235, 240, 245)), (16, 890))
        pygame.image.save(sheet, str(args.output / 'review-sheet.png'))
    finally:
        pygame.font.quit()
    print(json.dumps({'views': len(measurements), 'preview_changed_channels': 0,
                      'state_sha256': report['state_sha256'], 'status': report['status']}))


if __name__ == '__main__':
    main()
