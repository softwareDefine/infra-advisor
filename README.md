# infra-advisor — 배포 추천 MCP 서버

저장소를 읽어 **적합한 배포 인프라를 근거와 함께 추천**하는 읽기 전용 [MCP](https://modelcontextprotocol.io) 서버입니다.
Claude Desktop 같은 MCP 호스트에 등록하면, LLM이 다음 도구를 호출해 분석·추천합니다.

> 소프트뱅크 해커톤 수상작 **Pawploy(AgentCore)** 에서 제가 설계·구현한 에이전트 도구 구조를,
> private 레포 의존 없이 **MCP 표준 서버**로 다시 구현한 데모입니다.

## 설계 원칙 (Pawploy 그대로)

| 원칙 | 구현 |
|---|---|
| **판단은 LLM, 사실·검사는 코드** | 호스트 LLM이 추론하고, 서버는 "검증된 사실"만 돌려준다. 추천 자체도 코드가 결정 |
| **표면 패턴이 아니라 AST로 판정** | 웹 서버는 프레임워크를 실제 `import` 했거나 stdlib HTTP 서버를 **실제 생성자 호출**한 경우에만 인정 — 주석·문자열·미호출 import는 오탐 제외 |
| **추천은 일관·설명가능** | LLM이 아니라 코드가 **검증된 능력 카탈로그(허용 목록)** 에 대조해 결정 → 같은 입력엔 항상 같은 추천, 후보마다 근거·제약 동봉 |
| **읽기 전용 + 인젝션 안전 경계** | 쓰기·배포·삭제 도구 없음. 비밀 파일(`.env`·`*.pem`·`*secret*`)은 읽지 않고, 경로 탈출(`..`)·크기 상한을 코드로 강제 |

## 도구

| 도구 | 설명 |
|---|---|
| `list_files(root)` | 파일 목록 (비밀 파일·`node_modules`·`.git` 제외, 상한 2000) |
| `read_file(root, path)` | 파일 1개 읽기 (비밀 거부·256KB 상한·경로 탈출 차단) |
| `detect_stack(root)` | AST로 언어·웹 서버·워커·WebSocket·DB·엔트리포인트를 **근거와 함께** 판정 |
| `recommend_infra(root)` | 능력 카탈로그에 대조해 배포 대상 1~N순위를 **근거·제약과 함께** 추천 |

카탈로그: AWS Lambda · GCP Cloud Run · AWS EC2 · AWS EC2(Compose) · AWS ECS Fargate.

## 설치 · 실행

```bash
pip install -e .          # 또는:  pip install mcp
python -m infra_advisor.server     # stdio MCP 서버 기동
```

### Claude Desktop에 등록

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "infra-advisor": {
      "command": "python",
      "args": ["-m", "infra_advisor.server"],
      "cwd": "<이 저장소 절대경로>"
    }
  }
}
```

등록 후 Claude에게 *"이 레포 `examples/flask_api` 배포 어디에 할지 추천해줘"* 라고 하면,
`detect_stack` → `recommend_infra` 를 호출해 근거와 함께 답합니다.

## 예시 결과

| 예제 | 판정 | 추천 |
|---|---|---|
| `examples/flask_api` | Flask, 짧은 웹 요청 | **AWS Lambda** (요청 단위 실행이 비용 효율적) |
| `examples/realtime_worker` | WebSocket + Celery 워커 + DB | **AWS EC2 (Docker Compose)** (상시 실행·다중 컨테이너) |

## 테스트

```bash
pip install pytest && pytest -q
```

AST 오탐 방지(주석·문자열·미호출 import는 web 아님), 비밀 파일 차단, 경로 탈출 차단,
추천 결정성(같은 입력=같은 출력)을 검증합니다.
