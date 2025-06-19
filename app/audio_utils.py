import os
import subprocess
from pathlib import Path
from speechbrain.pretrained import EncoderClassifier
import numpy as np

_classifier = None
def get_classifier():
    global _classifier
    if _classifier is None:
        _classifier = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb")
    return _classifier

def parse_silence_log(ffmpeg_output: str):
    import re
    starts = []
    ends = []
    for line in ffmpeg_output.splitlines():
        if "silence_start" in line:
            match = re.search(r"silence_start: (\d+\.?\d*)", line)
            if match:
                starts.append(float(match.group(1)))
        elif "silence_end" in line:
            match = re.search(r"silence_end: (\d+\.?\d*)", line)
            if match:
                ends.append(float(match.group(1)))
    return list(zip(ends[:-1], starts[1:]))  # (start, end) for segments between silences

def get_storage_audio_path(*paths):
    base = os.path.join("storage", "audio")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, *paths)

def convert_webm_to_wav(webm_path, wav_path):
    wav_path = get_storage_audio_path(wav_path) if not wav_path.startswith("storage/audio/") else wav_path
    subprocess.run([
        "ffmpeg", "-y", "-i", webm_path,
        "-ar", "16000", "-ac", "1", wav_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def split_wav_by_silence(wav_path, output_dir, silence_threshold="-35dB", silence_duration=0.7):
    output_dir = get_storage_audio_path(output_dir) if not output_dir.startswith("storage/audio/") else output_dir
    result = subprocess.run([
        "ffmpeg", "-i", wav_path,
        "-af", f"silencedetect=noise={silence_threshold}:d={silence_duration}",
        "-f", "null", "-"
    ], stderr=subprocess.PIPE, text=True)

    segments = parse_silence_log(result.stderr)
    if not segments:
        return []

    saved_files = []
    for i, (start, end) in enumerate(segments):
        out_file = Path(output_dir) / f"{Path(wav_path).stem}_seg_{i}.wav"
        subprocess.run([
            "ffmpeg", "-y", "-i", wav_path,
            "-ss", str(start), "-to", str(end),
            "-c", "copy", str(out_file)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        saved_files.append(str(out_file))

    return saved_files

def extract_and_save_embedding(audio_path: str) -> str:
    """
    Extracts embedding from audio using speechbrain and saves it to a file.
    Returns the path to the saved embedding file.
    """
    classifier = get_classifier()
    signal = classifier.load_audio(audio_path)
    embedding = classifier.encode_batch(signal)
    embedding_np = embedding.squeeze().cpu().numpy()

    embedding_dir = get_storage_audio_path("embeddings")
    os.makedirs(embedding_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(audio_path))[0]
    embedding_path = os.path.join(embedding_dir, f"{base}_embedding.npy")
    np.save(embedding_path, embedding_np)
    return embedding_path

def extract_voice_embedding(audio_path: str) -> np.ndarray:
    """
    Extracts a voice embedding from an audio file using speechbrain.
    Returns the embedding as a numpy array.
    """
    classifier = get_classifier()
    signal = classifier.load_audio(audio_path)
    # signal: torch.Tensor, shape: (1, N) or (N,)
    try:
        import soundfile as sf
        info = sf.info(audio_path)
        print(f"[임베딩 추출] audio_path={audio_path} | samplerate={info.samplerate} | channels={info.channels} | format={info.format} | subtype={info.subtype}")
    except Exception as e:
        print(f"[임베딩 추출] audio_path={audio_path} | 파일 정보 확인 실패: {e}")
    print(f"[임베딩 추출] signal.shape={getattr(signal, 'shape', None)}, signal.dtype={getattr(signal, 'dtype', None)}")
    embedding = classifier.encode_batch(signal)
    embedding_np = embedding.squeeze().cpu().numpy().astype(np.float32)
    return embedding_np

def cosine_similarity(vec1, vec2):
    # print("vec1:", vec1)
    # print("vec2:", vec2)
    if vec1 is None or vec2 is None:
        return -1.0
    v1 = np.array(vec1)
    v2 = np.array(vec2)
    if v1.shape != v2.shape:
        return -1.0
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return -1.0
    return float(np.dot(v1, v2) / (norm1 * norm2))

def cut_wav_by_timestamps(wav_path, segments, output_dir):
    """
    wav_path: 원본 wav 파일 경로
    segments: [(start, end), ...] 초 단위
    output_dir: 저장할 폴더
    return: 저장된 파일 경로 리스트
    """
    output_dir = get_storage_audio_path(output_dir) if not output_dir.startswith("storage/audio/") else output_dir
    os.makedirs(output_dir, exist_ok=True)
    saved_files = []
    for i, (start, end) in enumerate(segments):
        out_file = Path(output_dir) / f"{Path(wav_path).stem}_seg_{i}.wav"
        subprocess.run([
            "ffmpeg", "-y", "-i", wav_path,
            "-ss", str(start), "-to", str(end),
            "-c", "copy", str(out_file)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        saved_files.append(str(out_file))
    return saved_files 