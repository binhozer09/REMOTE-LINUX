#!/usr/bin/env python3
import os
import json
import hashlib
import zipfile
import urllib.request
import re
import threading
import time
import shutil
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

def download_official_via_browser():
    """Use the official Garena download page exactly as a user would: open it and click its download button."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
    except Exception as exc:
        raise RuntimeError("Selenium/Chromium WebDriver não está instalado: " + str(exc))

    download_dir = Path("/tmp/freefire-official-browser")
    download_dir.mkdir(parents=True, exist_ok=True)
    for old in download_dir.iterdir():
        if old.is_file():
            old.unlink(missing_ok=True)

    options = Options()
    options.binary_location = shutil.which("chromium") or "/usr/bin/chromium"
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,900")
    options.add_experimental_option("prefs", {
        "download.default_directory": str(download_dir),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    })
    driver_path = shutil.which("chromedriver") or "/usr/bin/chromedriver"
    driver = None
    try:
        driver = webdriver.Chrome(service=Service(driver_path), options=options)
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": str(download_dir)
        })
        official_page = OFFICIAL.replace("lang=en", "lang=pt-br")
        driver.get(official_page)
        deadline = time.time() + 35
        while time.time() < deadline and driver.execute_script("return document.readyState") != "complete":
            time.sleep(0.5)
        time.sleep(5)

        clickable = driver.find_elements(By.CSS_SELECTOR, "a,button,[role='button'],img")
        selected = None
        labels = []
        for element in clickable:
            label = " ".join([
                element.text or "",
                element.get_attribute("aria-label") or "",
                element.get_attribute("alt") or "",
                element.get_attribute("title") or ""
            ]).strip()
            if label:
                labels.append(label[:80])
            if re.search(r"\b(baixar|download)\b", label, re.I):
                selected = element
                if element.tag_name.lower() == "img":
                    selected = element.find_element(By.XPATH, "..")
                break

        if selected is None:
            raise ValueError("Botão oficial de download não localizado. Elementos visíveis: " + repr(labels[:30]))

        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", selected)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", selected)

        deadline = time.time() + 180
        while time.time() < deadline:
            pending = list(download_dir.glob("*.crdownload")) + list(download_dir.glob("*.part"))
            files = [p for p in download_dir.iterdir() if p.is_file() and p not in pending]
            for candidate in files:
                if candidate.stat().st_size >= 1024 * 1024:
                    with candidate.open("rb") as stream:
                        magic = stream.read(2)
                    if magic == b"PK":
                        if candidate.stat().st_size > MAX_APK_BYTES:
                            raise ValueError("APK excede 250 MB")
                        candidate.replace(APK)
                        digest = hashlib.sha256(APK.read_bytes()).hexdigest()
                        return {
                            "saved": str(APK),
                            "bytes": APK.stat().st_size,
                            "sha256": digest,
                            "final_url": driver.current_url,
                            "source": "official Garena page button"
                        }
            time.sleep(2)

        raise TimeoutError("O botão oficial foi acionado, mas nenhum arquivo APK ZIP terminou de baixar. Página final: " + driver.current_url)
    finally:
        if driver is not None:
            driver.quit()


def download_official():
    cookie_jar = urllib.request.HTTPCookieProcessor()
    opener = urllib.request.build_opener(cookie_jar)
    page_req = urllib.request.Request(
        OFFICIAL,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,*/*"
        }
    )
    with opener.open(page_req, timeout=90) as response:
        page = response.read(5 * 1024 * 1024 + 1)
        page_url = response.geturl()
        content_type = response.headers.get("Content-Type", "")

    candidates = []
    api_reports = []
    languages = ["pt-br", "en", "hi", "id", "ru", "es", "th", "bn", "tr", "ur", "fr", "vn", "zh-tw"]
    for language in languages:
        api_url = urljoin(page_url, "/api/info?lang=" + language)
        try:
            api_req = urllib.request.Request(
                api_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Referer": page_url,
                    "Origin": "https://ffodownload.freefiremobile.com",
                    "X-Requested-With": "XMLHttpRequest"
                }
            )
            with opener.open(api_req, timeout=25) as api_response:
                api_payload = json.loads(api_response.read(2 * 1024 * 1024).decode("utf-8", "replace"))
            payload_data = api_payload.get("data", api_payload) if isinstance(api_payload, dict) else {}
            config = payload_data.get("config", {}) if isinstance(payload_data, dict) else {}
            apk_link = config.get("apk_link") if isinstance(config, dict) else None
            download_link = config.get("download_link") if isinstance(config, dict) else None
            api_reports.append({
                "lang": language,
                "is_ind": config.get("is_ind") if isinstance(config, dict) else None,
                "apk_link": apk_link,
                "download_link": download_link
            })
            if apk_link and apk_link not in candidates:
                candidates.append(apk_link)
        except Exception as exc:
            api_reports.append({"lang": language, "error": str(exc)})
    print("AUTO: resultados API oficial " + json.dumps(api_reports, ensure_ascii=False), flush=True)

    if page.startswith(b"PK"):
        candidates.insert(0, page_url)
    elif not candidates:
        source = page[:5 * 1024 * 1024].decode("utf-8", "replace")
        raw_links = re.findall(r'''(?:href|src|data-href|data-url)\s*=\s*["']([^"']+)["']''', source, re.I)
        raw_links += re.findall(r'''https?://[^"'\s<>]+''', source, re.I)
        allowed = ("freefiremobile.com", "garena.com", "akamaihd.net", "akamaized.net", "wildflamestudio.com")
        for raw in raw_links:
            absolute = urljoin(page_url, html.unescape(raw))
            parsed = urlparse(absolute)
            host = (parsed.hostname or "").lower()
            if host.endswith(allowed) and parsed.path.lower().endswith(".apk") and absolute not in candidates:
                candidates.append(absolute)
        if not candidates:
            print("AUTO: API oficial sem apk_link; tentando o botão de download no navegador oficial", flush=True)

    print("AUTO: links APK candidatos " + json.dumps(candidates[:10], ensure_ascii=False), flush=True)
    last_error = "nenhum link retornou APK ZIP"
    for target in candidates[:10]:
        temp = APK.with_suffix(".download")
        digest = hashlib.sha256()
        total = 0
        first = b""
        try:
            download_req = urllib.request.Request(
                target,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": page_url,
                    "Origin": "https://ffodownload.freefiremobile.com",
                    "Accept": "*/*"
                }
            )
            with opener.open(download_req, timeout=90) as response:
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
                last_error = target + " não retornou ZIP"
                continue
            temp.replace(APK)
            return {"saved": str(APK), "bytes": total, "sha256": digest.hexdigest(), "final_url": final_url}
        except Exception as exc:
            temp.unlink(missing_ok=True)
            last_error = target + " -> " + str(exc)
    try:
        return download_official_via_browser()
    except Exception as exc:
        last_error += "; tentativa pelo botão oficial no navegador falhou: " + str(exc)
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
