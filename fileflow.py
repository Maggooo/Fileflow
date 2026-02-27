#!/usr/bin/env python3
"""
Organizator de Fisiere — interfata web moderna, zero dependinte externe.
Ruleaza: python3 organizator.py
"""

import os, shutil, hashlib, json, threading, webbrowser
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

LIMITA_MARIME_KB = 50
FOLDER_BACKUP    = "_backup_sters"
PORT             = 7491

# ─────────────────────────────────────────────────────────────
#  LOGICA ORGANIZARE
# ─────────────────────────────────────────────────────────────

def hash_fisier(cale, bloc=65536):
    h = hashlib.md5()
    with open(cale, 'rb') as f:
        while chunk := f.read(bloc):
            h.update(chunk)
    return h.hexdigest()

def obtine_data_creare(cale):
    s = os.stat(cale)
    try:    return datetime.fromtimestamp(s.st_birthtime)
    except: return datetime.fromtimestamp(min(s.st_mtime, s.st_ctime))

def rezolva_conflict(cale):
    if not os.path.exists(cale): return cale
    baza, ext = os.path.splitext(cale)
    i = 1
    while os.path.exists(f"{baza}_{i}{ext}"): i += 1
    return f"{baza}_{i}{ext}"

def colecteaza_fisiere(src):
    out = []
    for r, _, fs in os.walk(src):
        for f in fs:
            out.append(os.path.join(r, f))
    return out

def organizeaza(cfg, progress_cb):
    src     = cfg["sursa"]
    dest    = cfg["destinatie"]
    metoda  = cfg["metoda"]
    dry_run = cfg.get("dry_run", False)
    actiune = "Mutat" if metoda == "m" else "Copiat"

    ext_inc = set(cfg.get("ext_include", "").split())
    ext_exc = set(cfg.get("ext_exclude", "").split())
    sterge_mici = cfg.get("sterge_mici", False)
    backup_mici = cfg.get("backup_mici", False)
    limita_kb   = cfg.get("limita_kb", LIMITA_MARIME_KB)
    omit_dup    = cfg.get("omit_duplicate", False)

    fisiere = colecteaza_fisiere(src)
    total   = len(fisiere)
    log     = []
    hashuri = {}
    stats   = {"procesat": 0, "sters": 0, "duplicate": 0, "omis_ext": 0, "erori": 0}

    for idx, cale in enumerate(fisiere):
        nume      = os.path.basename(cale)
        ext_bruta = os.path.splitext(nume)[1].lower().lstrip('.')
        try:    marime_kb = os.path.getsize(cale) / 1024
        except: marime_kb = 0
        marime_str = f"{marime_kb:.1f} KB"
        entry = {"fisier": nume, "dest": "", "marime": marime_str, "motiv": "", "status": ""}

        progress_cb(idx + 1, total, nume)

        # 1. Filtrare extensie
        if ext_inc and ext_bruta not in ext_inc:
            entry.update(status="omis-ext", motiv=f"extensie '{ext_bruta}' neinclusă")
            log.append(entry); stats["omis_ext"] += 1; continue
        if ext_bruta in ext_exc:
            entry.update(status="omis-ext", motiv=f"extensie '{ext_bruta}' exclusă")
            log.append(entry); stats["omis_ext"] += 1; continue

        # 2. Stergere fisiere mici
        if sterge_mici and marime_kb < limita_kb:
            if not dry_run:
                if backup_mici:
                    bk = os.path.join(src, FOLDER_BACKUP)
                    os.makedirs(bk, exist_ok=True)
                    shutil.copy2(cale, rezolva_conflict(os.path.join(bk, nume)))
                try:
                    os.remove(cale)
                    status = "backup+sters" if backup_mici else "sters"
                except Exception as e:
                    entry.update(status="eroare", motiv=str(e))
                    log.append(entry); stats["erori"] += 1; continue
            else:
                status = "dry-run"
            entry.update(status=status, motiv=f"< {limita_kb} KB")
            log.append(entry); stats["sters"] += 1; continue

        # 3. Duplicate
        if omit_dup:
            try:
                h = hash_fisier(cale)
                if h in hashuri:
                    orig = os.path.basename(hashuri[h])
                    entry.update(status="duplicat", motiv=f"egal cu '{orig}'")
                    log.append(entry); stats["duplicate"] += 1; continue
                hashuri[h] = cale
            except: pass

        # 4. Calcul destinatie
        ext_folder = ext_bruta or "fara_extensie"
        data       = obtine_data_creare(cale)
        folder_d   = os.path.join(dest, ext_folder, str(data.year), data.strftime("%m-%B"))
        cale_dest  = rezolva_conflict(os.path.join(folder_d, nume))
        dest_rel   = os.path.relpath(cale_dest, dest)

        # 5. Copiere / Mutare
        try:
            if not dry_run:
                os.makedirs(folder_d, exist_ok=True)
                if metoda == "m": shutil.move(cale, cale_dest)
                else:             shutil.copy2(cale, cale_dest)
                if omit_dup: hashuri[h] = cale_dest
            status = "dry-run" if dry_run else actiune.lower()
            entry.update(status=status, dest=dest_rel)
            log.append(entry); stats["procesat"] += 1
        except Exception as e:
            entry.update(status="eroare", motiv=str(e))
            log.append(entry); stats["erori"] += 1

    # Curatare directoare goale
    if metoda == "m" and not dry_run:
        for r, _, _ in os.walk(src, topdown=False):
            if r == src: continue
            try: os.rmdir(r)
            except: pass

    return {"log": log, "stats": stats, "actiune": actiune, "dry_run": dry_run}

