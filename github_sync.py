"""GitHub 同步模块 — 使用 REST API 读写仓库文件"""
import os, json, base64, hashlib, time
from pathlib import Path
import requests

DATA_DIR = Path(__file__).parent / "data"
TOKEN_FILE = DATA_DIR / "github_token.json"
SYNC_MANIFEST = DATA_DIR / "github_sync.json"

REPO_OWNER = "zhutie-zhang"
REPO_NAME = "zhang-GYL"
API_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"


def _get_token():
    if TOKEN_FILE.exists():
        try:
            data = json.loads(TOKEN_FILE.read_text("utf-8"))
            return data.get("token", "")
        except:
            pass
    return ""


def _headers():
    token = _get_token()
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }


def _load_manifest():
    if SYNC_MANIFEST.exists():
        try:
            return json.loads(SYNC_MANIFEST.read_text("utf-8"))
        except:
            pass
    return {"files": {}}


def _save_manifest(manifest):
    SYNC_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")


def _file_sha(content_bytes):
    return hashlib.sha1(content_bytes).hexdigest()


def _local_to_repo_path(local_path):
    """Convert local path to repo-relative path."""
    p = Path(local_path)
    data_dir = DATA_DIR.resolve()
    try:
        rel = p.resolve().relative_to(data_dir)
        return str(rel).replace("\\", "/")
    except ValueError:
        return p.name


def _repo_to_local_path(repo_path):
    """Convert repo-relative path to local path."""
    return DATA_DIR / repo_path


def list_remote_files():
    """List all files in the repo root (recursive)."""
    token = _get_token()
    if not token:
        return []
    files = []
    _list_recursive("", files)
    return files


def _list_recursive(path, results):
    url = f"{API_BASE}/contents/{path}" if path else f"{API_BASE}/contents/"
    resp = requests.get(url, headers=_headers(), timeout=15)
    if resp.status_code != 200:
        return
    items = resp.json()
    if not isinstance(items, list):
        return
    for item in items:
        if item["type"] == "file":
            results.append({
                "path": item["path"],
                "sha": item["sha"],
                "size": item.get("size", 0),
            })
        elif item["type"] == "dir":
            _list_recursive(item["path"], results)


def download_file(repo_path):
    """Download a single file from the repo."""
    url = f"{API_BASE}/contents/{repo_path}"
    resp = requests.get(url, headers=_headers(), timeout=15)
    if resp.status_code != 200:
        return None
    data = resp.json()
    if "content" not in data:
        return None
    content = base64.b64decode(data["content"])
    local_path = _repo_to_local_path(repo_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(content)
    return {"sha": data["sha"], "size": len(content)}


def upload_file(repo_path, content_bytes, message=None):
    """Create or update a file in the repo."""
    token = _get_token()
    if not token:
        return {"error": "no token"}
    manifest = _load_manifest()
    sha = manifest["files"].get(repo_path, {}).get("sha")
    if not sha:
        existing = _get_file_sha_remote(repo_path)
        if existing:
            sha = existing
    url = f"{API_BASE}/contents/{repo_path}"
    body = {
        "message": message or f"update {repo_path}",
        "content": base64.b64encode(content_bytes).decode("ascii"),
    }
    if sha:
        body["sha"] = sha
    resp = requests.put(url, headers=_headers(), json=body, timeout=30)
    if resp.status_code in (200, 201):
        data = resp.json()
        manifest["files"][repo_path] = {
            "sha": data.get("content", {}).get("sha", ""),
            "size": len(content_bytes),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        _save_manifest(manifest)
        return {"ok": True, "sha": data.get("content", {}).get("sha", "")}
    return {"error": resp.text[:200]}


def _get_file_sha_remote(repo_path):
    url = f"{API_BASE}/contents/{repo_path}"
    resp = requests.get(url, headers=_headers(), timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        return data.get("sha")
    return None


def pull_all():
    """Pull all files from repo to local data directory."""
    token = _get_token()
    if not token:
        return {"ok": False, "error": "no token"}
    remote_files = list_remote_files()
    if not remote_files:
        return {"ok": True, "downloaded": 0, "message": "repo empty or no files"}
    manifest = _load_manifest()
    downloaded = 0
    skipped = 0
    for rf in remote_files:
        repo_path = rf["path"]
        local_sha = manifest["files"].get(repo_path, {}).get("sha")
        if local_sha == rf["sha"]:
            skipped += 1
            continue
        result = download_file(repo_path)
        if result:
            manifest["files"][repo_path] = {
                "sha": result["sha"],
                "size": result["size"],
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            downloaded += 1
    _save_manifest(manifest)
    return {"ok": True, "downloaded": downloaded, "skipped": skipped, "total": len(remote_files)}


def push_all():
    """Push all local data files to the repo."""
    token = _get_token()
    if not token:
        return {"ok": False, "error": "no token"}
    pushed = 0
    errors = []
    SKIP_FILES = {"github_token.json", "github_sync.json", "__pycache__"}
    for f in DATA_DIR.iterdir():
        if f.name in SKIP_FILES:
            continue
        if f.is_file() and f.suffix in (".json", ".csv", ".xlsx", ".xls"):
            repo_path = f.name
            content = f.read_bytes()
            result = upload_file(repo_path, content, f"sync {f.name}")
            if result.get("ok"):
                pushed += 1
            else:
                errors.append(f"{f.name}: {result.get('error', 'unknown')}")
    return {"ok": not errors, "pushed": pushed, "errors": errors}


def push_file(local_path):
    """Push a single local file to the repo."""
    p = Path(local_path)
    if not p.exists():
        return {"error": "file not found"}
    repo_path = p.name
    content = p.read_bytes()
    return upload_file(repo_path, content, f"upload {p.name}")
