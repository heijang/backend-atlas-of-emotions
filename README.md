## 감정도감 백엔드

### 환경 변수 설정

- `ENV/.env_example` 파일을 `ENV/.env`로 복사한 뒤, 아래 항목을 반드시 채워주세요:
  - CLOVA_SECRET_KEY
  - CLOVA_INVOKE_URL
  - GOOGLE_API_KEY
- 예시:
  ```
  CLOVA_SECRET_KEY=여기에_클로바_시크릿키
  CLOVA_INVOKE_URL=여기에_클로바_API_URL
  GOOGLE_API_KEY=여기에_구글_API_KEY
  ```

  # PostgreSQL DB 연결 정보도 아래와 같이 입력하세요:
  POSTGRES_HOST=DB_IP
  POSTGRES_PORT=5432
  POSTGRES_DB=emotion
  POSTGRES_USER=postgres
  POSTGRES_PASSWORD=비밀번호

---

### 실행 방법

1. 의존성 설치

```
pip install -r requirements.txt
```

2. 서버 실행 (최상위 폴더에서 아래 명령어로 실행하세요)

```
uvicorn app.main:app --reload
```

### DB 연결 테스트

- PostgreSQL DB 연결이 정상적으로 되는지 확인하려면 아래 명령어를 실행하세요:

```
python -m app.persistence.dao_test
```

- 사용법 및 상세 예시는 `app/persistence/dao_test.py` 상단 주석을 참고하세요.

### 감정분석 테스트 실행

- 오디오 파일과 텍스트를 입력해 Gemini 기반 감정분석 결과를 콘솔로 확인할 수 있습니다.
- 예시 스크립트: `app/emotion_analyzer_test.py`
- 실행 방법 (최상위 폴더에서):

```
python -m app.emotion_analyzer_test
```

- 또는 아래와 같이 실행해도 됩니다:
```
PYTHONPATH=. python app/emotion_analyzer_test.py
```

- 결과는 텍스트/음성 각각의 감정 점수, 우세 감정, 표준 감정, 한글, 색상 정보가 dict로 출력됩니다.

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
