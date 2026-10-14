"""Usine à vidéos — moteur de rendu.

Une vidéo = une liste de scènes. Chaque scène :
  kicker   : petit bandeau en haut (optionnel)            ex. "13 OCTOBRE"
  big      : gros chiffre/mot (optionnel)                  ex. "161 000"
  title    : texte principal ; *mot* = surligné couleur    ex. "PERSONNE NE T'EXPLIQUE *POURQUOI*"
  sub      : ligne sous le titre (optionnel)
  say      : sous-titre affiché en bas (= ce que dit la voix)
  voice    : texte prononcé (optionnel, sinon = say)
  image    : chemin d'image (optionnel)
  note     : petite mention (ex. "Photo d'archive 2018")
Options globales : style ('photo' | 'manga'), tag, sources, accent (#RRGGBB), voice_speed, music (bool)
"""
import json, math, os, random, re, subprocess, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageFont

FPS = 30
W, H = 1080, 1920
BASE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.environ.get('MODELS_DIR', os.path.join(BASE, 'models'))
FONT_DIR = os.environ.get('INTER_DIR', '/usr/share/fonts/opentype/inter')
JP_FONT = os.environ.get('JP_FONT', '/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc')
PALETTES = ['#FF2846', '#FFC832', '#46AAFF', '#3CE6A0', '#9670FF', '#FF7828', '#FF4678', '#AABEDC']

_kokoro = None
def kokoro():
    global _kokoro
    if _kokoro is None:
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(os.path.join(MODELS, 'kokoro-v1.0.onnx'), os.path.join(MODELS, 'voices-v1.0.bin'))
    return _kokoro

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-2000:])

def hex2rgb(h):
    h = h.lstrip('#'); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

def ass_col(rgb):
    return f"&H00{rgb[2]:02X}{rgb[1]:02X}{rgb[0]:02X}&"

def esc(t):
    return (t or '').replace('{', '(').replace('}', ')').replace('\n', '\\N')

def hl(t, acc):
    """*mot* -> mot en couleur d'accent"""
    return re.sub(r'\*(.+?)\*', lambda m: '{\\c' + ass_col(acc) + '}' + m.group(1) + '{\\c&HFFFFFF&}', esc(t))

def ts(x):
    return f"0:{int(x // 60):02d}:{x % 60:05.2f}"

# ------------------------------------------------------------------ voice
def synth_voices(scenes, wd, speed, progress):
    import soundfile as sf
    durs = []
    for i, s in enumerate(scenes):
        text = (s.get('voice') or s.get('say') or '').strip()
        out = f'{wd}/t{i:02d}.wav'
        if text:
            a, sr = kokoro().create(text, voice='ff_siwis', speed=speed, lang='fr-fr')
            sf.write(f'{wd}/k{i:02d}.wav', a, sr)
            run(['ffmpeg', '-v', 'error', '-y', '-i', f'{wd}/k{i:02d}.wav', '-af',
                 'silenceremove=start_periods=1:start_threshold=-45dB,areverse,'
                 'silenceremove=start_periods=1:start_threshold=-45dB,areverse,aresample=44100',
                 '-ac', '1', out])
            with wave.open(out) as w: durs.append(w.getnframes() / w.getframerate())
        else:
            durs.append(0.0)
        progress(5 + 25 * (i + 1) / len(scenes), f'Voix {i + 1}/{len(scenes)}')
    return durs

