"""音频拼接：无 ffmpeg 时的纯 WAV 路径与时间戳累积。"""
from pipeline.audio import AudioMixer
from providers.mock_provider import MockTTS, silent_wav


def make_line(line_id: str, seconds: float, pause_ms: int) -> dict:
    return {
        "line_id": line_id,
        "audio_bytes": silent_wav(seconds),
        "fmt": "wav",
        "character": "A",
        "text": "台词",
        "pause_after_ms": pause_ms,
        "audio_file": f"lines/{line_id}.wav",
    }


def test_wav_concat_without_ffmpeg():
    mixer = AudioMixer(ffmpeg=None)
    audio, segments, mode, fmt = mixer.synth_page_audio([
        make_line("a", 0.5, 100),
        make_line("b", 0.25, 0),
    ])

    assert mode == "single"
    assert fmt == "wav"
    assert audio and audio.startswith(b"RIFF")

    assert segments[0]["start_ms"] == 0
    assert segments[0]["end_ms"] == 500
    assert segments[1]["start_ms"] == 600       # 500ms + 100ms 停顿
    assert segments[1]["end_ms"] == 850


def test_measure_wav_duration():
    mixer = AudioMixer(ffmpeg=None)
    assert mixer.measure_duration_ms(silent_wav(1.0), "wav") == 1000


def test_mock_tts_duration_scales_with_text():
    tts = MockTTS()
    short = tts.synthesize("短", "voice")
    long = tts.synthesize("这是一句明显更长的台词" * 3, "voice")
    assert long.duration_ms > short.duration_ms
    assert short.audio_bytes.startswith(b"RIFF")


def test_mixed_format_falls_back_to_sequence():
    mixer = AudioMixer(ffmpeg=None)
    lines = [make_line("a", 0.2, 0)]
    lines.append({**make_line("b", 0.2, 0), "fmt": "mp3"})
    audio, segments, mode, _ = mixer.synth_page_audio(lines)
    assert mode == "sequence"
    assert audio is None
    assert segments[0]["order"] == 1