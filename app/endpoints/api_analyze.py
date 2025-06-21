import json
import os

from fastapi import APIRouter, File, Response, UploadFile

from app.utils.audio_utils import extract_and_save_embedding, get_storage_audio_path

router = APIRouter()

# TODO: 오디오 업로드 분석 기능 추가 예정
@router.post('/api/v1/analyze/audio')
def analyze_audio(file: UploadFile = File(...)):
    upload_dir = get_storage_audio_path("uploads")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)
    with open(file_path, "wb") as f:
        f.write(file.file.read())
    embedding_path = extract_and_save_embedding(file_path)
    return Response(content=json.dumps({"embedding_file": embedding_path}, ensure_ascii=False), media_type='application/json')