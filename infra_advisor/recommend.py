"""판정된 '사실'을 카탈로그 능력표에 대조해 배포 대상을 추천한다.

- LLM 이 아니라 코드가 결정 → 같은 입력엔 항상 같은 추천 (결정적·일관성).
- 추천은 카탈로그 허용 목록 안에서만 나오고, 각 후보에 근거(detected fact)와
  제약(limits)을 함께 붙인다 → 설명 가능.
"""
from __future__ import annotations

from .catalog import TARGETS, is_allowed


def recommend(facts: dict) -> dict:
    """detect_stack 의 facts 를 받아 1~N 순위 추천을 돌려준다."""
    always_on = bool(facts.get("has_worker") or facts.get("uses_websocket"))
    multi = bool(facts.get("uses_database"))  # 데모: DB 동반 → 다중 컨테이너로 간주
    is_web = bool(facts.get("is_web_server"))

    ranked: list[tuple[str, int, str]] = []  # (target_id, 점수, 근거)
    for tid, spec in TARGETS.items():
        score = 0
        why: list[str] = []

        if always_on:
            if spec["always_on"]:
                score += 3
                why.append("상시 실행(워커/WebSocket) 필요 → 항상 켜진 대상")
            else:
                score -= 3
                why.append("요청 단위 실행이라 상시 연결/워커에 부적합")
        else:
            if is_web and spec["stateless"]:
                score += 3
                why.append("짧은 웹 요청 위주 → 요청 단위 실행이 비용 효율적")
            if spec["always_on"] and is_web:
                score += 1
                why.append("상시 서버로도 운영 가능(대안)")

        if multi and spec["multi_container"]:
            score += 2
            why.append("DB·캐시 등 컨테이너 여러 개 동반 → 한 서버에 함께")
        if multi and not spec["multi_container"] and not spec["stateless"]:
            why.append("단일 컨테이너 가정 — DB 는 별도 관리 필요")

        if facts.get("uses_websocket") and not spec["supports_websocket"]:
            score -= 5
            why.append("WebSocket 미지원")

        ranked.append((tid, score, "; ".join(why) or "기본 후보"))

    ranked.sort(key=lambda r: r[1], reverse=True)

    candidates = []
    for tid, score, why in ranked:
        assert is_allowed(tid)  # 목록 밖 값은 애초에 생기지 않는다
        spec = TARGETS[tid]
        candidates.append({
            "target": tid,
            "label": spec["label"],
            "cloud": spec["cloud"],
            "score": score,
            "good_for": spec["good_for"],
            "limits": spec["limits"],
            "reason": why,
        })

    top = candidates[0]
    return {
        "recommended": top["target"],
        "recommended_label": top["label"],
        "summary": f"{top['label']} — {top['reason']}",
        "candidates": candidates,
        "facts_used": {
            "is_web_server": is_web,
            "always_on": always_on,
            "multi_container": multi,
            "uses_websocket": bool(facts.get("uses_websocket")),
        },
    }
