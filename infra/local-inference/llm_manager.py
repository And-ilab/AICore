"""Local LLM process manager: switch GGUF models under one OpenAI alias."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw) if raw else default


CATALOG_PATH = _env_path("CATALOG_PATH", HERE / "models.json")
STATE_PATH = _env_path("STATE_PATH", HERE / ".llm_manager_state.json")
MODELS_DIR = _env_path("MODELS_DIR", REPO / "models")
LLAMA_DIR = _env_path("LLAMA_DIR", MODELS_DIR / "llama.cpp")
GGUF_DIR = _env_path("GGUF_DIR", MODELS_DIR / "llm")
LLAMA_SERVER_PATH = os.environ.get("LLAMA_SERVER_PATH", "")

MANAGER_HOST = os.environ.get("LLM_MANAGER_HOST", "127.0.0.1")
MANAGER_PORT = int(os.environ.get("LLM_MANAGER_PORT", "8070"))
LLAMA_HOST = os.environ.get("LLAMA_HOST", "127.0.0.1")
LLAMA_PORT = int(os.environ.get("LLAMA_PORT", "8080"))
CTX = int(os.environ.get("LLM_CTX", "4096"))
THREADS = int(os.environ.get("LLM_THREADS") or os.cpu_count() or 4)
DEFAULT_MODEL_ID = os.environ.get("LLM_DEFAULT_MODEL_ID", "")

_lock = threading.Lock()
_process: subprocess.Popen[bytes] | None = None
_log_fh: Any = None
_active_id: str | None = None
_switching = False
_last_error: str | None = None


def _load_catalog() -> dict[str, Any]:
    with CATALOG_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if LLAMA_PORT:
        data["llama_port"] = LLAMA_PORT
    return data


def _find_llama_server() -> Path:
    if LLAMA_SERVER_PATH:
        path = Path(LLAMA_SERVER_PATH)
        if path.is_file():
            return path
        raise FileNotFoundError(f"LLAMA_SERVER_PATH not found: {path}")
    direct = LLAMA_DIR / "llama-server.exe"
    if direct.is_file():
        return direct
    unix = LLAMA_DIR / "llama-server"
    if unix.is_file():
        return unix
    matches = list(LLAMA_DIR.rglob("llama-server.exe")) + list(
        LLAMA_DIR.rglob("llama-server")
    )
    if not matches:
        raise FileNotFoundError(
            f"llama-server not found under {LLAMA_DIR}. "
            "Run download-models.sh / download-models.ps1 or set LLAMA_SERVER_PATH"
        )
    return matches[0]


def _model_by_id(catalog: dict[str, Any], model_id: str) -> dict[str, Any]:
    for item in catalog["models"]:
        if item["id"] == model_id:
            return item
    raise KeyError(model_id)


def _gguf_path(item: dict[str, Any]) -> Path:
    path = GGUF_DIR / item["gguf"]
    if not path.is_file():
        raise FileNotFoundError(f"GGUF missing: {path}")
    return path


def _save_state(model_id: str) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps({"active_model_id": model_id}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_state() -> str | None:
    if not STATE_PATH.is_file():
        return None
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = data.get("active_model_id")
    return value if isinstance(value, str) else None


def _llama_ready(port: int, timeout: float = 300.0) -> bool:
    """Wait until OpenAI /v1/models returns HTTP 200 (not 503 while loading)."""
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/v1/models"
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=3) as resp:
                if resp.status == 200:
                    # Ensure body looks like a model list, not an error page.
                    body = resp.read().decode("utf-8", errors="replace")
                    if '"data"' in body or '"models"' in body or '"id"' in body:
                        return True
        except Exception:
            # urllib raises HTTPError for 503 while the GGUF is still loading.
            pass
        if _process is not None and _process.poll() is not None:
            return False
        time.sleep(1.0)
    return False


def _kill_pid(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        try:
            os.kill(pid, 15)
        except OSError:
            pass
        time.sleep(0.3)
        try:
            os.kill(pid, 9)
        except OSError:
            pass


def _free_llama_port(port: int) -> None:
    """Best-effort stop of a foreign llama-server occupying the port."""
    if os.name == "nt":
        try:
            out = subprocess.check_output(
                ["netstat", "-ano"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.CalledProcessError):
            return
        needle = f":{port}"
        for line in out.splitlines():
            if needle not in line or "LISTENING" not in line:
                continue
            parts = line.split()
            if not parts:
                continue
            try:
                pid = int(parts[-1])
            except ValueError:
                continue
            if pid > 0:
                _kill_pid(pid)
        return
    try:
        out = subprocess.check_output(
            ["ss", "-lptn", f"sport = :{port}"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        try:
            out = subprocess.check_output(
                ["lsof", "-ti", f":{port}"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            for raw in out.split():
                try:
                    _kill_pid(int(raw))
                except ValueError:
                    continue
            return
        except (OSError, subprocess.CalledProcessError):
            return
    # ss output: users:(("llama-server",pid=123,fd=5))
    import re

    for match in re.finditer(r"pid=(\d+)", out):
        _kill_pid(int(match.group(1)))


def _stop_llama() -> None:
    global _process, _log_fh
    proc = _process
    _process = None
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
        except (OSError, ValueError):
            pass
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            _kill_pid(proc.pid)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
    if _log_fh is not None:
        try:
            _log_fh.close()
        except OSError:
            pass
        _log_fh = None


def _start_llama(model_id: str) -> None:
    global _process, _log_fh, _active_id, _last_error
    catalog = _load_catalog()
    item = _model_by_id(catalog, model_id)
    gguf = _gguf_path(item)
    alias = catalog.get("openai_alias") or "qwen2.5-1.5b-instruct"
    port = int(catalog.get("llama_port") or LLAMA_PORT or 8080)
    llama = _find_llama_server()
    if not llama.is_file():
        raise FileNotFoundError(f"llama-server binary missing: {llama}")
    if not os.access(llama, os.X_OK):
        raise PermissionError(f"llama-server is not executable: {llama}")

    _stop_llama()
    _free_llama_port(port)
    time.sleep(0.4)
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

    log_path = STATE_PATH.parent / "llama-server.log"
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _log_fh = log_path.open("ab", buffering=0)

    cmd = [
        str(llama),
        "-m",
        str(gguf),
        "--host",
        LLAMA_HOST,
        "--port",
        str(port),
        "-c",
        str(CTX),
        "-t",
        str(THREADS),
        "--alias",
        alias,
    ]
    env = os.environ.copy()
    # Official image libs live next to the binary.
    lib_dirs = [
        str(llama.parent),
        str(llama.parent / "lib"),
        "/opt/llama",
        "/opt/llama/lib",
    ]
    existing = [path for path in lib_dirs if Path(path).is_dir()]
    if existing:
        env["LD_LIBRARY_PATH"] = ":".join(
            existing + ([env["LD_LIBRARY_PATH"]] if env.get("LD_LIBRARY_PATH") else [])
        )

    print(f"Starting llama-server: {' '.join(cmd)}", flush=True)
    _process = subprocess.Popen(
        cmd,
        cwd=str(MODELS_DIR),
        stdout=_log_fh,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
        env=env,
    )
    if not _llama_ready(port):
        code = _process.poll()
        detail = ""
        try:
            _log_fh.flush()
            if log_path.is_file():
                detail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
        except OSError:
            detail = ""
        _stop_llama()
        _last_error = (
            f"llama-server failed to become ready (exit={code}). "
            f"log_tail={detail!r}"
        )
        raise RuntimeError(_last_error)
    _active_id = model_id
    _last_error = None
    _save_state(model_id)


def switch_model(model_id: str) -> dict[str, Any]:
    global _switching, _last_error
    with _lock:
        _switching = True
        try:
            _start_llama(model_id)
            return status_payload()
        except Exception as exc:  # noqa: BLE001
            _last_error = str(exc)
            raise
        finally:
            _switching = False


def status_payload() -> dict[str, Any]:
    catalog = _load_catalog()
    available: list[dict[str, Any]] = []
    for item in catalog["models"]:
        gguf = GGUF_DIR / item["gguf"]
        available.append(
            {
                "id": item["id"],
                "label": item["label"],
                "description": item.get("description", ""),
                "available": gguf.is_file(),
                "gguf": item["gguf"],
            }
        )
    running = _process is not None and _process.poll() is None
    port = int(catalog.get("llama_port") or LLAMA_PORT or 8080)
    ready = bool(_active_id) and running and not _switching
    return {
        "active_model_id": _active_id,
        "switching": _switching,
        "llama_running": running,
        "ready": ready,
        "openai_alias": catalog.get("openai_alias"),
        "openai_base_url": f"http://{LLAMA_HOST}:{port}/v1",
        "models": available,
        "last_error": _last_error,
    }


def ensure_started() -> None:
    catalog = _load_catalog()
    preferred = (
        _read_state()
        or DEFAULT_MODEL_ID
        or catalog.get("default_model_id")
        or "qwen2.5-1.5b-instruct"
    )
    models = catalog["models"]
    ordered_ids = [preferred] + [m["id"] for m in models]
    seen: set[str] = set()
    last_exc: Exception | None = None
    for model_id in ordered_ids:
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        try:
            item = _model_by_id(catalog, model_id)
            if not (GGUF_DIR / item["gguf"]).is_file():
                continue
            switch_model(model_id)
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    if last_exc:
        raise last_exc
    raise FileNotFoundError(
        f"No local GGUF models found under {GGUF_DIR}. Run download-models.sh"
    )


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        if code != 204:
            self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._json(204, {})

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/health", "/v1/health"):
            self._json(200, {"status": "ok", **status_payload()})
            return
        if self.path in ("/models", "/v1/models", "/"):
            self._json(200, status_payload())
            return
        self._json(404, {"error": "not_found"})

    def do_PUT(self) -> None:  # noqa: N802
        if self.path not in ("/models", "/v1/models", "/active"):
            self._json(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid_json"})
            return
        model_id = body.get("model_id") or body.get("id")
        if not isinstance(model_id, str) or not model_id.strip():
            self._json(400, {"error": "model_id_required"})
            return
        try:
            payload = switch_model(model_id.strip())
        except KeyError:
            self._json(404, {"error": "unknown_model", "model_id": model_id})
            return
        except FileNotFoundError as exc:
            self._json(404, {"error": "model_file_missing", "details": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001
            self._json(500, {"error": "switch_failed", "details": str(exc)})
            return
        self._json(200, payload)


def _autostart_worker() -> None:
    try:
        ensure_started()
        print(f"Active model: {_active_id}", flush=True)
    except Exception as exc:  # noqa: BLE001
        global _last_error
        _last_error = str(exc)
        print(f"WARN: could not autostart LLM: {exc}", flush=True)


def main() -> None:
    print(
        f"LLM manager on http://{MANAGER_HOST}:{MANAGER_PORT} "
        f"(llama {LLAMA_HOST}:{LLAMA_PORT})",
        flush=True,
    )
    print(f"GGUF_DIR={GGUF_DIR} CATALOG={CATALOG_PATH}", flush=True)

    # Bind HTTP first so healthchecks work while the GGUF is loading.
    server = ThreadingHTTPServer((MANAGER_HOST, MANAGER_PORT), Handler)
    starter = threading.Thread(target=_autostart_worker, name="llm-autostart", daemon=True)
    starter.start()
    print("HTTP manager listening; autostarting llama in background…", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _stop_llama()
        server.server_close()


if __name__ == "__main__":
    main()
