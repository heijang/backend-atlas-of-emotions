import os
import subprocess
from pathlib import Path

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

def convert_webm_to_wav(webm_path, wav_path):
    subprocess.run([
        "ffmpeg", "-y", "-i", webm_path,
        "-ar", "16000", "-ac", "1", wav_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def split_wav_by_silence(wav_path, output_dir, silence_threshold="-35dB", silence_duration=0.7):
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