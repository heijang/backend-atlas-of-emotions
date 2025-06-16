## 감정도감 백엔드

### 실행 방법

1. 의존성 설치

```
pip install -r requirements.txt
```

2. 서버 실행 (최상위 폴더에서 아래 명령어로 실행하세요)

```
uvicorn app.main:app --reload
```

### 중요
- 반드시 프로젝트 최상위 폴더(즉, app 폴더가 보이는 위치)에서 실행해야 합니다.
- `python app/main.py`로 실행하면 모듈 import 에러가 발생할 수 있습니다.
- Flask 개발 서버 경고는 무시해도 되며, 실제 서비스 배포 시에는 gunicorn 등 WSGI 서버를 사용하세요.

- HTTP API 엔드포인트
  - `GET /report/<user_id>`
  - `POST /embed-audio/` (multipart/form-data, file 필드 필요)

- WebSocket (Socket.IO)
  - 클라이언트에서 Socket.IO로 연결 후 'audio_chunk' 이벤트로 바이너리 데이터 전송
  - 예시: `io.connect('http://localhost:8000')` 후 `socket.emit('audio_chunk', data)`
