from fastapi import APIRouter, UploadFile, File, Response
import os
import json
from app.audio_utils import extract_and_save_embedding, get_storage_audio_path

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