"""
audio — 音频后处理：时长测量 / 拼接 / 插静音 / 时间戳累积。

三层实现（自动择优）：
  1. 有 ffmpeg → 所有输入统一解码为 24kHz 单声道 PCM → stdlib 拼接+插静音 → 编码 mp3
     （跨格式、跨采样率通吃；时间戳按 PCM 字节数精确累积）
  2. 无 ffmpeg 且全部为 WAV → 纯 stdlib 拼接（输出 wav）
  3. 其余 → sequence 模式（不拼接，逐句文件 + 前端逐行播放）
"""
import logging
import os
import subprocess
import tempfile
import wave
from io import BytesIO
from pathlib import Path
from typing import Optional

from providers import ffmpeg_path

log = logging.getLogger(__name__)

CANON_RATE = 24000      # 统一采样率
CANON_CH = 1            # 单声道
CANON_WIDTH = 2         # 16bit
MP3_BITRATE = "128k"
FFMPEG_TIMEOUT = 120    # 单次编解码超时（秒），防止异常输入卡死流水线

_UNSET = object()


class AudioMixer:
    """唯一感知 ffmpeg 存在与否的模块。"""

    def __init__(self, ffmpeg=_UNSET):
        # 显式传 ffmpeg=None 可强制走纯 stdlib WAV 路径（测试用）
        self.ffmpeg = ffmpeg_path() if ffmpeg is _UNSET else ffmpeg
        self.has_ffmpeg = self.ffmpeg is not None

    # ── 时长测量 ──────────────────────────────────────────
    def measure_duration_ms(self, audio_bytes: bytes, fmt: str) -> Optional[int]:
        try:
            if fmt == "wav":
                with wave.open(BytesIO(audio_bytes)) as w:
                    return int(round(w.getnframes() * 1000.0 / w.getframerate()))
            if self.ffmpeg:
                return self._pcm_duration_ms(self._to_pcm(audio_bytes))
        except Exception:
            pass
        return None

    # ── ffmpeg 编解码（pipe，免临时文件依赖）──────────────
    def _to_pcm(self, audio_bytes: bytes) -> bytes:
        p = subprocess.run(
            [self.ffmpeg, "-hide_banner", "-loglevel", "error",
             "-i", "pipe:0", "-f", "s16le", "-acodec", "pcm_s16le",
             "-ar", str(CANON_RATE), "-ac", str(CANON_CH), "pipe:1"],
            input=audio_bytes, capture_output=True, timeout=FFMPEG_TIMEOUT)
        if p.returncode != 0 or not p.stdout:
            raise RuntimeError("ffmpeg 解码失败: " + p.stderr.decode(errors="ignore")[:200])
        return p.stdout

    @staticmethod
    def _pcm_duration_ms(pcm: bytes) -> int:
        return int(len(pcm) / (CANON_RATE * CANON_WIDTH) * 1000)

    def _pcm_to_mp3(self, pcm: bytes) -> bytes:
        fd, tmp = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        try:
            p = subprocess.run(
                [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "s16le", "-ar", str(CANON_RATE), "-ac", str(CANON_CH),
                 "-i", "pipe:0", "-b:a", MP3_BITRATE, tmp],
                input=pcm, capture_output=True, timeout=FFMPEG_TIMEOUT)
            if p.returncode != 0:
                raise RuntimeError("ffmpeg 编码失败: " + p.stderr.decode(errors="ignore")[:200])
            return Path(tmp).read_bytes()
        finally:
            Path(tmp).unlink(missing_ok=True)

    # ── 拼页合成 ──────────────────────────────────────────
    def synth_page_audio(self, lines: list) -> tuple:
        """
        lines: [{line_id, audio_bytes, fmt, duration_ms?, character, text, pause_after_ms}]
        返回 (page_audio_bytes | None, segments, mode, out_fmt)
        """
        if self.ffmpeg:
            try:
                return self._concat_ffmpeg(lines)
            except Exception as e:
                # ffmpeg 异常时保底降级；记录下来，避免"坏了"看起来像"没装"
                log.warning("ffmpeg 拼接失败，降级为 WAV/逐句模式: %s", e)
        if {ln.get("fmt", "wav") for ln in lines} == {"wav"}:
            durations = []
            for ln in lines:
                dur = ln.get("duration_ms") or self.measure_duration_ms(ln["audio_bytes"], "wav")
                if dur is None:
                    return self._sequence(lines)
                durations.append(dur)
            return self._concat_wav(lines, durations)
        return self._sequence(lines)

    def _concat_ffmpeg(self, lines: list) -> tuple:
        """统一路径：全部解码为 PCM → 拼接 + 插静音 → 编码 mp3，时间戳按字节数精确累积。"""
        cursor, segments, mixed = 0, [], bytearray()
        for ln in lines:
            pcm = self._to_pcm(ln["audio_bytes"])
            dur = self._pcm_duration_ms(pcm)
            start = cursor
            end = start + dur
            segments.append({
                "line_id": ln["line_id"], "start_ms": start, "end_ms": end,
                "character": ln.get("character", ""), "text": ln.get("text", ""),
            })
            mixed += pcm
            pause = int(ln.get("pause_after_ms", 0) or 0)
            if pause:
                n = int(CANON_RATE * pause / 1000) * CANON_CH * CANON_WIDTH
                mixed += b"\x00" * n
            cursor = end + pause
        return self._pcm_to_mp3(bytes(mixed)), segments, "single", "mp3"

    # ── 无 ffmpeg 时的纯 stdlib WAV 拼接 ─────────────────
    def _concat_wav(self, lines: list, durations: list) -> tuple:
        chunks, params_key, out_params = [], None, None
        for ln in lines:
            buf = BytesIO(ln["audio_bytes"])
            with wave.open(buf) as w:
                p = w.getparams()
                key = (p.nchannels, p.sampwidth, p.framerate)
                if params_key is None:
                    params_key, out_params = key, key
                elif key != params_key:
                    return self._sequence(lines)   # 采样参数不一致，降级
                chunks.append((w.readframes(w.getnframes()), ln.get("pause_after_ms", 0)))

        nchannels, sampwidth, framerate = out_params
        out = BytesIO()
        with wave.open(out, "wb") as w:
            w.setnchannels(nchannels)
            w.setsampwidth(sampwidth)
            w.setframerate(framerate)
            for frames, pause_ms in chunks:
                w.writeframes(frames)
                n_silent = int(framerate * pause_ms / 1000.0)
                if n_silent:
                    w.writeframes(b"\x00" * (n_silent * nchannels * sampwidth))
        page_bytes = out.getvalue()

        cursor, segments = 0.0, []
        for ln, dur in zip(lines, durations):
            start = int(round(cursor))
            end = start + dur
            cursor = end + ln.get("pause_after_ms", 0)
            segments.append({
                "line_id": ln["line_id"], "start_ms": start, "end_ms": end,
                "character": ln.get("character", ""), "text": ln.get("text", ""),
            })
        return page_bytes, segments, "single", "wav"

    # ── 序列降级 ──────────────────────────────────────────
    def _sequence(self, lines: list) -> tuple:
        segments = []
        for idx, ln in enumerate(lines, start=1):
            segments.append({
                "line_id": ln["line_id"],
                "order": idx,
                "audio_file": ln.get("audio_file", ""),
                "pause_after_ms": ln.get("pause_after_ms", 0),
                "character": ln.get("character", ""),
                "text": ln.get("text", ""),
            })
        return None, segments, "sequence", None