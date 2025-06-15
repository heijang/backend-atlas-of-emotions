from fastapi import FastAPI
from app.websocket import router as ws_router
from app.api import router as api_router

app = FastAPI()
app.include_router(ws_router)
app.include_router(api_router)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True) 