# ─────────────────────────────────────────────────────────────
#  STATE GLOBAL
# ─────────────────────────────────────────────────────────────

state = {
    "running":  False,
    "progress": {"current": 0, "total": 0, "fisier": ""},
    "result":   None,
}

# ─────────────────────────────────────────────────────────────
#  INTERFATA HTML
# ─────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Organizator Fișiere</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@400;600;800&display=swap');

  :root {
    --bg:      #0f0f13;
    --surface: #17171e;
    --border:  #2a2a36;
    --accent:  #7c6af7;
    --accent2: #f76a8c;
    --green:   #4ade80;
    --yellow:  #fbbf24;
    --red:     #f87171;
    --muted:   #6b6b80;
    --text:    #e8e8f0;
  }

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'Syne', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    overflow-x: hidden;
  }

  body::before {
    content: '';
    position: fixed; inset: 0;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.035'/%3E%3C/svg%3E");
    pointer-events: none; z-index: 0;
  }

  .wrap { max-width: 860px; margin: 0 auto; padding: 40px 24px; position: relative; z-index: 1; }

  header { margin-bottom: 44px; }
  .logo { font-size: 11px; font-family: 'DM Mono', monospace; color: var(--accent); letter-spacing: 3px; text-transform: uppercase; margin-bottom: 10px; }
  h1 { font-size: clamp(26px, 5vw, 44px); font-weight: 800; line-height: 1.1; }
  h1 span { color: var(--accent); }
  .subtitle { color: var(--muted); font-size: 13px; margin-top: 6px; font-family: 'DM Mono', monospace; }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 24px 28px;
    margin-bottom: 16px;
  }
  .card-title {
    font-size: 10px; font-family: 'DM Mono', monospace;
    color: var(--accent); letter-spacing: 2px; text-transform: uppercase;
    margin-bottom: 18px; display: flex; align-items: center; gap: 8px;
  }
  .card-title::after { content: ''; flex: 1; height: 1px; background: var(--border); }

  .field { margin-bottom: 14px; }
  .field:last-child { margin-bottom: 0; }
  label {
    display: block; font-size: 11px; color: var(--muted);
    font-family: 'DM Mono', monospace; margin-bottom: 6px;
    letter-spacing: 1px; text-transform: uppercase;
  }
  input[type=text] {
    width: 100%; background: var(--bg);
    border: 1px solid var(--border); border-radius: 8px;
    padding: 10px 14px; color: var(--text); font-family: 'DM Mono', monospace;
    font-size: 13px; transition: border-color .2s; outline: none;
  }
  input[type=text]:focus { border-color: var(--accent); }
  input[type=text]::placeholder { color: #383845; }

  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  @media (max-width: 580px) { .grid2 { grid-template-columns: 1fr; } }

  .toggle-group { display: flex; gap: 8px; }
  .toggle-btn {
    padding: 8px 20px; border-radius: 8px; border: 1px solid var(--border);
    background: transparent; color: var(--muted); font-family: 'Syne', sans-serif;
    font-size: 13px; font-weight: 600; cursor: pointer; transition: all .15s;
  }
  .toggle-btn:hover { border-color: var(--accent); color: var(--text); }
  .toggle-btn.active { background: var(--accent); border-color: var(--accent); color: #fff; }

  .switch-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 0; border-bottom: 1px solid var(--border);
  }
  .switch-row:last-child { border-bottom: none; padding-bottom: 0; }
  .switch-label { font-size: 14px; }
  .switch-sub { font-size: 11px; color: var(--muted); font-family: 'DM Mono', monospace; margin-top: 2px; }
  .switch { position: relative; width: 42px; height: 22px; flex-shrink: 0; }
  .switch input { opacity: 0; width: 0; height: 0; }
  .slider {
    position: absolute; inset: 0; background: var(--border);
    border-radius: 22px; cursor: pointer; transition: background .2s;
  }
  .slider::before {
    content: ''; position: absolute;
    width: 16px; height: 16px; left: 3px; top: 3px;
    background: var(--muted); border-radius: 50%; transition: all .2s;
  }
  .switch input:checked + .slider { background: var(--accent); }
  .switch input:checked + .slider::before { transform: translateX(20px); background: #fff; }

  .btn-run {
    width: 100%; padding: 15px; border-radius: 12px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border: none; color: #fff; font-family: 'Syne', sans-serif;
    font-size: 15px; font-weight: 800; cursor: pointer;
    letter-spacing: 1px; text-transform: uppercase;
    transition: opacity .2s, transform .1s;
    position: relative; overflow: hidden;
  }
  .btn-run:hover { opacity: .9; }
  .btn-run:active { transform: scale(.98); }
  .btn-run:disabled { opacity: .35; cursor: not-allowed; }
  .btn-run .shimmer {
    position: absolute; top: 0; left: -100%; width: 60%; height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,.15), transparent);
    animation: shimmer 2s infinite;
  }
  @keyframes shimmer { to { left: 200%; } }

  #progress-section { display: none; }
  .progress-bar-wrap { background: var(--border); border-radius: 99px; height: 5px; overflow: hidden; margin: 12px 0; }
  .progress-bar-fill { height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent2)); border-radius: 99px; transition: width .3s; width: 0%; }
  .progress-text { font-family: 'DM Mono', monospace; font-size: 12px; color: var(--muted); }
  .progress-file { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--accent); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 4px; }

  #result-section { display: none; }

  .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; margin-bottom: 22px; }
  .stat-card {
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 10px; padding: 14px; text-align: center;
  }
  .stat-num { font-size: 30px; font-weight: 800; line-height: 1; }
  .stat-label { font-size: 10px; color: var(--muted); font-family: 'DM Mono', monospace; margin-top: 4px; letter-spacing: 1px; text-transform: uppercase; }
  .stat-card.green .stat-num  { color: var(--green); }
  .stat-card.yellow .stat-num { color: var(--yellow); }
  .stat-card.red .stat-num    { color: var(--red); }
  .stat-card.purple .stat-num { color: var(--accent); }
  .stat-card.muted .stat-num  { color: var(--muted); }

  .table-controls { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; align-items: center; }
  .filter-btn {
    padding: 4px 12px; border-radius: 6px; border: 1px solid var(--border);
    background: transparent; color: var(--muted); font-family: 'DM Mono', monospace;
    font-size: 10px; cursor: pointer; transition: all .15s; text-transform: uppercase; letter-spacing: 1px;
  }
  .filter-btn:hover, .filter-btn.active { background: var(--accent); border-color: var(--accent); color: #fff; }
  .search-input {
    margin-left: auto; padding: 4px 12px; border-radius: 6px;
    border: 1px solid var(--border); background: var(--bg);
    color: var(--text); font-family: 'DM Mono', monospace; font-size: 11px;
    outline: none; width: 180px;
  }
  .search-input:focus { border-color: var(--accent); }

  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  thead th {
    text-align: left; padding: 7px 10px;
    font-family: 'DM Mono', monospace; font-size: 10px;
    color: var(--muted); letter-spacing: 1px; text-transform: uppercase;
    border-bottom: 1px solid var(--border); cursor: pointer; user-select: none;
  }
  thead th:hover { color: var(--accent); }
  thead th .sa { margin-left: 3px; opacity: .4; }
  thead th.sorted .sa { opacity: 1; color: var(--accent); }
  tbody tr { border-bottom: 1px solid var(--border); transition: background .1s; }
  tbody tr:hover { background: rgba(124,106,247,.06); }
  td { padding: 7px 10px; font-family: 'DM Mono', monospace; vertical-align: middle; }
  td.fn { max-width: 180px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  td.dp { max-width: 220px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--muted); font-size: 11px; }
  td.sz { color: var(--muted); white-space: nowrap; }

  .badge { display: inline-block; padding: 2px 7px; border-radius: 99px; font-size: 10px; font-weight: 600; letter-spacing: .5px; text-transform: uppercase; }
  .b-ok    { background: rgba(74,222,128,.15);  color: var(--green); }
  .b-st    { background: rgba(251,191,36,.15);   color: var(--yellow); }
  .b-dup   { background: rgba(107,107,128,.15);  color: var(--muted); }
  .b-dry   { background: rgba(124,106,247,.15);  color: var(--accent); }
  .b-err   { background: rgba(248,113,113,.15);  color: var(--red); }

  .dry-badge {
    display: inline-block; padding: 4px 12px; border-radius: 6px;
    background: rgba(124,106,247,.15); color: var(--accent);
    font-family: 'DM Mono', monospace; font-size: 11px; letter-spacing: 1px;
    text-transform: uppercase; margin-bottom: 16px;
  }

  .pagination { display: flex; gap: 5px; justify-content: center; margin-top: 14px; flex-wrap: wrap; }
  .page-btn {
    padding: 3px 10px; border-radius: 5px; border: 1px solid var(--border);
    background: transparent; color: var(--muted); font-family: 'DM Mono', monospace;
    font-size: 11px; cursor: pointer; transition: all .15s;
  }
  .page-btn:hover, .page-btn.active { background: var(--accent); border-color: var(--accent); color: #fff; }

  .btn-back {
    display: inline-block; margin-top: 18px; padding: 9px 18px;
    border-radius: 8px; border: 1px solid var(--border);
    background: transparent; color: var(--text); font-family: 'Syne', sans-serif;
    font-size: 13px; font-weight: 600; cursor: pointer; transition: all .15s;
  }
  .btn-back:hover { border-color: var(--accent); color: var(--accent); }

  .toast {
    position: fixed; bottom: 20px; right: 20px;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 10px 16px;
    font-family: 'DM Mono', monospace; font-size: 12px;
    box-shadow: 0 8px 32px rgba(0,0,0,.4);
    transform: translateY(60px); opacity: 0; transition: all .3s; z-index: 999;
  }
  .toast.show { transform: translateY(0); opacity: 1; }
  .toast.ok  { border-color: var(--green); color: var(--green); }
  .toast.err { border-color: var(--red);   color: var(--red); }

  ::-webkit-scrollbar { width: 5px; height: 5px; }
  ::-webkit-scrollbar-track { background: var(--bg); }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
</head>
<body>
<div class="wrap">

  <header>
    <div class="logo">// tool v3.0</div>
    <h1>Organizator<br><span>Fișiere</span></h1>
    <p class="subtitle">zero dependințe &middot; python built-in &middot; linux / mac / windows</p>
  </header>

  <!-- CONFIG -->
  <div id="config-section">

    <div class="card">
      <div class="card-title">01 — Căi</div>
      <div class="field">
        <label>Sursă</label>
        <input type="text" id="sursa" placeholder="/home/user/Downloads">
      </div>
      <div class="field">
        <label>Destinație</label>
        <input type="text" id="destinatie" placeholder="/home/user/Organizat">
      </div>
    </div>

    <div class="card">
      <div class="card-title">02 — Filtrare extensii</div>
      <div class="grid2">
        <div class="field">
          <label>Include doar (gol = toate)</label>
          <input type="text" id="ext_include" placeholder="jpg png pdf mp4">
        </div>
        <div class="field">
          <label>Exclude</label>
          <input type="text" id="ext_exclude" placeholder="tmp log ds_store">
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">03 — Operație</div>
      <div class="toggle-group">
        <button class="toggle-btn active" data-val="c" onclick="setMetoda(this)">Copiază</button>
        <button class="toggle-btn" data-val="m" onclick="setMetoda(this)">Mută</button>
      </div>
    </div>

    <div class="card">
      <div class="card-title">04 — Opțiuni avansate</div>
      <div class="switch-row">
        <div>
          <div class="switch-label">Șterge fișiere mici</div>
          <div class="switch-sub" id="sterge-sub">elimină fișierele sub
            <input type="number" id="limita_kb" value="50" min="1" max="99999"
              style="width:58px;background:var(--bg);border:1px solid var(--border);border-radius:5px;
                     padding:1px 6px;color:var(--accent);font-family:'DM Mono',monospace;font-size:11px;
                     outline:none;text-align:center;"
              onfocus="this.style.borderColor='var(--accent)'"
              onblur="this.style.borderColor='var(--border)'"
            > KB din sursă
          </div>
        </div>
        <label class="switch"><input type="checkbox" id="sterge_mici" onchange="toggleBackup()"><span class="slider"></span></label>
      </div>
      <div class="switch-row" id="backup-row" style="opacity:.3;pointer-events:none">
        <div>
          <div class="switch-label">Backup înainte de ștergere</div>
          <div class="switch-sub">salvează copie în _backup_sters/</div>
        </div>
        <label class="switch"><input type="checkbox" id="backup_mici"><span class="slider"></span></label>
      </div>
      <div class="switch-row">
        <div>
          <div class="switch-label">Omite duplicate</div>
          <div class="switch-sub">detectare prin hash MD5</div>
        </div>
        <label class="switch"><input type="checkbox" id="omit_duplicate"><span class="slider"></span></label>
      </div>
      <div class="switch-row">
        <div>
          <div class="switch-label">Dry-run</div>
          <div class="switch-sub">simulare completă, fără modificări reale</div>
        </div>
        <label class="switch"><input type="checkbox" id="dry_run"><span class="slider"></span></label>
      </div>
    </div>

    <button class="btn-run" id="btn-start" onclick="startOrganizare()">
      <span class="shimmer"></span>
      Pornește organizarea
    </button>

  </div>

  <!-- PROGRESS -->
  <div id="progress-section">
    <div class="card">
      <div class="card-title">Se procesează...</div>
      <div class="progress-bar-wrap">
        <div class="progress-bar-fill" id="prog-bar"></div>
      </div>
      <div class="progress-text" id="prog-text">0 / 0 fișiere</div>
      <div class="progress-file" id="prog-file">—</div>
    </div>
  </div>

  <!-- REZULTATE -->
  <div id="result-section">
    <div class="card">
      <div class="card-title">Rezultate</div>
      <div id="dry-badge" class="dry-badge" style="display:none">⚡ Dry-run — nicio modificare reală</div>
      <div class="stats-grid" id="stats-grid"></div>
      <div class="table-controls">
        <button class="filter-btn active" onclick="filtreaza('toate',this)">Toate</button>
        <button class="filter-btn" onclick="filtreaza('ok',this)">Procesate</button>
        <button class="filter-btn" onclick="filtreaza('sters',this)">Șterse</button>
        <button class="filter-btn" onclick="filtreaza('dup',this)">Duplicate</button>
        <button class="filter-btn" onclick="filtreaza('eroare',this)">Erori</button>
        <input class="search-input" type="text" placeholder="Caută fișier..." oninput="cauta(this.value)">
      </div>
      <div style="overflow-x:auto">
        <table>
          <thead>
            <tr>
              <th onclick="sorteaza('status')">Status <span class="sa">↕</span></th>
              <th onclick="sorteaza('fisier')">Fișier <span class="sa">↕</span></th>
              <th onclick="sorteaza('dest')">Destinație <span class="sa">↕</span></th>
              <th onclick="sorteaza('marime')">Mărime <span class="sa">↕</span></th>
              <th>Motiv</th>
            </tr>
          </thead>
          <tbody id="tbl"></tbody>
        </table>
      </div>
      <div class="pagination" id="pag"></div>
      <button class="btn-back" onclick="resetUI()">← Rulează din nou</button>
    </div>
  </div>

</div>
<div class="toast" id="toast"></div>

<script>
  let metoda = 'c';
  let allData = [], filteredData = [];
  let sortCol = '', sortAsc = true;
  let curPage = 1;
  const PER = 50;
  let activeFilter = 'toate', searchTerm = '';
  let pollIv = null;

  function setMetoda(btn) {
    document.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    metoda = btn.dataset.val;
  }

  function toggleBackup() {
    const on = document.getElementById('sterge_mici').checked;
    const row = document.getElementById('backup-row');
    row.style.opacity = on ? '1' : '.3';
    row.style.pointerEvents = on ? 'auto' : 'none';
  }

  function toast(msg, type='ok') {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.className = `toast show ${type}`;
    setTimeout(() => t.classList.remove('show'), 3000);
  }

  async function startOrganizare() {
    const sursa = document.getElementById('sursa').value.trim();
    const dest  = document.getElementById('destinatie').value.trim();
    if (!sursa || !dest) { toast('Completează sursa și destinația!', 'err'); return; }

    const cfg = {
      sursa, destinatie: dest, metoda,
      ext_include:    document.getElementById('ext_include').value.trim(),
      ext_exclude:    document.getElementById('ext_exclude').value.trim(),
      sterge_mici:    document.getElementById('sterge_mici').checked,
      limita_kb:      parseInt(document.getElementById('limita_kb').value) || 50,
      backup_mici:    document.getElementById('backup_mici').checked,
      omit_duplicate: document.getElementById('omit_duplicate').checked,
      dry_run:        document.getElementById('dry_run').checked,
    };

    document.getElementById('btn-start').disabled = true;
    document.getElementById('config-section').style.display = 'none';
    document.getElementById('progress-section').style.display = 'block';

    try {
      const r = await fetch('/start', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(cfg)
      });
      if (!r.ok) throw new Error(await r.text());
      pollIv = setInterval(pollProgress, 400);
    } catch(e) {
      toast('Eroare: ' + e.message, 'err');
      resetUI();
    }
  }

  async function pollProgress() {
    try {
      const d = await (await fetch('/progress')).json();
      if (d.total > 0) {
        const pct = Math.round(d.current / d.total * 100);
        document.getElementById('prog-bar').style.width = pct + '%';
        document.getElementById('prog-text').textContent = `${d.current} / ${d.total} fișiere (${pct}%)`;
        document.getElementById('prog-file').textContent = d.fisier || '—';
      }
      if (!d.running && d.result) {
        clearInterval(pollIv);
        showResult(d.result);
      }
    } catch(e) {}
  }

  function showResult(res) {
    document.getElementById('progress-section').style.display = 'none';
    document.getElementById('result-section').style.display = 'block';
    if (res.dry_run) document.getElementById('dry-badge').style.display = 'inline-block';
    const s = res.stats;
    document.getElementById('stats-grid').innerHTML = `
      <div class="stat-card green">  <div class="stat-num">${s.procesat}</div>  <div class="stat-label">${res.actiune}</div></div>
      <div class="stat-card yellow"> <div class="stat-num">${s.sters}</div>     <div class="stat-label">Șterse</div></div>
      <div class="stat-card purple"> <div class="stat-num">${s.duplicate}</div> <div class="stat-label">Duplicate</div></div>
      <div class="stat-card muted">  <div class="stat-num">${s.omis_ext}</div>  <div class="stat-label">Omise ext.</div></div>
      <div class="stat-card red">    <div class="stat-num">${s.erori}</div>     <div class="stat-label">Erori</div></div>
    `;
    allData = res.log;
    applyFilter();
  }

  function badge(status) {
    const m = {
      'copiat': ['b-ok','Copiat'], 'mutat': ['b-ok','Mutat'],
      'sters': ['b-st','Șters'], 'backup+sters': ['b-st','Backup+Șters'],
      'duplicat': ['b-dup','Duplicat'], 'omis-ext': ['b-dup','Omis ext.'],
      'dry-run': ['b-dry','Dry-run'], 'eroare': ['b-err','Eroare'],
    };
    const [cls, lbl] = m[status] || ['b-dup', status];
    return `<span class="badge ${cls}">${lbl}</span>`;
  }

  function applyFilter() {
    let data = [...allData];
    if (activeFilter !== 'toate') {
      const m = {
        'ok':     s => s==='copiat'||s==='mutat'||s==='dry-run',
        'sters':  s => s==='sters'||s==='backup+sters',
        'dup':    s => s==='duplicat'||s==='omis-ext',
        'eroare': s => s==='eroare',
      };
      if (m[activeFilter]) data = data.filter(r => m[activeFilter](r.status));
    }
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      data = data.filter(r => r.fisier.toLowerCase().includes(q) || r.dest.toLowerCase().includes(q));
    }
    if (sortCol) {
      data.sort((a, b) => {
        let va = a[sortCol]||'', vb = b[sortCol]||'';
        if (sortCol==='marime') { va=parseFloat(va); vb=parseFloat(vb); }
        return sortAsc ? (va>vb?1:-1) : (va<vb?1:-1);
      });
    }
    filteredData = data;
    curPage = 1;
    renderTable();
  }

  function renderTable() {
    const start = (curPage-1)*PER;
    document.getElementById('tbl').innerHTML = filteredData.slice(start, start+PER).map(r => `
      <tr>
        <td>${badge(r.status)}</td>
        <td class="fn" title="${r.fisier}">${r.fisier}</td>
        <td class="dp" title="${r.dest}">${r.dest||'—'}</td>
        <td class="sz">${r.marime}</td>
        <td style="font-size:11px;color:var(--muted)">${r.motiv||''}</td>
      </tr>`).join('');
    const pages = Math.ceil(filteredData.length/PER);
    document.getElementById('pag').innerHTML = pages<=1 ? '' :
      Array.from({length:pages},(_,i)=>i+1)
        .map(i=>`<button class="page-btn ${i===curPage?'active':''}" onclick="goPage(${i})">${i}</button>`)
        .join('');
  }

  function goPage(p) { curPage=p; renderTable(); }

  function filtreaza(f, btn) {
    activeFilter = f;
    document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    applyFilter();
  }

  function cauta(v) { searchTerm=v; applyFilter(); }

  function sorteaza(col) {
    if (sortCol===col) sortAsc=!sortAsc; else { sortCol=col; sortAsc=true; }
    document.querySelectorAll('thead th').forEach(th=>th.classList.remove('sorted'));
    const idx = ['status','fisier','dest','marime'].indexOf(col);
    if (idx>=0) {
      const th = document.querySelectorAll('thead th')[idx];
      th.classList.add('sorted');
      th.querySelector('.sa').textContent = sortAsc?'↑':'↓';
    }
    applyFilter();
  }

  function resetUI() {
    document.getElementById('config-section').style.display = 'block';
    document.getElementById('progress-section').style.display = 'none';
    document.getElementById('result-section').style.display = 'none';
    document.getElementById('btn-start').disabled = false;
    document.getElementById('dry-badge').style.display = 'none';
    document.getElementById('prog-bar').style.width = '0%';
    allData = []; filteredData = [];
  }
