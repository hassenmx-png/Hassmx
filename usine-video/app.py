"""Usine à vidéos — serveur web (FastAPI)."""
import json, os, re, secrets, threading, time, uuid
import requests
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import engine

DATA = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(__file__), 'data'))
os.makedirs(f'{DATA}/jobs', exist_ok=True); os.makedirs(f'{DATA}/uploads', exist_ok=True)
USER = os.environ.get('APP_USER', 'admin'); PASS = os.environ.get('APP_PASSWORD', '')
UA = {'User-Agent': 'UsineVideo/1.0 (personal tool)'}

app = FastAPI(title='Usine à vidéos')
security = HTTPBasic(auto_error=False)

def auth(creds: HTTPBasicCredentials = Depends(security)):
    if not PASS: return True
    if creds and secrets.compare_digest(creds.username, USER) and secrets.compare_digest(creds.password, PASS):
        return True
    raise HTTPException(401, headers={'WWW-Authenticate': 'Basic'})

jobs = {}
lock = threading.Lock()   # un rendu à la fois (CPU)

def job_path(jid): return f'{DATA}/jobs/{jid}'

def worker(jid, spec):
    j = jobs[jid]
    def prog(p, m): j.update(progress=round(p, 1), message=m)
    with lock:
        j['status'] = 'running'
        try:
            out, total = engine.render(spec, job_path(jid), prog)
            j.update(status='done', duration=round(total, 1), file=out)
        except Exception as e:
            j.update(status='error', message=str(e)[:500])
    json.dump({k: v for k, v in j.items()}, open(f'{job_path(jid)}/job.json', 'w'))

@app.get('/', response_class=HTMLResponse)
def index(_=Depends(auth)):
    return open(os.path.join(os.path.dirname(__file__), 'static', 'index.html'), encoding='utf-8').read()

@app.post('/api/upload')
async def upload(file: UploadFile = File(...), _=Depends(auth)):
    ext = os.path.splitext(file.filename or '')[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.webp'): raise HTTPException(400, 'Image jpg/png/webp uniquement')
    name = uuid.uuid4().hex + ext
    with open(f'{DATA}/uploads/{name}', 'wb') as f: f.write(await file.read())
    return {'id': name, 'url': f'/api/image/{name}'}

@app.get('/api/image/{name}')
def image(name: str, _=Depends(auth)):
    if not re.fullmatch(r'[a-f0-9]{32}\.(jpg|jpeg|png|webp)', name): raise HTTPException(404)
    return FileResponse(f'{DATA}/uploads/{name}')

@app.get('/api/commons')
def commons(q: str, _=Depends(auth)):
    """Recherche d'images libres de droits sur Wikimedia Commons (CC BY / BY-SA / domaine public)."""
    r = requests.get('https://commons.wikimedia.org/w/api.php', headers=UA, timeout=20, params={
        'action': 'query', 'format': 'json', 'generator': 'search', 'gsrsearch': q + ' filetype:bitmap',
        'gsrnamespace': 6, 'gsrlimit': 24, 'prop': 'imageinfo', 'iiprop': 'url|size|extmetadata', 'iiurlwidth': 1200})
    out = []
    for p in (r.json().get('query', {}).get('pages', {}) or {}).values():
        ii = p['imageinfo'][0]; m = ii.get('extmetadata', {})
        lic = m.get('LicenseShortName', {}).get('value', '')
        if not re.search(r'CC|Public domain|PD', lic, re.I) or re.search(r'NC|ND', lic): continue
        out.append({'thumb': ii.get('thumburl'), 'title': p['title'][5:], 'license': lic,
                    'author': re.sub('<[^>]+>', '', m.get('Artist', {}).get('value', '')).strip()[:80],
                    'page': ii.get('descriptionurl')})
    return out

@app.post('/api/commons/import')
def commons_import(payload: dict, _=Depends(auth)):
    url = payload.get('thumb', '')
    if not url.startswith('https://upload.wikimedia.org/'): raise HTTPException(400)
    name = uuid.uuid4().hex + '.jpg'
    data = requests.get(url, headers=UA, timeout=30).content
    open(f'{DATA}/uploads/{name}', 'wb').write(data)
    return {'id': name, 'url': f'/api/image/{name}', 'credit': f"{payload.get('author','')} ({payload.get('license','')})"}

@app.post('/api/render')
def render(spec: dict, _=Depends(auth)):
    scenes = []
    for s in spec.get('scenes', []):
        s = {k: v for k, v in s.items() if v not in (None, '')}
        if s.get('image_id'):
            if not re.fullmatch(r'[a-f0-9]{32}\.(jpg|jpeg|png|webp)', s['image_id']): raise HTTPException(400)
            s['image'] = f"{DATA}/uploads/{s['image_id']}"
        scenes.append(s)
    spec['scenes'] = scenes
    jid = time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:6]
    os.makedirs(job_path(jid), exist_ok=True)
    json.dump(spec, open(f'{job_path(jid)}/spec.json', 'w'), ensure_ascii=False)
    jobs[jid] = {'id': jid, 'status': 'queued', 'progress': 0, 'message': "En file d'attente",
                 'title': (spec.get('name') or 'Vidéo')[:80]}
    threading.Thread(target=worker, args=(jid, spec), daemon=True).start()
    return {'id': jid}

@app.get('/api/jobs')
def list_jobs(_=Depends(auth)):
    out = dict(jobs)
    for d in sorted(os.listdir(f'{DATA}/jobs'))[-30:]:
        if d not in out and os.path.exists(f'{job_path(d)}/job.json'):
            out[d] = json.load(open(f'{job_path(d)}/job.json'))
    return sorted(out.values(), key=lambda j: j['id'], reverse=True)

@app.get('/api/job/{jid}')
def job(jid: str, _=Depends(auth)):
    if jid not in jobs:
        p = f'{job_path(jid)}/job.json'
        if not os.path.exists(p): raise HTTPException(404)
        return json.load(open(p))
    return jobs[jid]

@app.get('/api/video/{jid}')
def video(jid: str, _=Depends(auth)):
    if not re.fullmatch(r'[0-9-]+[a-f0-9]{6}', jid): raise HTTPException(404)
    p = f'{job_path(jid)}/video.mp4'
    if not os.path.exists(p): raise HTTPException(404)
    return FileResponse(p, media_type='video/mp4', filename=f'video-{jid}.mp4')

@app.get('/api/spec/{jid}')
def spec(jid: str, _=Depends(auth)):
    p = f'{job_path(jid)}/spec.json'
    if not os.path.exists(p): raise HTTPException(404)
    return json.load(open(p))
