import json
import os
import numpy as np
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from app.services.voice_service import voice_embedding_service
from app.utils.audio_utils import get_storage_audio_path

router = APIRouter()

# TODO: 오디오 업로드 분석 기능 추가 예정
@router.post("/api/v1/analyze/audio")
def analyze_audio(file: UploadFile = File(...)):
    upload_dir = get_storage_audio_path("uploads")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)
    
    with open(file_path, "wb") as f:
        f.write(file.file.read())
        
    embedding = voice_embedding_service.extract_voice_embedding(file_path)
    
    if embedding is not None:
        embedding_dir = get_storage_audio_path("embeddings")
        os.makedirs(embedding_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(file_path))[0]
        embedding_path = os.path.join(embedding_dir, f"{base}_embedding.npy")
        np.save(embedding_path, embedding)
        return JSONResponse(content={"embedding_file": embedding_path})
    else:
        return JSONResponse(content={"success": False, "error": "Failed to extract embedding"}, status_code=500)