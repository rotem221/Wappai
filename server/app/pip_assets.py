"""Bounded, data-only sprite packs shared by iOS and ESP32. No executable assets."""
import io,json,struct,zlib,hashlib
from pathlib import Path
from PIL import Image,ImageOps

SIZE=96;FRAMES=24;MAX_PACK=160_000
CATALOG=json.loads((Path(__file__).resolve().parent.parent/'sim/pixel-motions.json').read_text())
POSES=CATALOG['poses'];MOTIONS=CATALOG['motions']
STYLE='Original premium pixel-art pocket companion, crisp deliberate square pixels, expressive eyes, readable silhouette, charming full body with short limbs. No typography, logos, frames, props outside the character, or copied characters. Flat exact solid magenta #FF00FF background for clean removal; do not use magenta anywhere in the character. No ground shadow.'
def preview_prompt(brief):
    return STYLE+' Create one square 1024x1024 image, exactly one character in a relaxed front-facing pose. Entire body, ears, feet and accessories visible, centered with 15% clear margin on all sides. If an image is attached, preserve its recognizable character identity and adapt it to this pixel style. Treat this JSON as the visual brief only: '+json.dumps({'description':brief},ensure_ascii=False)
def atlas_prompt():
    poses=['relaxed friendly idle','eyes closed blink','attentive listening, lean forward','listening, raised ears or hand to ear',
      'thinking, hand to chin','thinking, glance upward','speaking, small open mouth','speaking, wider mouth and small hand gesture',
      'happy, eyes smiling','joyful small hop, lifted arms','sleeping, closed eyes','sleeping, gentle exhale',
      'surprised, round eyes and open mouth','sad, lowered eyes','wave hello, arm raised left','wave hello, arm raised right',
      'angry, brows down','wink one eye','love, heart-shaped eyes','crying, visible tiny tears','confused, tilted head',
      'proud, confident pose','scared, wide eyes, hands close','yawning, open mouth, sleepy eyes']
    return STYLE+' Use the attached APPROVED character as the exact identity reference. Create ONE portrait sprite sheet, 1024 pixels wide by 1536 pixels high, exactly FOUR columns and SIX rows of equally sized 256x256 cells. Exactly 24 complete characters, one per cell, NEVER add labels or grid lines. Keep identical anatomy, costume, palette and character size in every cell, feet on a common baseline, front-facing. Preserve 15% empty magenta margins in EVERY cell; no overlapping or clipped limbs. Animate face and limbs, not the camera. Row-major cells, left to right then top to bottom: '+ '; '.join(f'{i+1}: {pose}' for i,pose in enumerate(poses))+'. Every pose must be visibly distinct where specified. Return only the sprite sheet.'
def read_image(data,max_pixels=12_000_000):
    if not isinstance(data,bytes) or not 1<=len(data)<=12_000_000:raise ValueError('גודל התמונה אינו תקין')
    with Image.open(io.BytesIO(data)) as image:
        if image.width*image.height>max_pixels or min(image.size)<32:raise ValueError('ממדי התמונה אינם תקינים')
        image.load();return ImageOps.exif_transpose(image).convert('RGBA')
def png(image):
    out=io.BytesIO();image.save(out,format='PNG');return out.getvalue()
def cutout(image):
    image=image.copy();pixels=image.load()
    # Preserve genuine alpha. Otherwise remove the specified chroma key only;
    # never infer arbitrary photo backgrounds or erase non-magenta body colours.
    if image.getchannel('A').getextrema()[0]<128:return image
    for y in range(image.height):
        for x in range(image.width):
            r,g,b,a=pixels[x,y]
            # Model output can shade/antialias the matte to dark magenta.
            # Key its hue across brightness levels, preserving blue/violet
            # body colours (unequal red/blue) and genuine authored alpha.
            bright_key=r>210 and b>210 and g<65 and abs(r-b)<40
            dark_key=min(r,b)>70 and g<min(r,b)*.35 and abs(r-b)<max(r,b)*.20
            if bright_key or dark_key:pixels[x,y]=(0,0,0,0)
    return image
