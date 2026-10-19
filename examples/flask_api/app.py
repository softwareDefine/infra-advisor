"""짧은 웹 요청 위주의 Flask API 예제 (→ Lambda/Cloud Run 적합 예상)."""
from flask import Flask, jsonify

app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
