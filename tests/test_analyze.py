"""analyze/recommend 동작·안전 규칙 테스트.

핵심은 '표면 패턴이 아니라 AST 로 판정한다'는 것:
import/문자열/주석에 서버 이름이 있어도, 실제 생성자 호출이 없으면 web 아님.
"""
import os
from pathlib import Path

import pytest

from infra_advisor import analyze
from infra_advisor.recommend import recommend

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


# ── AST: 오탐 방지 ──────────────────────────────────────────────

def test_stdlib_http_comment_string_is_not_web(tmp_path):
    (tmp_path / "util.py").write_text(
        "# from http.server import HTTPServer  설명용 주석\n"
        'DOC = "HTTPServer() 를 이렇게 씁니다"  # 문자열일 뿐\n'
        "import http.server  # import 만, 호출 없음\n",
        encoding="utf-8",
    )
    facts = analyze.detect_stack(str(tmp_path))
    assert facts["is_web_server"] is False  # 주석·문자열·미호출 import → web 아님


def test_stdlib_http_real_call_is_web(tmp_path):
    (tmp_path / "srv.py").write_text(
        "from http.server import HTTPServer, BaseHTTPRequestHandler\n"
        "httpd = HTTPServer(('0.0.0.0', 80), BaseHTTPRequestHandler)\n"
        "httpd.serve_forever()\n",
        encoding="utf-8",
    )
    facts = analyze.detect_stack(str(tmp_path))
    assert facts["is_web_server"] is True  # 실제 생성자 호출 → web


# ── 예제 저장소 end-to-end ───────────────────────────────────────

def test_flask_api_recommends_request_scaled():
    facts = analyze.detect_stack(str(EXAMPLES / "flask_api"))
    assert facts["is_web_server"] is True
    assert "Flask" in facts["web_frameworks"]
    rec = recommend(facts)
    # 짧은 웹 요청 → 요청 단위 실행(Lambda/Cloud Run)이 1순위
    assert rec["recommended"] in {"aws_lambda", "gcp_cloud_run"}


def test_realtime_worker_recommends_always_on():
    facts = analyze.detect_stack(str(EXAMPLES / "realtime_worker"))
    assert facts["uses_websocket"] is True
    assert facts["has_worker"] is True
    assert facts["uses_database"] is True
    rec = recommend(facts)
    # 상시 실행 + DB → 항상 켜진 대상, Lambda 류는 밀린다
    assert rec["recommended"] in {"aws_ec2_compose", "aws_ec2", "aws_ecs_fargate"}
    assert rec["recommended"] != "aws_lambda"


def test_recommendation_is_deterministic():
    facts = analyze.detect_stack(str(EXAMPLES / "flask_api"))
    a = recommend(facts)
    b = recommend(facts)
    assert a == b  # LLM 아님 → 같은 입력엔 같은 추천


# ── 안전 규칙 ────────────────────────────────────────────────────

def test_secret_file_not_listed_or_read(tmp_path):
    (tmp_path / ".env").write_text("SECRET_KEY=abcd", encoding="utf-8")
    (tmp_path / "app.py").write_text("x = 1", encoding="utf-8")
    files = analyze.list_files(str(tmp_path))
    assert ".env" not in files
    assert "app.py" in files
    with pytest.raises(PermissionError):
        analyze.read_file(str(tmp_path), ".env")


def test_path_traversal_blocked(tmp_path):
    (tmp_path / "app.py").write_text("x = 1", encoding="utf-8")
    with pytest.raises(ValueError):
        analyze.read_file(str(tmp_path), "../../etc/passwd")


def test_is_secret_rules():
    for name in (".env", "server.pem", "my_secret.txt", "AccessKey.csv",
                 "id_rsa", "db_password.yaml"):
        assert analyze.is_secret(name), name
    for name in ("app.py", "README.md", "main.go"):
        assert not analyze.is_secret(name), name
