## 실행 방법

1. 의존성 설치

```
pip install -r requirements.txt
```

2. 서버 실행

```
uvicorn app.main:app --reload
```

- WebSocket 엔드포인트: `/ws`
- HTTP API 예시: `/report/{user_id}`