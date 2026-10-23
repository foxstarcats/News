"""VOICEVOX エンジンで台本を読み上げ、1本のMP3にまとめる。"""

from __future__ import annotations

import io
import time
import wave

import lameenc
import requests


class Voicevox:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def wait_until_ready(self, timeout: float = 300) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = requests.get(f"{self.base_url}/version", timeout=5)
                if r.ok:
                    print(f"  VOICEVOX engine {r.text.strip()} ready")
                    return
            except requests.RequestException:
                pass
            time.sleep(3)
        raise RuntimeError(f"VOICEVOX エンジンに接続できません: {self.base_url}")

    def synthesize(self, text: str, speaker: int, speed: float) -> bytes:
        for attempt in range(3):
            try:
                q = requests.post(f"{self.base_url}/audio_query",
                                  params={"text": text, "speaker": speaker}, timeout=60)
                q.raise_for_status()
                query = q.json()
                query["speedScale"] = speed
                s = requests.post(f"{self.base_url}/synthesis", params={"speaker": speaker},
                                  json=query, timeout=300)
                s.raise_for_status()
                return s.content
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(5)
        raise AssertionError("unreachable")


def render_episode(script: dict, cfg: dict, engine_url: str, out_path: str) -> float:
    """台本をMP3に変換して保存し、長さ（秒）を返す。"""
    vv = Voicevox(engine_url)
    vv.wait_until_ready()
    voices = cfg["voices"]
    speakers = {"host": voices["host"]["speaker_id"], "guest": voices["guest"]["speaker_id"]}

    pcm = bytearray()
    rate = None
    lines = script["lines"]
    started = time.time()
    for i, line in enumerate(lines, 1):
        wav_bytes = vv.synthesize(line["text"], speakers[line["speaker"]], voices["speed"])
        with wave.open(io.BytesIO(wav_bytes)) as w:
            if rate is None:
                rate = w.getframerate()
                silence = b"\x00\x00" * int(rate * voices["pause_ms"] / 1000)
            if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != rate:
                raise RuntimeError("想定外の音声形式です")
            pcm += w.readframes(w.getnframes())
        pcm += silence
        if i % 20 == 0 or i == len(lines):
            print(f"  音声合成 {i}/{len(lines)} ({time.time() - started:.0f}s)")

    encoder = lameenc.Encoder()
    encoder.set_bit_rate(64)
    encoder.set_in_sample_rate(rate)
    encoder.set_channels(1)
    encoder.set_quality(2)
    mp3 = encoder.encode(bytes(pcm)) + encoder.flush()
    with open(out_path, "wb") as f:
        f.write(mp3)
    return len(pcm) / 2 / rate
