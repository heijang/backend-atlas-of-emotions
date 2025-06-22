from pathlib import Path
import subprocess
import wave
import numpy as np


def cut_wav_by_timestamps(input_wav: str, timestamps: list[tuple[float, float]], output_dir: str) -> list[str]:
    """WAV 파일을 주어진 타임스탬프 목록에 따라 여러 세그먼트로 잘라 저장합니다.

    Args:
        input_wav (str): 원본 WAV 파일 경로.
        timestamps (list[tuple[float, float]]): 자르기 위한 (시작 시간, 종료 시간) 튜플의 리스트.
        output_dir (str): 잘린 WAV 세그먼트를 저장할 디렉토리 경로.

    Returns:
        list[str]: 저장된 각 세그먼트 파일의 경로 리스트.
    """
    if not Path(output_dir).exists():
        Path(output_dir).mkdir(parents=True)
    
    segment_files = []
    try:
        with wave.open(input_wav, 'rb') as wf:
            framerate = wf.getframerate()
            sampwidth = wf.getsampwidth()
            nchannels = wf.getnchannels()
            
            for i, (start_sec, end_sec) in enumerate(timestamps):
                output_wav = Path(output_dir) / f"segment_{i+1}.wav"
                
                start_frame = int(start_sec * framerate)
                end_frame = int(end_sec * framerate)
                
                wf.setpos(start_frame)
                frames = wf.readframes(end_frame - start_frame)
                
                with wave.open(str(output_wav), 'wb') as out_f:
                    out_f.setnchannels(nchannels)
                    out_f.setsampwidth(sampwidth)
                    out_f.setframerate(framerate)
                    out_f.writeframes(frames)
                segment_files.append(str(output_wav))
    except Exception as e:
        print(f"오디오 컷팅 중 에러: {e}")
        return []
    return segment_files


def get_storage_audio_path(subpath: str = "") -> str:
    """storage/audio를 기준으로 하위 경로를 생성하고, 전체 절대 경로를 반환합니다.

    Args:
        subpath (str, optional): storage/audio 아래에 추가할 하위 경로. Defaults to "".

    Returns:
        str: 생성된 디렉토리의 전체 경로.
    """
    base_dir = Path(__file__).parent.parent.parent / "storage" / "audio"
    target_path = base_dir / subpath
    # exist_ok=True: 해당 경로가 존재하더라도 에러 발생 X
    target_path.mkdir(parents=True, exist_ok=True)
    return str(target_path)


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """두 개의 numpy 벡터 간의 코사인 유사도를 계산합니다.

    Args:
        vec1 (np.ndarray): 첫 번째 벡터.
        vec2 (np.ndarray): 두 번째 벡터.

    Returns:
        float: 두 벡터 간의 코사인 유사도 값 (-1.0 ~ 1.0).
               벡터가 유효하지 않거나 정규화할 수 없는 경우 -1.0을 반환합니다.
    """
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