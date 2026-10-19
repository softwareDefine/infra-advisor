"""infra-advisor MCP 서버.

저장소를 읽어 배포 인프라를 근거와 함께 추천하는 도구들을 MCP 로 노출한다.
Pawploy(AgentCore) 의 에이전트 도구 구조를 MCP 표준 서버로 옮긴 데모:

  - 도구는 전부 **읽기 전용** (쓰기·배포·삭제 도구 없음) → 프롬프트 인젝션 안전 경계
  - 비밀 파일은 읽지 않음
  - 추천은 **코드가 카탈로그 능력표에 대조해 결정** → LLM 변동 없이 일관
  - "판단은 LLM(호스트), 검사·사실은 코드(서버)" 경계를 MCP 로 구현

실행:
  uv run infra-advisor            # 또는
  python -m infra_advisor.server
호스트(Claude Desktop 등)의 MCP 설정에 stdio 서버로 등록하면 도구가 노출된다.
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import analyze, recommend as _recommend

mcp = MCPServer("infra-advisor")


@mcp.tool()
def list_files(root: str) -> list[str]:
    """저장소 경로의 파일 목록을 돌려준다 (읽기 전용).

    비밀 파일(.env, *.pem, *secret* 등)과 node_modules·.git 같은 폴더는 제외하고,
    최대 2000개까지 돌려준다.

    Args:
        root: 분석할 로컬 저장소의 절대/상대 경로.
    """
    return analyze.list_files(root)


@mcp.tool()
def read_file(root: str, path: str) -> str:
    """저장소 안 파일 하나를 읽는다 (읽기 전용).

    비밀 파일은 거부하고, 256KB 까지만 읽으며, root 밖 경로(.. 탈출)는 막는다.

    Args:
        root: 저장소 루트 경로.
        path: root 기준 상대 경로.
    """
    return analyze.read_file(root, path)


@mcp.tool()
def detect_stack(root: str) -> dict:
    """저장소를 AST 로 파싱해 기술 스택·실행 특성을 '사실'로 판정한다.

    웹 서버는 프레임워크를 실제 import 했거나 stdlib HTTP 서버를 실제로 생성한
    경우에만 인정한다(주석·문자열·미호출 import 제외). 워커/스케줄러, WebSocket,
    DB 사용, 엔트리포인트도 코드 근거(evidence)와 함께 돌려준다.

    Args:
        root: 저장소 루트 경로.
    """
    return analyze.detect_stack(root)


@mcp.tool()
def recommend_infra(root: str) -> dict:
    """저장소에 맞는 배포 대상을 근거와 함께 1~N 순위로 추천한다.

    detect_stack 의 사실을 카탈로그 능력표(허용 목록)에 대조해 코드가 결정하므로,
    같은 입력에는 항상 같은 추천이 나온다(결정적·일관). 각 후보에 적합 이유·제약을
    함께 붙인다.

    Args:
        root: 저장소 루트 경로.
    """
    facts = analyze.detect_stack(root)
    result = _recommend.recommend(facts)
    result["evidence"] = facts.get("evidence", [])
    return result


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
