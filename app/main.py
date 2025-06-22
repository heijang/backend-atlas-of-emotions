from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.endpoints.api_user import router as api_user_router
from app.endpoints.api_analyze import router as api_analyze_router
from app.endpoints.api_report import router as api_report_router
from app.endpoints.ws_user_voice import router as ws_user_router
from app.endpoints.ws_analyze import router as ws_analyze_router
import uvicorn

app = FastAPI()

# CORS 설정 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발 시 전체 허용, 운영 시 도메인 제한 권장
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_user_router)
app.include_router(api_analyze_router)
app.include_router(api_report_router)
app.include_router(ws_user_router)
app.include_router(ws_analyze_router)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)