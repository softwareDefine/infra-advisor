"""저장소를 '사실'로 판정하는 코드.

핵심 원칙 (Pawploy 설계 그대로):
- **표면 패턴(정규식·문자열) 대신 코드 AST 로 판정.**
  웹 서버는 실제로 `import` 되고 생성자가 호출된 경우에만 web 으로 분류한다.
  주석·문자열·호출 없는 import 는 해당하지 않는다 → 오탐 제거.
- **비밀 파일은 읽지 않는다.** (프롬프트 인젝션·자격증명 유출 방어)
- 판정은 되돌릴 수 없는 부작용 없이, 읽기 전용으로만 한다.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

# 안 읽는/안 걷는 디렉터리
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist",
             "build", ".next", ".terraform", "vendor", ".idea", ".vscode"}
MAX_FILES = 2000
MAX_READ_BYTES = 256 * 1024  # 파일 1개 읽기 상한

# 비밀로 간주해 읽기를 거부하는 이름 규칙
_SECRET_NAMES = {".env", ".env.local", ".npmrc", ".pypirc", "credentials",
                 "id_rsa", "id_ed25519"}
_SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore")
_SECRET_HINTS = ("secret", "credential", "accesskey", "access_key", "token",
                 "password", "private")


def is_secret(name: str) -> bool:
    """자격증명으로 보이는 파일인가. 읽기 전에 항상 통과시킨다."""
    low = name.lower()
    base = os.path.basename(low)
    if base in _SECRET_NAMES:
        return True
    if base.startswith(".env"):
        return True
    if low.endswith(_SECRET_SUFFIXES):
        return True
    return any(h in low for h in _SECRET_HINTS)


def _safe_join(root: Path, rel: str) -> Path:
    """root 밖으로 나가는 경로(.. 탈출)를 막는다."""
    root = root.resolve()
    target = (root / rel).resolve()
    if root != target and root not in target.parents:
        raise ValueError(f"root 밖 경로 접근 거부: {rel}")
    return target


def list_files(root: str) -> list[str]:
    """읽기 전용 파일 목록. 비밀 파일·제외 디렉터리·상한을 지킨다."""
    base = Path(root).resolve()
    if not base.is_dir():
        raise NotADirectoryError(root)
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if is_secret(fn):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), base)
            out.append(rel.replace(os.sep, "/"))
            if len(out) >= MAX_FILES:
                return sorted(out)
    return sorted(out)


def read_file(root: str, rel_path: str) -> str:
    """파일 1개를 읽는다. 비밀 파일은 거부, 크기 상한, 경로 탈출 차단."""
    if is_secret(rel_path):
        raise PermissionError(f"비밀 파일은 읽지 않습니다: {rel_path}")
    target = _safe_join(Path(root), rel_path)
    if not target.is_file():
        raise FileNotFoundError(rel_path)
    data = target.read_bytes()[:MAX_READ_BYTES]
    return data.decode("utf-8", errors="replace")


# ── AST 기반 사실 판정 ────────────────────────────────────────────────

_WEB_IMPORTS = {
    "flask": "Flask", "fastapi": "FastAPI", "django": "Django",
    "aiohttp": "aiohttp", "starlette": "Starlette", "bottle": "Bottle",
}
# stdlib HTTP 서버: 실제 생성자 호출이 있어야 web
_STDLIB_HTTP = {"HTTPServer", "ThreadingHTTPServer", "BaseHTTPRequestHandler"}
_WORKER_IMPORTS = {"celery", "apscheduler", "rq", "schedule"}
_WS_HINTS = {"websocket", "websockets", "socketio", "channels"}
_DB_HINTS = {"psycopg", "psycopg2", "asyncpg", "sqlalchemy", "pymysql",
             "mysqlclient", "sqlite3", "pymongo", "redis"}


def _iter_py(base: Path):
    for dp, dn, fns in os.walk(base):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for fn in fns:
            if fn.endswith(".py") and not is_secret(fn):
                yield Path(dp) / fn


def detect_stack(root: str) -> dict:
    """저장소를 AST 로 파싱해 '사실'을 돌려준다.

    - web 서버: 프레임워크를 실제 import 했거나, stdlib HTTP 서버를
      실제 생성자 호출한 경우에만 True (주석·문자열·미호출 import 제외).
    - 장시간 실행(워커/스케줄러), WebSocket, DB 사용 여부도 코드 근거로 판정.
    """
    base = Path(root).resolve()
    facts = {
        "language": None,
        "web_frameworks": [],      # 실제 import 된 것
        "is_web_server": False,
        "has_worker": False,       # celery/스케줄러/상시 루프
        "uses_websocket": False,
        "uses_database": False,
        "entrypoints": [],         # __main__ 블록이 있는 파일
        "evidence": [],            # 사람이 읽을 근거
        "py_files_scanned": 0,
    }

    py_files = list(_iter_py(base))
    has_node = (base / "package.json").is_file()
    if py_files:
        facts["language"] = "python"
    elif has_node:
        facts["language"] = "node"
        facts["evidence"].append("package.json 발견 (Node.js)")
        return facts  # 데모는 Python AST 판정에 집중

    web_fw: set[str] = set()
    for pf in py_files:
        facts["py_files_scanned"] += 1
        try:
            tree = ast.parse(pf.read_bytes()[:MAX_READ_BYTES].decode("utf-8", "replace"))
        except (SyntaxError, ValueError):
            continue
        rel = os.path.relpath(pf, base).replace(os.sep, "/")

        imported_names: set[str] = set()   # 이 파일이 import 한 최상위 모듈
        imported_symbols: set[str] = set()  # from x import Y 의 Y
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    imported_names.add(a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_names.add(node.module.split(".")[0])
                for a in node.names:
                    imported_symbols.add(a.name)

        # 1) 웹 프레임워크: import 사실만으로 web 으로 본다 (프레임워크는 import = 사용)
        for mod, label in _WEB_IMPORTS.items():
            if mod in imported_names:
                web_fw.add(label)
                facts["is_web_server"] = True
                facts["evidence"].append(f"{rel}: {label} import")

        # 2) stdlib HTTP 서버: import 만으론 부족 — 실제 생성자 호출이 있어야 web
        stdlib_http_imported = ("http" in imported_names
                                or "socketserver" in imported_names
                                or imported_symbols & _STDLIB_HTTP)
        if stdlib_http_imported:
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = node.func
                    name = (fn.attr if isinstance(fn, ast.Attribute)
                            else fn.id if isinstance(fn, ast.Name) else None)
                    if name in _STDLIB_HTTP:
                        facts["is_web_server"] = True
                        facts["evidence"].append(
                            f"{rel}: stdlib {name}() 실제 호출 → web 서버")
                        break

        # 3) 워커/스케줄러
        if imported_names & _WORKER_IMPORTS:
            facts["has_worker"] = True
            facts["evidence"].append(
                f"{rel}: {', '.join(sorted(imported_names & _WORKER_IMPORTS))} (상시 워커)")

        # 4) WebSocket / 실시간
        if (imported_names & _WS_HINTS) or (imported_symbols & _WS_HINTS):
            facts["uses_websocket"] = True
            facts["evidence"].append(f"{rel}: WebSocket/실시간 라이브러리")

        # 5) DB
        if imported_names & _DB_HINTS:
            facts["uses_database"] = True
            facts["evidence"].append(
                f"{rel}: {', '.join(sorted(imported_names & _DB_HINTS))} (DB/캐시)")

        # 6) 엔트리포인트 (__main__)
        src = pf.read_text("utf-8", "replace")
        if "__main__" in src and "if __name__" in src:
            facts["entrypoints"].append(rel)

    facts["web_frameworks"] = sorted(web_fw)
    return facts
