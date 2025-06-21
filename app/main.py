from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.endpoint.websocket import router as ws_router
from app.endpoint.api import router as api_router

app = FastAPI()

# CORS 설정 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발 시 전체 허용, 운영 시 도메인 제한 권장
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws_router)
app.include_router(api_router)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True) 