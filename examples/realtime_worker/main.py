"""상시 실행 + WebSocket + DB 를 쓰는 예제 (→ EC2 Compose 적합 예상).

주석 안의 flask 라는 단어는 web 판정에 잡히면 안 된다(AST 는 주석을 무시).
"""
import asyncio

import websockets  # 실시간 연결
import psycopg2    # DB
from celery import Celery  # 상시 워커

celery_app = Celery("tasks", broker="redis://localhost:6379/0")


async def handler(ws):
    async for msg in ws:
        await ws.send(msg)


async def main():
    async with websockets.serve(handler, "0.0.0.0", 8765):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
