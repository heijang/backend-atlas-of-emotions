from fastapi import APIRouter, UploadFile, File, Response, Request, Form
import os
import json
from app.util.audio_utils import extract_and_save_embedding, get_storage_audio_path
from app.dao.user_dao import UserDAO
from app.voice_identifier import save_user_voice_embedding_to_db, load_user_voice_embedding_to_memory
from typing import Optional
from app.endpoint.websocket import user_voice_embeddings_mem

router = APIRouter()

@router.get('/report/{user_id}')
def get_report(user_id: int):
    # 예시 데이터
    data = {"user_id": user_id, "report": "감정 분석 결과"}
    return Response(content=json.dumps(data, ensure_ascii=False), media_type='application/json')

@router.post('/embed-audio/')
def embed_audio(file: UploadFile = File(...)):
    upload_dir = get_storage_audio_path("uploads")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)
    with open(file_path, "wb") as f:
        f.write(file.file.read())
    embedding_path = extract_and_save_embedding(file_path)
    return Response(content=json.dumps({"embedding_file": embedding_path}, ensure_ascii=False), media_type='application/json')

@router.post('/register-user')
async def register_user(request: Request):
    data = await request.json()
    user_id = data.get('user_id')
    user_name = data.get('user_name')
    if not user_id or not user_name:
        return Response(content=json.dumps({'success': False, 'error': 'user_id, user_name required'}), media_type='application/json', status_code=400)
    dao = UserDAO()
    try:
        dao.register_user(user_id, user_name)
        return Response(content=json.dumps({'success': True}), media_type='application/json')
    except Exception as e:
        return Response(content=json.dumps({'success': False, 'error': str(e)}), media_type='application/json', status_code=500)
    finally:
        dao.close()

@router.post('/api/signup')
async def signup_user(request: Request, voice_file: Optional[UploadFile] = File(None)):
    if request.headers.get('content-type', '').startswith('multipart/form-data'):
        form = await request.form()
        user_id = form.get('user_id')
        user_name = form.get('user_name')
    else:
        data = await request.json()
        user_id = data.get('user_id')
        user_name = data.get('user_name')
    if not user_id or not user_name:
        return Response(content=json.dumps({'success': False, 'error': 'user_id, user_name required'}), media_type='application/json', status_code=400)
    dao = UserDAO()
    try:
        dao.register_user(user_id, user_name)
        # 음성 파일이 있으면 임베딩 저장
        if voice_file is not None:
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
                tmp.write(await voice_file.read())
                tmp_path = tmp.name
            save_user_voice_embedding_to_db(user_id, tmp_path)
        user = dao.get_user_by_id(user_id)
        if user:
            return Response(content=json.dumps({'success': True, **user}), media_type='application/json', status_code=200)
        else:
            return Response(content=json.dumps({'success': False, 'error': 'User not found after registration'}), media_type='application/json', status_code=500)
    except Exception as e:
        return Response(content=json.dumps({'success': False, 'error': str(e)}), media_type='application/json', status_code=500)
    finally:
        dao.close()

@router.post('/api/login')
async def login_user(request: Request):
    data = await request.json()
    user_id = data.get('user_id')
    if not user_id:
        return Response(content=json.dumps({'success': False, 'error': 'user_id required'}), media_type='application/json', status_code=400)
    dao = UserDAO()
    try:
        user = dao.get_user_by_id(user_id)
        if user:
            # 음성 임베딩 메모리 적재
            embedding = load_user_voice_embedding_to_memory(user_id)
            if embedding is not None:
                user_voice_embeddings_mem[user_id] = embedding
                print(f"[로그인] user_id={user_id} 음성 임베딩 메모리 적재 완료.")
            else:
                print(f"[로그인] user_id={user_id} 음성 임베딩 정보 없음.")
            return Response(content=json.dumps({'success': True, **user}), media_type='application/json', status_code=200)
        else:
            return Response(content=json.dumps({'success': False, 'error': 'User not found'}), media_type='application/json', status_code=404)
    except Exception as e:
        return Response(content=json.dumps({'success': False, 'error': str(e)}), media_type='application/json', status_code=500)
    finally:
        dao.close() 