</script>
</body>
</html>
"""

# ─────────────────────────────────────────────────────────────
#  HTTP SERVER
# ─────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            self._send(200, 'text/html; charset=utf-8', HTML.encode())
        elif path == '/progress':
            data = {
                "running": state["running"],
                "current": state["progress"]["current"],
                "total":   state["progress"]["total"],
                "fisier":  state["progress"]["fisier"],
                "result":  state["result"],
            }
            self._send(200, 'application/json', json.dumps(data).encode())
        else:
            self._send(404, 'text/plain', b'Not found')

    def do_POST(self):
        if self.path == '/start':
            length = int(self.headers.get('Content-Length', 0))
            try:
                cfg = json.loads(self.rfile.read(length))
            except:
                self._send(400, 'text/plain', b'Bad JSON'); return

            if state["running"]:
                self._send(409, 'text/plain', b'Already running'); return

            state["running"]  = True
            state["result"]   = None
            state["progress"] = {"current": 0, "total": 0, "fisier": ""}

            def run():
                def cb(cur, tot, f):
                    state["progress"] = {"current": cur, "total": tot, "fisier": f}
                try:
                    state["result"] = organizeaza(cfg, cb)
                except Exception as e:
                    state["result"] = {"log": [], "stats": {}, "eroare": str(e)}
                finally:
                    state["running"] = False

            threading.Thread(target=run, daemon=True).start()
            self._send(200, 'application/json', b'{"ok":true}')
        else:
            self._send(404, 'text/plain', b'Not found')

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)


# ─────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    server = HTTPServer(('127.0.0.1', PORT), Handler)
    url    = f'http://127.0.0.1:{PORT}'
    print(f'\n  Organizator Fisiere')
    print(f'  ---------------------')
    print(f'  Deschide:  {url}')
    print(f'  Oprire:    Ctrl+C\n')
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n  Server oprit.')
