"""배포 대상 카탈로그 (허용 목록).

추천은 이 목록 안에서만 나온다. 목록 밖 값은 코드가 버린다.
각 대상의 능력(good_for)·제약(limits)을 문서로 고정해 두고,
판정 결과를 이 능력표에 대조해 근거와 함께 추천한다.

→ Pawploy AgentCore 의 catalog.py 를 MCP 데모용으로 재구성한 것.
  "LLM 이 상황을 상상해서 고르는" 대신 "검증된 능력표에 근거해 코드가 고른다".
"""
from __future__ import annotations

# 각 대상은 실제로 배포 가능한(=검증된) 구성만 담는다.
TARGETS: dict[str, dict] = {
    "aws_lambda": {
        "label": "AWS Lambda",
        "cloud": "aws",
        "good_for": "요청이 가끔 오고 요청 하나가 짧게 끝나는 웹 API·웹앱",
        "limits": "요청당 실행 시간 상한, 상태·로컬 파일을 서버에 남길 수 없음, WebSocket 불가",
        # 추천 판정에 쓰는 능력 플래그
        "stateless": True,
        "always_on": False,
        "supports_websocket": False,
        "multi_container": False,
    },
    "gcp_cloud_run": {
        "label": "Google Cloud Run",
        "cloud": "gcp",
        "good_for": "컨테이너 웹앱을 요청 있을 때만 실행 (Lambda 보다 제약이 적음)",
        "limits": "요청 단위 실행, 로컬 파일은 임시, 상시 연결에는 부적합",
        "stateless": True,
        "always_on": False,
        "supports_websocket": False,
        "multi_container": False,
    },
    "aws_ec2": {
        "label": "AWS EC2",
        "cloud": "aws",
        "good_for": "항상 켜져 있어야 하는 서버, 실시간 연결, 오래 걸리는 요청",
        "limits": "켜져 있는 동안 계속 과금, 서버 1대라 직접 관리 필요",
        "stateless": False,
        "always_on": True,
        "supports_websocket": True,
        "multi_container": False,
    },
    "aws_ec2_compose": {
        "label": "AWS EC2 (Docker Compose)",
        "cloud": "aws",
        "good_for": "DB·캐시·워커·프록시처럼 컨테이너 여러 개가 한 서버에서 같이 떠야 하는 앱",
        "limits": "켜져 있는 동안 계속 과금, 서버 1대라 DB 데이터는 서버를 지우면 사라짐",
        "stateless": False,
        "always_on": True,
        "supports_websocket": True,
        "multi_container": True,
    },
    "aws_ecs_fargate": {
        "label": "AWS ECS Fargate",
        "cloud": "aws",
        "good_for": "항상 켜진 컨테이너 서비스를 서버 관리 없이 운영",
        "limits": "로드밸런서 비용이 추가로 듦",
        "stateless": False,
        "always_on": True,
        "supports_websocket": True,
        "multi_container": False,
    },
}

ALLOWED = frozenset(TARGETS)


def is_allowed(target_id: str) -> bool:
    """목록 밖 값은 코드가 버린다."""
    return target_id in ALLOWED
