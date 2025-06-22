from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.services.user_services import user_service
from app.services.user_voice_service import user_voice_service
from app.endpoints.ws_analyze import user_voice_embeddings_mem

router = APIRouter()

@router.post("/api/v1/users")
async def register_user(request: Request):
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        form = await request.form()
        user_id = form.get("user_id")
        user_name = form.get("user_name")
    else:
        data = await request.json()
        user_id = data.get("user_id")
        user_name = data.get("user_name")
    if not user_id or not user_name:
        return JSONResponse(
            content={"success": False, "error": "user_id, user_name required"},
            status_code=400,
        )
    
    try:
        user_service.register_user(user_id, user_name)
        user = user_service.get_user_by_id(user_id)
        if user:
            return JSONResponse(content={"success": True, **user}, status_code=200)
        else:
            return JSONResponse(
                content={"success": False, "error": "User not found after registration"},
                status_code=500,
            )
    except Exception as e:
        return JSONResponse(
            content={"success": False, "error": str(e)}, status_code=500
        )

@router.post("/api/v1/auth/login")
async def login_user(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    if not user_id:
        return JSONResponse(
            content={"success": False, "error": "user_id required"}, status_code=400
        )
    
    try:
        user = user_service.get_user_by_id(user_id)
        if user:
            # 음성 임베딩 메모리 적재
            user_uid = user.get('uid')
            embedding = user_voice_service.get_user_voice_embedding(user_uid)
            if embedding is not None:
                user_voice_embeddings_mem[user_id] = embedding
                print(f"[로그인] user_id={user_id} 음성 임베딩 메모리 적재 완료.")
            else:
                print(f"[로그인] user_id={user_id} 음성 임베딩 정보 없음.")
            return JSONResponse(content={"success": True, **user}, status_code=200)
        else:
            return JSONResponse(
                content={"success": False, "error": "User not found"}, status_code=404
            )
    except Exception as e:
        return JSONResponse(
            content={"success": False, "error": str(e)}, status_code=500
        ) 