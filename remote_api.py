#!/usr/bin/env python3
import os, json, hashlib, zipfile, urllib.request, urllib.error, re, html
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path
TOKEN = os.environ.get("REMOTE_CONTROL_TOKEN", "")
APK = Path("/tmp/freefire-official.apk")
OFFICIAL = "https://ffodownload.freefiremobile.com/?lang=en"

class Handler(BaseHTTPRequestHandler):
    def reply(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        supplied = q.get("token", [""])[0]
        import hmac
        if not TOKEN or not hmac.compare_digest(supplied, TOKEN):
            return self.reply(403, {"ok": False, "error": "forbidden"})
        task = q.get("task", ["status"])[0]
        if task == "status":
            return self.reply(200, {"ok": True, "service": "REMOTE-LINUX remote task API", "apk_downloaded": APK.exists(), "apk_bytes": APK.stat().st_size if APK.exists() else 0, "tasks": ["download_freefire", "inspect_apk"]})
        if task == "download_freefire":
            try:
                req = urllib.request.Request(OFFICIAL, headers={"User-Agent":"Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=90) as response:
                    data = response.read(250 * 1024 * 1024 + 1)
                    final_url = response.geturl()
                if len(data) > 250 * 1024 * 1024:
                    return self.reply(413, {"ok":False,"error":"APK excede 250 MB"})
                if not data.startswith(b"PK"):
                    return self.reply(502, {"ok":False,"error":"A página oficial não retornou um arquivo APK ZIP", "final_url":final_url, "content_start":data[:100].decode("utf-8","replace")})
                APK.write_bytes(data)
                return self.reply(200, {"ok":True,"saved":str(APK),"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest(),"final_url":final_url})
            except Exception as e:
                return self.reply(502, {"ok":False,"error":str(e)})
        if task == "inspect_apk":
            if not APK.exists():
                return self.reply(404, {"ok":False,"error":"APK ainda não foi baixado; execute download_freefire"})
            try:
                with zipfile.ZipFile(APK) as z:
                    names = z.namelist()
                    interesting = [n for n in names if re.search(r'(fps|frame|config|device|quality|setting|global|version|manifest)', n, re.I)][:160]
                    dex = [n for n in names if re.fullmatch(r'classes(?:\d+)?\.dex', n)]
                    libs = [n for n in names if n.endswith(".so")]
                    hits = []
                    patterns = re.compile(rb'(?i)(fps|frame.?rate|refresh.?rate|90.?hz|60.?hz|target.?fps|frame.?limit)')
                    for n in names:
                        if n.endswith((".xml",".json",".ini",".cfg",".txt",".properties")) and z.getinfo(n).file_size < 2_000_000:
                            raw = z.read(n)
                            if patterns.search(raw):
                                for m in patterns.finditer(raw):
                                    hits.append({"file":n,"match":raw[max(0,m.start()-50):m.end()+70].decode("utf-8","replace")[:180]})
                                    if len(hits)>=80: break
                        if len(hits)>=80: break
                    return self.reply(200, {"ok":True,"apk_bytes":APK.stat().st_size,"sha256":hashlib.sha256(APK.read_bytes()).hexdigest(),"entry_count":len(names),"dex_files":dex,"native_libraries_count":len(libs),"native_libraries":libs[:100],"interesting_paths":interesting,"text_config_hits":hits,"note":"APK inspection only; binary AndroidManifest and compiled Unity/IL2CPP assets may require specialized decoding. No anti-cheat or signature bypass is performed."})
            except Exception as e:
                return self.reply(500, {"ok":False,"error":str(e)})
        return self.reply(400, {"ok":False,"error":"unknown task"})
    def log_message(self, fmt, *args):
        print("remote-api:", fmt % args, flush=True)

HTTPServer(("127.0.0.1", 8081), Handler).serve_forever()