def preview(data):
    im=cutout(read_image(data));box=im.getchannel('A').getbbox()
    if not box or im.getchannel('A').getextrema()[0]>=128:raise ValueError('הרקע לא הופרד כראוי; נסה ליצור שוב')
    im=im.crop(box);im.thumbnail((420,420),Image.Resampling.NEAREST)
    out=Image.new('RGBA',(512,512));out.alpha_composite(im,((512-im.width)//2,470-im.height));return png(out)
def compile_pack(data,pip_id,asset_id,name,directory):
    image=read_image(data)
    if abs(image.width/image.height-2/3)>.035:raise ValueError('גיליון המצבים אינו בפריסה הנדרשת; אפשר לנסות שוב')
    cells=[];boxes=[]
    for row in range(6):
        for col in range(4):
            cell=cutout(image.crop((round(col*image.width/4),round(row*image.height/6),round((col+1)*image.width/4),round((row+1)*image.height/6))))
            a=cell.getchannel('A').point(lambda v:255 if v>=180 else 0);cell.putalpha(a);box=a.getbbox()
            if not box or a.getextrema()[0]>=180:raise ValueError('חסר ציור או רקע שקוף באחד המצבים')
            if box[0]<2 or box[1]<2 or box[2]>cell.width-2 or box[3]>cell.height-2:raise ValueError('אחת הדמויות נחתכה; יש לנסות מחדש')
            fraction=sum(v>0 for v in a.tobytes())/(cell.width*cell.height)
            if not .035<fraction<.75:raise ValueError('אחת התנוחות אינה תקינה')
            cells.append(cell);boxes.append(box)
    # Shared scale preserves pose proportions and registration across all 24 cells.
    scale=min(80/max(b[2]-b[0] for b in boxes),82/max(b[3]-b[1] for b in boxes))
    atlas=Image.new('RGBA',(SIZE*4,SIZE*6));bounds=[]
    for i,(cell,b) in enumerate(zip(cells,boxes)):
        cell=cell.crop(b);cell=cell.resize((max(1,round(cell.width*scale)),max(1,round(cell.height*scale))),Image.Resampling.NEAREST)
        frame=Image.new('RGBA',(SIZE,SIZE));frame.alpha_composite(cell,((SIZE-cell.width)//2,90-cell.height));bounds.extend(frame.getchannel('A').getbbox())
        atlas.alpha_composite(frame,((i%4)*SIZE,(i//4)*SIZE))
    # Validate that the model produced authored states, not 24 copies of one pose.
    hashes={hashlib.sha256(atlas.crop(((i%4)*SIZE,(i//4)*SIZE,(i%4+1)*SIZE,(i//4+1)*SIZE)).tobytes()).digest() for i in range(FRAMES)}
    if len(hashes)<16:raise ValueError('לא נוצר מגוון מספיק של הבעות; יש לנסות שוב')
    quant=atlas.convert('RGB').quantize(colors=127,method=Image.Quantize.MEDIANCUT)
    pal=quant.getpalette();pal += [0]*(768-len(pal));palette=[0]
    for i in range(127):
        r,g,b=pal[i*3:i*3+3];palette.append(((r>>3)<<11)|((g>>2)<<5)|(b>>3) or 1)
    palette += [0]*(256-len(palette));indices=[]
    for i in range(FRAMES):
        x,y=(i%4)*SIZE,(i//4)*SIZE
        q=quant.crop((x,y,x+SIZE,y+SIZE)).tobytes();a=atlas.crop((x,y,x+SIZE,y+SIZE)).getchannel('A').tobytes()
        indices.extend(v+1 if alpha>=180 else 0 for v,alpha in zip(q,a))
    encoded=bytearray();run=0;last=None
    for v in indices:
        if v==last and run<255:run+=1
        else:
            if run:encoded.extend((run,last))
            last=v;run=1
    encoded.extend((run,last))
    header=struct.pack('<4sHHHHI32s32s64s',b'WPP1',SIZE,SIZE,FRAMES,256,len(encoded),pip_id.encode(),asset_id.encode(),name.encode()[:63])
    body=header+bytes(bounds)+struct.pack('<256H',*palette)+encoded;pack=body+struct.pack('<I',zlib.crc32(body))
    if len(pack)>MAX_PACK:raise ValueError('הדמות מפורטת מדי לזיכרון המכשיר; נסה עיצוב פשוט יותר')
    directory.mkdir(parents=True,exist_ok=True)
    (directory/'atlas.png').write_bytes(png(atlas));(directory/'preview.png').write_bytes(png(atlas.crop((0,0,SIZE,SIZE))))
    (directory/'character.bin').write_bytes(pack)
    manifest={'version':1,'size':SIZE,'frames':FRAMES,'poses':POSES,'motions':MOTIONS,'sha256':hashlib.sha256(pack).hexdigest(),'bytes':len(pack)}
    (directory/'manifest.json').write_text(json.dumps(manifest))
    return manifest
