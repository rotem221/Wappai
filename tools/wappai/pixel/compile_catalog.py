"""Compile the shared, declarative art catalog; append rigs without editing renderers."""
from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parents[3]
cat=json.loads((ROOT/'assets/pips/pixel/catalog.json').read_text())
assert cat['version']==1 and cat['size']==96 and len(cat['poses'])==24
chars=cat['characters'];assert 1<=len(chars)<=8
assert [c['id'] for c in chars]==list(range(len(chars))), 'Append stable rig IDs; never reorder them'
for c in chars:
    assert re.fullmatch('[A-Za-z][A-Za-z0-9_-]{0,29}',c['name'])
    for field in ['source','expressionsSource']:
        path=(ROOT/'assets/pips/pixel'/c[field]).resolve()
        assert path.is_relative_to((ROOT/'assets/pips/pixel/source').resolve()) and path.is_file()
    assert len(c['dizzyEyes'])==2 and all(len(e)==4 and 0<e[0]<96 and 0<e[1]<96 and 2<=e[2]<=12 and 2<=e[3]<=12 for e in c['dizzyEyes'])
    assert 0<=c['expressionRow']<c['expressionRows']<=8
h='#pragma once\nstruct PixelKey {unsigned char pose; unsigned short ms;};\nstruct PixelMotion {const char* name;const PixelKey* frames;int count;};\n'
for name,keys in cat['motions'].items():
    assert re.fullmatch('[a-z][a-z_]{0,22}',name) and 1<=len(keys)<=32
    assert all(type(f['pose']) is int and 0<=f['pose']<24 and type(f['ms']) is int and 80<=f['ms']<=10000 for f in keys)
    h+=f'static const PixelKey pm_{name}[]={{'+','.join('{'+str(f['pose'])+','+str(f['ms'])+'}' for f in keys)+'};\n'
h+='static const PixelMotion PIXEL_MOTIONS[]={'+','.join('{"'+k+'",pm_'+k+',sizeof(pm_'+k+')/sizeof(PixelKey)}' for k in cat['motions'])+'};\n'
(ROOT/'firmware/src/face/pixel_motions.gen.h').write_text(h)
(ROOT/'firmware/src/face/pixel_catalog.gen.h').write_text('#pragma once\nstatic constexpr int PIXEL_RIG_COUNT='+str(len(chars))+';\nstatic const char *const PIXEL_RIG_NAMES[]={'+','.join(json.dumps(c['name']) for c in chars)+'};\nstatic const float PIXEL_RIG_HUES[]={'+','.join(str(c['hue'])+'.f' for c in chars)+'};\n')
for dest in ['ios/Piko/Piko/PipMotions.json','server/sim/pixel-motions.json']:(ROOT/dest).write_text(json.dumps(cat,indent=2)+'\n')
print(f'Catalog: {len(chars)} rigs, 24 poses each, {len(cat["motions"])} motion mappings')

with (ROOT/'firmware/src/face/pixel_catalog.gen.h').open('a') as f:
    f.write('static const float PIXEL_DIZZY_EYES[][2][4]={'+','.join('{'+','.join('{'+','.join(str(float(v))+'f' for v in e)+'}' for e in c['dizzyEyes'])+'}' for c in chars)+'};\n')
