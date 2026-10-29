from flask import Flask, request, render_template_string, send_file
import yt_dlp
import os
import re
import tempfile
import threading
import uuid
from pathlib import Path

app = Flask(__name__)
JOBS = {}
LOCK = threading.Lock()
DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "my_mp4_converter"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

PAGE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>My MP4 Converter</title>
<style>
:root{color-scheme:dark;--bg:#080f1b;--panel:#111d2c;--line:#26364b;--blue:#2583ff;--muted:#a8b8ce;--green:#36e0b0}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at top,#14243b 0,#080f1b 60%);font:16px system-ui,Segoe UI,sans-serif;color:#eef5ff;min-height:100vh}
header{padding:20px 5vw;border-bottom:1px solid var(--line);font-weight:800;font-size:22px}header span{color:#56a2ff}
main{max-width:850px;margin:48px auto;padding:0 18px}.intro{text-align:center;margin-bottom:28px}.logo{display:inline-grid;place-items:center;background:#ff343f;width:56px;height:44px;border-radius:12px;margin-bottom:12px;font-size:25px}.intro h1{font-size:clamp(28px,4vw,42px);margin:8px 0}.intro p{color:var(--muted);margin:8px 0}.safe{color:var(--green);font-size:14px}
.card{background:rgba(17,29,44,.94);border:1px solid var(--line);border-radius:18px;padding:26px;box-shadow:0 18px 55px #0004}
label{display:block;font-weight:700;margin:4px 0 10px}.urlrow{display:flex;gap:8px}input[type=url]{min-width:0;flex:1;background:#0b1523;border:1px solid #334760;border-radius:10px;padding:15px;color:white;font:inherit}select{width:100%;background:#0b1523;border:1px solid #334760;border-radius:10px;padding:13px;color:white;font:inherit}
button{border:0;border-radius:10px;background:var(--blue);color:white;font-weight:750;font-size:16px;padding:14px 18px;cursor:pointer}button:hover{filter:brightness(1.1)}button:disabled{opacity:.6;cursor:wait}.field{margin:22px 0}.quality{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}.q{background:#0b1523;border:1px solid #334760;border-radius:10px;padding:13px;text-align:center}.q input{accent-color:#2583ff}.q label{margin:0;cursor:pointer}.submit{width:100%;margin-top:4px}.note{font-size:13px;color:var(--muted);line-height:1.6;margin-top:18px}.status{margin-top:18px;padding:14px;border-radius:10px;background:#0b1523;border:1px solid var(--line);white-space:pre-wrap;overflow-wrap:anywhere}.features{display:flex;justify-content:center;gap:24px;flex-wrap:wrap;color:var(--muted);font-size:14px;margin:24px 0}.small{font-size:12px;color:var(--muted);text-align:center;margin-top:24px}
@media(max-width:580px){.card{padding:18px}.urlrow{flex-direction:column}.quality{grid-template-columns:repeat(2,1fr)}main{margin-top:28px}}
</style>
</head>
<body>
<header>▶ My <span>MP4 Converter</span></header>
<main>
<div class="intro"><div class="logo">▶</div><h1>Video to MP4 Converter</h1><p>Paste a video link, choose quality, and save a file.</p><div class="safe">● Runs on your own computer · No ads · No account</div></div>
<section class="card">
<form id="form">
<div class="field"><label for="url">Video URL</label><div class="urlrow"><input id="url" name="url" type="url" placeholder="https://…" required autocomplete="url"><button type="button" id="paste">Paste</button></div></div>
<div class="field"><label for="quality">Maximum video quality</label><select id="quality" name="quality"><option value="best">Best available</option><option value="2160">2160p (4K)</option><option value="1080">1080p (Full HD)</option><option value="720" selected>720p (HD)</option><option value="480">480p</option><option value="360">360p</option></select></div>
<button class="submit" id="submit" type="submit">⬇ Download MP4</button>
</form>
<div class="status" id="status" hidden></div>
<p class="note">Only download videos you own or have permission to save, and follow the source site's terms. Quality depends on the original video. This local app does not upload your URL to a separate converter website. Downloads are saved to your Downloads folder.</p>
</section>
<div class="features"><span>✓ Free</span><span>✓ No ads</span><span>✓ Quality options</span><span>✓ Local interface</span></div>
<div class="small">Personal-use starter project · Powered by yt-dlp</div>
</main>
<script>
const form=document.querySelector('#form'), statusBox=document.querySelector('#status'), submit=document.querySelector('#submit');
document.querySelector('#paste').addEventListener('click',async()=>{try{document.querySelector('#url').value=await navigator.clipboard.readText()}catch(e){statusBox.hidden=false;statusBox.textContent='Clipboard access was blocked. Click the URL box and press Ctrl+V.'}});
form.addEventListener('submit',async e=>{
 e.preventDefault(); submit.disabled=true; submit.textContent='Downloading…'; statusBox.hidden=false; statusBox.textContent='Starting download. Keep this page open.';
 try{
  const response=await fetch('/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:document.querySelector('#url').value,quality:document.querySelector('#quality').value})});
  const data=await response.json(); if(!response.ok) throw new Error(data.error||'Download failed.');
  statusBox.textContent='Download ready. Your browser will save the file.';
  const a=document.createElement('a');a.href=data.file;a.download='';document.body.appendChild(a);a.click();a.remove();
 }catch(err){statusBox.textContent='Could not download: '+err.message+'\nCheck the link and make sure yt-dlp/FFmpeg are installed and up to date.'}
 finally{submit.disabled=false;submit.textContent='⬇ Download MP4'}
});
</script>
</body></html>
"""

def safe_filename(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return (name[:120] or "video") + ".mp4"

@app.get("/")
def home():
    return render_template_string(PAGE)

@app.post("/download")
def download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    quality = data.get("quality", "best")
    if not re.match(r"^https?://", url, re.I):
        return {"error": "Please enter a valid http or https video URL."}, 400
    # Restrict to YouTube domains in this starter app to reduce misuse.
    if not re.search(r"(^|\.)((www|m)\.)?(youtube\.com|youtu\.be)(/|$)", re.sub(r"^https?://", "", url, flags=re.I), re.I):
        return {"error": "This starter version accepts YouTube URLs only."}, 400
    if quality not in {"best", "2160", "1080", "720", "480", "360"}:
        return {"error": "Invalid quality selection."}, 400

    job_id = uuid.uuid4().hex
    output_template = str(DOWNLOAD_DIR / (job_id + ".%(ext)s"))
    if quality == "best":
        fmt = "bestvideo*+bestaudio/best"
    else:
        h = int(quality)
        fmt = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"
    opts = {
        "format": fmt,
        "outtmpl": output_template,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        # Find the produced file; yt-dlp may merge to mp4 or use a source extension.
        candidates = list(DOWNLOAD_DIR.glob(job_id + ".*"))
        candidates = [p for p in candidates if p.is_file() and p.suffix.lower() not in {".part", ".ytdl", ".json"}]
        if not candidates:
            return {"error": "No output file was produced. Try updating yt-dlp and FFmpeg."}, 500
        file_path = next((p for p in candidates if p.suffix.lower() == ".mp4"), candidates[0])
        with LOCK:
            JOBS[job_id] = {"path": str(file_path), "name": safe_filename(info.get("title", "video"))}
        return {"file": f"/file/{job_id}"}
    except Exception as exc:
        # Keep the message useful without dumping tracebacks to the browser.
        return {"error": str(exc)[:500]}, 500

@app.get("/file/<job_id>")
def get_file(job_id):
    with LOCK:
        item = JOBS.get(job_id)
    if not item or not os.path.isfile(item["path"]):
        return "File not found or expired. Please try again.", 404
    return send_file(item["path"], as_attachment=True, download_name=item["name"])

if __name__ == "__main__":
    print("Open http://127.0.0.1:5000 in your browser. Press Ctrl+C to stop.")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")), debug=False)