# ------------------------------------------------------------------ backgrounds
def _halftone():
    im = Image.new('L', (W, H), 0); d = ImageDraw.Draw(im); step = 14
    for y in range(0, H, step):
        r = 4.2 * (0.35 + 0.65 * y / H)
        for x in range((y // step) % 2 * step // 2, W, step):
            d.ellipse((x - r, y - r, x + r, y + r), fill=255)
    return im

def _speedlines(seed, acc, n=90):
    rnd = random.Random(seed); im = Image.new('RGBA', (W // 2, H // 2), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    cx, cy = 270, 450
    for _ in range(n):
        a = rnd.uniform(0, 2 * math.pi); r0 = rnd.uniform(85, 165); r1 = 700; w = rnd.uniform(0.004, 0.02)
        pts = [(cx + r0 * math.cos(a), cy + r0 * math.sin(a)), (cx + r1 * math.cos(a - w), cy + r1 * math.sin(a - w)),
               (cx + r1 * math.cos(a + w), cy + r1 * math.sin(a + w))]
        d.polygon(pts, fill=(acc if rnd.random() < 0.25 else (255, 255, 255)) + (int(rnd.uniform(40, 120)),))
    return im.resize((W, H), Image.BILINEAR)

def _cover_fg(im, z):
    """4:5 crop for the photo panel"""
    iw, ih = im.size
    if iw / ih > 0.8: ch, cw = ih, ih * 0.8
    else: cw, ch = iw, iw * 1.25
    w2, h2 = cw / z, ch / z
    box = (int(iw / 2 - w2 / 2), int(ih / 2 - h2 / 2), int(iw / 2 + w2 / 2), int(ih / 2 + h2 / 2))
    return im.crop(box).resize((1080, 1350), Image.LANCZOS)

def render_frames(scenes, starts, total, style, wd, progress):
    os.makedirs(f'{wd}/fr', exist_ok=True)
    bounds = [round(s * FPS) for s in starts] + [round(total * FPS)]
    HT = _halftone() if style == 'manga' else None
    oi = 0; nframes = bounds[-1]
    for ci, s in enumerate(scenes):
        acc = s['_acc']; bgc = tuple(int(v * 0.08) for v in acc)
        img = Image.open(s['image']).convert('RGB') if s.get('image') else None
        n = bounds[ci + 1] - bounds[ci]
        if style == 'manga' or img is None:
            base = Image.new('RGB', (W, H), bgc)
            g = np.linspace(0, 1, H)[:, None, None]
            arr = np.clip(np.array(base, np.float32) * (0.6 + 0.8 * g) + np.array(acc) * 0.10 * (1 - g), 0, 255)
            base = Image.fromarray(arr.astype(np.uint8))
            if HT is None: HT = _halftone()
            base = Image.composite(Image.new('RGB', (W, H), tuple(int(v * 0.35) for v in acc)), base, HT.point(lambda v: int(v * 0.45)))
            if s.get('kanji'):
                f = ImageFont.truetype(JP_FONT, 1100); kj = Image.new('L', (W, H), 0); d = ImageDraw.Draw(kj)
                bb = d.textbbox((0, 0), s['kanji'][:1], font=f)
                d.text(((W - bb[2] + bb[0]) / 2 - bb[0], (H - bb[3] + bb[1]) / 2 - bb[1] - 60), s['kanji'][:1], font=f, fill=255)
                base = Image.composite(Image.new('RGB', (W, H), tuple(min(255, int(v * 0.55 + 20)) for v in acc)), base, kj.point(lambda v: int(v * 0.22)))
            lines = [_speedlines(ci * 100 + j, acc) for j in range(6)]
        else:
            iw, ih = img.size
            bw = int(H * iw / ih); base = img.resize((max(bw, W), H)).filter(ImageFilter.GaussianBlur(30))
            base = base.crop(((base.width - W) // 2, 0, (base.width - W) // 2 + W, H))
            base = ImageEnhance.Brightness(base).enhance(0.33)
            lines = None
        for kk in range(n):
            t = kk / FPS; p = kk / max(1, n - 1)
            fr = base.copy()
            if lines:
                sl = lines[(kk // 2) % 6]
                if t > 0.9: sl = Image.fromarray((np.array(sl) * np.array([1, 1, 1, 0.45])).astype(np.uint8))
                fr.paste(sl, (0, 0), sl)
            if img is not None:
                z = (1.0 + 0.12 * p) if ci % 2 == 0 else (1.12 - 0.12 * p)
                if kk < 5: z += 0.07 * (5 - kk) / 5
                fg = _cover_fg(img, z)
                fg = ImageEnhance.Brightness(ImageEnhance.Contrast(fg).enhance(1.15)).enhance(0.62 if style == 'photo' else 0.5)
                if style == 'manga':
                    fg = fg.resize((900, 1125)); fr.paste(fg, (90, 400))
                else:
                    fr.paste(fg, (0, 285))
            if style == 'manga':
                d = ImageDraw.Draw(fr)
                d.rectangle((40, 330, W - 40, 1560), outline=(255, 255, 255), width=10)
                d.rectangle((52, 342, W - 52, 1548), outline=acc, width=4)
            if t < 0.12:
                fr = Image.blend(fr, Image.new('RGB', (W, H), (255, 255, 255)), max(0, 0.75 - t * 5))
            if style == 'manga' and t < 0.35:
                amp = int(22 * (1 - t / 0.35)); dx, dy = random.randint(-amp, amp), random.randint(-amp, amp)
                fr = fr.transform((W, H), Image.AFFINE, (1, 0, dx, 0, 1, dy), fillcolor=bgc)
            fr.save(f'{wd}/fr/o{oi:05d}.jpg', quality=90); oi += 1
            if oi % 30 == 0: progress(30 + 50 * oi / nframes, f'Images {oi}/{nframes}')

# ------------------------------------------------------------------ captions
STYLES = """Style: Big,Inter Black,260,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,-4,0,1,10,8,5,40,40,0,1
Style: Title,Inter Black,104,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,8,6,5,50,50,0,1
Style: TitleLow,Inter Black,92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,8,6,8,50,50,1150,1
Style: Kicker,Inter Black,58,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,4,0,3,14,0,8,50,50,215,1
Style: Note,Inter ExtraBold,40,&H00DDDDDD,&H00DDDDDD,&H00000000,&H00000000,0,0,0,0,100,100,0,0,3,10,0,8,50,50,300,1
Style: Sub,Inter Black,56,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,6,4,8,70,70,1300,1
Style: Say,Inter ExtraBold,48,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,5,3,2,70,70,140,1
Style: Src,Inter Medium,24,&H00BBBBBB,&H00BBBBBB,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,60,60,70,1
Style: Tag,Inter Black,40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,3,0,1,3,0,8,60,60,150,1
Style: Bar,Inter Black,20,&H004628FF,&H004628FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1"""

def write_ass(scenes, starts, total, spec, path):
    POP = r"{\fscx130\fscy130\t(0,120,\fscx100\fscy100)}"
    SLAM = r"{\fscx170\fscy170\t(0,90,\fscx100\fscy100)}"
    ev = []
    def add(s, e, st, tx): ev.append(f"Dialogue: 1,{ts(s)},{ts(e)},{st},,0,0,0,,{tx}")
    N = len(scenes)
    for i, s in enumerate(scenes):
        a = starts[i]; b = starts[i + 1] if i + 1 < N else total; acc = s['_acc']
        if s.get('kicker'): add(a, b, 'Kicker', esc(s['kicker']).upper())
        if s.get('note'): add(a, b, 'Note', esc(s['note']))
        if s.get('big'):
            add(a, b, 'Big', SLAM + '{\\c' + ass_col(acc) + '}' + esc(s['big']))
            if s.get('title'): add(a + 0.15, b, 'TitleLow', POP + hl(s['title'].upper(), acc))
        elif s.get('title'):
            title = s['title'].upper()
            fs = '{\\fs84}' if len(title) > 40 else ''
            add(a, b, 'Title', fs + POP + hl(title, acc))
        if s.get('sub'): add(a + 0.4, b, 'Sub', POP + hl(s['sub'], acc))
        if s.get('say'): add(a, b, 'Say', esc(s['say']))
    if spec.get('tag'):
        ev.append(f"Dialogue: 1,{ts(0)},{ts(total)},Tag,,0,0,0,,{{\\c&H4628FF&}}●{{\\c&HFFFFFF&}} {esc(spec['tag']).upper()}")
    if spec.get('sources'):
        ev.append(f"Dialogue: 1,{ts(0)},{ts(total)},Src,,0,0,0,,{esc(spec['sources'])}")
    ms = int(total * 1000)
    ev.append(f"Dialogue: 0,{ts(0)},{ts(total)},Bar,,0,0,0,,{{\\pos(0,0)\\clip(0,0,0,14)\\t(0,{ms},\\clip(0,0,1080,14))\\p1}}m 0 0 l 1080 0 1080 14 0 14{{\\p0}}")
    with open(path, 'w') as f:
        f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n[V4+ Styles]\n"
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
                + STYLES + "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n" + '\n'.join(ev) + '\n')

# ------------------------------------------------------------------ audio
def build_audio(scenes, starts, total, spec, wd):
    style = spec.get('style', 'photo')
    if style == 'manga':
        b = 60 / 140
        bed = (f"0.8*sin(2*PI*(45+90*exp(-25*mod(t,{2*b})))*mod(t,{2*b}))*exp(-7*mod(t,{2*b}))"
               f"+(random(0)*2-1)*exp(-18*mod(t+{b},{2*b}))*0.5+(random(1)*2-1)*exp(-90*mod(t,{b/2}))*0.15"
               "+0.06*(sin(2*PI*220*t)+sin(2*PI*261.6*t)+sin(2*PI*329.6*t))")
    else:
        bed = ("sin(2*PI*(45+80*exp(-20*mod(t,0.5)))*mod(t,0.5))*exp(-8*mod(t,0.5))*0.8"
               "+sin(2*PI*55*t)*0.12+sin(2*PI*82.4*t)*0.06+(random(0)*2-1)*exp(-70*mod(t+0.25,0.5))*0.18")
    vol = 0.2 if spec.get('music', True) else 0.0
    run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', f"aevalsrc='{bed}':d={total}:s=44100",
         '-af', f'lowpass=f=9000,volume={vol}', '-ac', '2', f'{wd}/bed.wav'])
    run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
         "aevalsrc='sin(2*PI*(75-40*t)*t)*exp(-6*t)+(random(0)*2-1)*0.4*exp(-15*t)':d=0.85:s=44100", '-ac', '2', f'{wd}/hit.wav'])
    ins, fl, lab = [], [], []
    def place(p, at, v):
        k = len(lab); d = max(0, int(at * 1000))
        ins.extend(['-i', p]); fl.append(f"[{k+1}:a]adelay={d}|{d},volume={v}[x{k}]"); lab.append(f"[x{k}]")
    for i, s in enumerate(scenes):
        place(f'{wd}/hit.wav', starts[i], 0.5)
        if os.path.exists(f'{wd}/t{i:02d}.wav'): place(f'{wd}/t{i:02d}.wav', starts[i] + s['_lead'], 1.5)
    fc = ';'.join(fl) + f";[0:a]{''.join(lab)}amix=inputs={len(lab)+1}:normalize=0:duration=first,acompressor=threshold=-14dB:ratio=3,alimiter=limit=0.93[a]"
    run(['ffmpeg', '-v', 'error', '-y', '-i', f'{wd}/bed.wav'] + ins + ['-filter_complex', fc, '-map', '[a]', '-ac', '2',
         '-c:a', 'aac', '-b:a', '192k', f'{wd}/audio.m4a'])

# ------------------------------------------------------------------ main entry
def render(spec, wd, progress=lambda p, m: None):
    """spec: dict (voir docstring). Retourne le chemin du mp4."""
    os.makedirs(wd, exist_ok=True)
    scenes = [dict(s) for s in spec['scenes'] if any(s.get(k) for k in ('title', 'big', 'say', 'voice', 'image'))]
    if not scenes: raise ValueError('Aucune scène')
    style = spec.get('style', 'photo')
    acc0 = hex2rgb(spec['accent']) if spec.get('accent') else None
    for i, s in enumerate(scenes):
        s['_acc'] = hex2rgb(s['accent']) if s.get('accent') else (acc0 if acc0 and style == 'photo' else hex2rgb(PALETTES[i % len(PALETTES)]))
        s['_lead'] = 0.12
    progress(2, 'Préparation')
    vd = synth_voices(scenes, wd, float(spec.get('voice_speed', 1.12)), progress)
    durs = [max(float(s.get('min_duration', 2.2)), d + 0.4) for s, d in zip(scenes, vd)]
    starts, t = [], 0.0
    for d in durs: starts.append(t); t += d
    total = t + 0.6
    render_frames(scenes, starts, total, style, wd, progress)
    progress(82, 'Sous-titres')
    write_ass(scenes, starts, total, spec, f'{wd}/v.ass')
    progress(85, 'Audio')
    build_audio(scenes, starts, total, spec, wd)
    progress(88, 'Encodage final')
    out = f'{wd}/video.mp4'
    run(['ffmpeg', '-v', 'error', '-y', '-framerate', str(FPS), '-i', f'{wd}/fr/o%05d.jpg', '-i', f'{wd}/audio.m4a',
         '-vf', f"ass={wd}/v.ass:fontsdir={FONT_DIR},format=yuv420p",
         '-c:v', 'libx264', '-preset', 'medium', '-crf', '22', '-maxrate', '5M', '-bufsize', '10M',
         '-c:a', 'copy', '-shortest', '-movflags', '+faststart', out])
    # nettoyage des images intermédiaires
    for f in os.listdir(f'{wd}/fr'): os.remove(f'{wd}/fr/{f}')
    progress(100, f'Terminé · {total:.0f} s')
    return out, total

if __name__ == '__main__':
    import sys
    spec = json.load(open(sys.argv[1]))
    print(render(spec, sys.argv[2], lambda p, m: print(f'{p:5.1f}% {m}')))
