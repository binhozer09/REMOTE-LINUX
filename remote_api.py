#!/usr/bin/env python3
import os
import json
import hashlib
import zipfile
import urllib.request
import re
import threading
import time
import html
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs, urljoin
from pathlib import Path

TOKEN = os.environ.get("REMOTE_CONTROL_TOKEN", "")
APK = Path("/tmp/freefire-official.apk")
OFFICIAL = "https://ffodownload.freefiremobile.com/?lang=en"
MAX_APK_BYTES = 250 * 1024 * 1024
AUTO_ANALYZE = os.environ.get("AUTO_ANALYZE_FREEFIRE", "0") == "1"
STATE = {"auto_task": "waiting", "error": None}

def download_official():
    req = urllib.request.Request(
        OFFICIAL,
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36", "Accept": "text/html,application/xhtml+xml,*/*"}
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        page = response.read(5 * 1024 * 1024 + 1)
        page_url = response.geturl()
        content_type = response.headers.get("Content-Type", "")
    if page.startswith(b"PK"):
        candidates = [page_url]
    else:
        source = page[:5 * 1024 * 1024].decode("utf-8", "replace")
        raw_links = re.findall(r'''(?:href|src|data-href|data-url)\s*=\s*["']([^"']+)["']''', source, re.I)
        raw_links += re.findall(r'''https?://[^"'\s<>]+''', source, re.I)
        candidates = []
        allowed = ("freefiremobile.com", "garena.com", "akamaihd.net", "akamaized.net", "wildflamestudio.com")
        def add_candidate(raw, base):
            absolute = urljoin(base, html.unescape(raw))
            host = (urlparse(absolute).hostname or "").lower()
            if host.endswith(allowed) and absolute not in candidates and re.search(r"\.apk(?:$|[?#])|download|package", absolute, re.I):
                candidates.append(absolute)
        for raw in raw_links:
            add_candidate(raw, page_url)

        script_urls = [urljoin(page_url, x) for x in re.findall(r'''<script[^>]+src=["']([^"']+)["']''', source, re.I)]
        script_findings = []
        for script_url in script_urls[:8]:
            try:
                script_req = urllib.request.Request(script_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(script_req, timeout=30) as script_response:
                    js = script_response.read(8 * 1024 * 1024).decode("utf-8", "replace")
                strings = re.findall(r'''["']([^"']*(?:\.apk|download|package|android)[^"']*)["']''', js, re.I)
                for value in strings[:100]:
                    add_candidate(value, script_url)
                for match in list(re.finditer(r"(?i)(apk|download|package|android)", js))[:25]:
                    script_findings.append({"script": script_url, "match": js[max(0, match.start()-100):match.end()+160]})
            except Exception as exc:
                script_findings.append({"script": script_url, "error": str(exc)})

        if not candidates:
            raise ValueError(
                "A página oficial retornou HTML, não o APK. "
                + "Content-Type=" + content_type
                + "; links=" + json.dumps(raw_links[:30], ensure_ascii=False)
                + "; scripts=" + json.dumps(script_findings[:30], ensure_ascii=False)
                + "; trecho=" + source[:400].replace("\n", " ")
            )

    last_error = "nenhum link retornou APK ZIP"
    for target in candidates[:10]:
        temp = APK.with_suffix(".download")
        digest = hashlib.sha256()
        total = 0
        first = b""
        try:
            download_req = urllib.request.Request(target, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(download_req, timeout=90) as response:
                final_url = response.geturl()
                with temp.open("wb") as out:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        if not first:
                            first = chunk[:2]
                        total += len(chunk)
                        if total > MAX_APK_BYTES:
                            raise ValueError("APK excede 250 MB")
                        digest.update(chunk)
                        out.write(chunk)
            if first != b"PK":
                temp.unlink(missing_ok=True)
                last_error = "link não retornou ZIP: " + final_url
                continue
            temp.replace(APK)
            return {"saved": str(APK), "bytes": total, "sha256": digest.hexdigest(), "final_url": final_url}
        except Exception as exc:
            temp.unlink(missing_ok=True)
            last_error = str(exc)
    raise ValueError("Não consegui obter o APK pelos links oficiais: " + last_error)

def inspect_apk():
    if not APK.exists():
        raise FileNotFoundError("APK ainda não foi baixado")
    with zipfile.ZipFile(APK) as z:
        names = z.namelist()
        interesting = [n for n in names if re.search(r"(fps|frame|config|device|quality|setting|global|version|manifest)", n, re.I)][:160]
        dex = [n for n in names if re.fullmatch(r"classes(?:\d+)?\.dex", n)]
        libs = [n for n in names if n.endswith(".so")]
        hits = []
        patterns = re.compile(rb"(?i)(fps|frame.?rate|refresh.?rate|90.?hz|60.?hz|target.?fps|frame.?limit)")
        for n in names:
            if n.endswith((".xml", ".json", ".ini", ".cfg", ".txt", ".properties")) and z.getinfo(n).file_size < 2_000_000:
                raw = z.read(n)
                for m in patterns.finditer(raw):
                    hits.append({"file": n, "match": raw[max(0, m.start()-50):m.end()+70].decode("utf-8", "replace")[:180]})
                    if len(hits) >= 80:
                        break
            if len(hits) >= 80:
                break
        return {
            "ok": True,
            "apk_bytes": APK.stat().st_size,
            "sha256": hashlib.sha256(APK.read_bytes()).hexdigest(),
            "entry_count": len(names),
            "dex_files": dex,
            "native_libraries_count": len(libs),
            "native_libraries": libs[:100],
            "interesting_paths": interesting,
            "text_config_hits": hits,
            "note": "APK inspection only; binary AndroidManifest and compiled Unity/IL2CPP assets may require specialized decoding. No anti-cheat or signature bypass is performed."
        }

def automatic_analysis():
    try:
        STATE["auto_task"] = "downloading"
        print("AUTO: iniciando download do APK oficial do Free Fire", flush=True)
        downloaded = download_official()
        print("AUTO: download concluído " + json.dumps(downloaded, ensure_ascii=False), flush=True)
        STATE["auto_task"] = "inspecting"
        report = inspect_apk()
        print("AUTO: inspeção inicial " + json.dumps(report, ensure_ascii=False), flush=True)
        STATE["auto_task"] = "completed"
    except Exception as exc:
        STATE["auto_task"] = "failed"
        STATE["error"] = str(exc)
        print("AUTO: falha " + repr(exc), flush=True)

class Handler(BaseHTTPRequestHandler):
    def reply(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if urlparse(self.path).path == "/health":
            return self.reply(200, {
                "ok": True,
                "service": "REMOTE-LINUX remote task API",
                "apk_downloaded": APK.exists(),
                "apk_bytes": APK.stat().st_size if APK.exists() else 0,
                "auto_task": STATE["auto_task"]
            })
        return self.reply(405, {"ok": False, "error": "method not allowed"})

    def do_GET(self):
        if urlparse(self.path).path == "/health":
            return self.reply(200, {
                "ok": True,
                "service": "REMOTE-LINUX remote task API",
                "apk_downloaded": APK.exists(),
                "apk_bytes": APK.stat().st_size if APK.exists() else 0,
                "auto_task": STATE["auto_task"]
            })
        q = parse_qs(urlparse(self.path).query)
        supplied = q.get("token", [""])[0]
        import hmac
        if not TOKEN or not hmac.compare_digest(supplied, TOKEN):
            return self.reply(403, {"ok": False, "error": "forbidden"})
        task = q.get("task", ["status"])[0]
        if task == "status":
            return self.reply(200, {
                "ok": True,
                "service": "REMOTE-LINUX remote task API",
                "apk_downloaded": APK.exists(),
                "apk_bytes": APK.stat().st_size if APK.exists() else 0,
                "auto_task": STATE["auto_task"],
                "auto_error": STATE["error"],
                "tasks": ["download_freefire", "inspect_apk"]
            })
        if task == "download_freefire":
            try:
                return self.reply(200, {"ok": True, **download_official()})
            except Exception as exc:
                return self.reply(502, {"ok": False, "error": str(exc)})
        if task == "inspect_apk":
            try:
                return self.reply(200, inspect_apk())
            except FileNotFoundError as exc:
                return self.reply(404, {"ok": False, "error": str(exc)})
            except Exception as exc:
                return self.reply(500, {"ok": False, "error": str(exc)})
        return self.reply(400, {"ok": False, "error": "unknown task"})

    def log_message(self, fmt, *args):
        print("remote-api:", fmt % args, flush=True)

server = HTTPServer(("127.0.0.1", 8081), Handler)
if AUTO_ANALYZE:
    threading.Thread(target=automatic_analysis, daemon=True).start()
print("REMOTE API escutando em 127.0.0.1:8081", flush=True)
server.serve_forever()
