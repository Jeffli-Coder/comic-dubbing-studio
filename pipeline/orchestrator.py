"""
orchestrator — BookPipeline 状态机：OCR → 合并 → 选音 → TTS → 拼接 → ready。
只调用 Provider 抽象，磁盘动作全部走 store 模块；任何阶段失败落 error 可断点续跑。
"""
import shutil
import time
import traceback
from pathlib import Path

from config import QWEN_VOICES
from pipeline import store
from pipeline.audio import AudioMixer
from pipeline.stages import body_name, run_merge, run_voice_pick
from providers.base import BaseLLM, BaseTTS, BaseVision, PageScript

STAGES = ("queued", "ocr", "voice_pick", "tts", "concat", "ready")


class BookPipeline:
    def __init__(self, book_id: str, vision: BaseVision, llm: BaseLLM,
                 tts: BaseTTS, mixer: AudioMixer | None = None):
        self.book_id = book_id
        self.vision = vision
        self.llm = llm
        self.tts = tts
        self.mixer = mixer or AudioMixer()
        self.dir = store.book_dir(book_id)
        self.provider_name = getattr(tts, "name", "?")

    # ═══════════════════════════════════════════════════════
    # 元数据/进度
    # ═══════════════════════════════════════════════════════
    def _meta(self) -> dict:
        return store.read_meta(self.book_id)

    def _bump(self, **patch) -> dict:
        meta = self._meta()
        progress = dict(meta.get("progress") or {})
        if "progress" in patch:
            progress.update(patch.pop("progress"))
            patch["progress"] = progress
        return store.write_meta(self.book_id, patch)

    # ═══════════════════════════════════════════════════════
    # 主流程
    # ═══════════════════════════════════════════════════════
    def run(self) -> None:
        try:
            images = store.iter_page_images(self.book_id)
            if not images:
                raise FileNotFoundError("pages 目录没有可处理的图片")

            # 供应商切换守卫：tts_provider 变化时旧音频缓存不可用，清空重合成
            meta = self._meta()
            prev_provider = meta.get("tts_provider")
            if prev_provider and prev_provider != self.provider_name:
                for sub in ("lines", "audio", "timings"):
                    shutil.rmtree(self.dir / sub, ignore_errors=True)
                    (self.dir / sub).mkdir(parents=True, exist_ok=True)
                self._bump(error=None)

            total_lines = None
            self._bump(status="ocr", progress={
                "stage": "ocr", "page_done": 0, "page_total": len(images),
                "done": 0, "total": total_lines or 0,
            })

            # ── 1. 逐页视觉识别（pages_raw 断点续跑；单页失败跳过不中断整书）──
            page_scripts, known = [], set()
            ocr_failed = []
            for i, img in enumerate(images, start=1):
                page_num = i
                cached = store.read_json(self.dir / "pages_raw" / f"p{page_num:03d}.json")
                if cached and not cached.get("ocr_failed"):
                    raw = PageScript.from_dict(cached)      # 续跑：复用上次识别结果
                else:
                    ctx = {"characters": sorted(known)} if known else None
                    try:
                        raw = self.vision.analyze_page(
                            img.read_bytes(), page_num=page_num, prev_context=ctx)
                        store.write_json_atomic(
                            self.dir / "pages_raw" / f"p{page_num:03d}.json", raw.to_dict())
                    except Exception as e:
                        # 内容审核拦截 / 网络错误等：记为空台词页照常入册（页码完整），不中断整书；
                        # 标记 ocr_failed，下次重跑会重新尝试该页
                        ocr_failed.append(page_num)
                        raw = PageScript(
                            page_num=page_num, lines=[],
                            page_notes=f"视觉识别失败（已跳过）: {type(e).__name__}: {str(e)[:150]}")
                        store.write_json_atomic(
                            self.dir / "pages_raw" / f"p{page_num:03d}.json",
                            {**raw.to_dict(), "ocr_failed": True})

                page_scripts.append(PageScript(
                    page_num=page_num, lines=list(raw.lines),
                    page_notes=raw.page_notes or ""))
                for ln in raw.lines:
                    b = body_name(str(ln.character))
                    if b and b != "未知":
                        known.add(b)
                self._bump(progress={"stage": "ocr", "page_done": page_num})
            if ocr_failed:
                self._bump(ocr_failed_pages=ocr_failed)

            # ── 2. LLM 合并成按页脚本 ──
            script = run_merge(self.llm, page_scripts)
            script["book_id"] = self.book_id
            # 用真实落盘文件名回填图片路径：上传 PNG/WebP 时扩展名不是 .jpg，
            # 而 LLM/Mock 输出里通常写死 pages/001.jpg，不回填会导致阅读页 404。
            image_by_page = {i: f"pages/{p.name}" for i, p in enumerate(images, start=1)}
            for page in script.get("pages", []):
                page["image"] = image_by_page.get(page.get("page_num"), page.get("image") or "")
            store.write_json_atomic(self.dir / "script.json", script)
            self._bump(title=script["title"])   # 同步进 meta，书架卡片显示真实标题

            # ── 3. LLM 选音 ──
            self._bump(status="voice_pick", progress={"stage": "voice_pick"})
            assignments = run_voice_pick(self.llm, script["title"], script["characters"])
            script["voice_assignments"] = assignments
            store.write_json_atomic(self.dir / "script.json", script)

            # ── 4+5. 逐页推进：先合成该页台词，再拼接该页 → 每页处理完立即可播放 ──
            total_lines = sum(len(p["lines"]) for p in script["pages"])
            self._bump(status="tts", tts_provider=self.provider_name, progress={
                "stage": "tts", "done": 0, "total": total_lines,
                "page_done": 0, "page_total": len(script["pages"]),
            })
            done_lines = 0
            for page_idx, page in enumerate(script["pages"], start=1):
                for ln in page["lines"]:
                    self._synthesize_line(
                        ln, assignments.get(body_name(ln["character"]), QWEN_VOICES[0]["voice"]))
                    done_lines += 1
                    self._bump(progress={"stage": "tts", "done": done_lines})
                self._concat_pages([page], stage="concat", page_done=page_idx)

            self._bump(status="ready", progress={
                "stage": "ready", "done": total_lines, "total": total_lines,
            })
        except Exception as e:
            traceback.print_exc()
            self._bump(status="error", error=f"{type(e).__name__}: {e}")
            raise

    # ═══════════════════════════════════════════════════════
    # 换音色：只重合成该角色台词，重拼受影响页
    # ═══════════════════════════════════════════════════════
    def resynth_voice(self, character: str, new_voice: str) -> None:
        try:
            if new_voice not in {v["voice"] for v in QWEN_VOICES}:
                raise ValueError(f"不在 50 音色清单中: {new_voice}")
            script = store.read_script(self.book_id)
            if not script:
                raise ValueError("script.json 不存在")
            body = body_name(character)
            targets = [ln for p in script["pages"] for ln in p["lines"]
                       if body_name(ln["character"]) == body]
            if not targets:
                raise ValueError(f"没有找到角色 {character} 的台词")

            self._bump(status="resynth", progress={
                "stage": "tts", "done": 0, "total": len(targets),
            })
            for idx, ln in enumerate(targets):
                self._synthesize_line(ln, new_voice, force=True)   # 强制重合成，绕过缓存
                self._bump(progress={"stage": "tts", "done": idx + 1})

            affected = {p["page_num"] for p in script["pages"]
                        if any(body_name(line["character"]) == body for line in p["lines"])}
            pages_to_rebuild = [p for p in script["pages"] if p["page_num"] in affected]
            self._concat_pages(pages_to_rebuild, stage="concat")

            script["voice_assignments"][body] = new_voice
            store.write_json_atomic(self.dir / "script.json", script)
            self._bump(status="ready", progress={"stage": "ready"},
                       last_voice_swap={"character": body, "voice": new_voice})
        except Exception as e:
            traceback.print_exc()
            self._bump(status="error", error=f"{type(e).__name__}: {e}")
            raise

    # ═══════════════════════════════════════════════════════
    # 内部
    # ═══════════════════════════════════════════════════════
    def _line_file(self, line_id: str) -> tuple[Path | None, str]:
        """找已缓存的单句音频（断点续跑：任意扩展名）。"""
        if not self.dir.exists():
            return None, ""
        for p in (self.dir / "lines").glob(f"{line_id}.*"):
            return p, p.suffix.lstrip(".")
        return None, ""

    def _synthesize_line(self, ln: dict, voice: str, force: bool = False) -> Path:
        """单句合成（带重试）。已缓存则复用；force=True 时强制重新合成（换音色专用）。"""
        line_id = ln["line_id"]
        cached, ext = self._line_file(line_id)
        if cached is not None and not force:
            return cached

        text = ln.get("text", "")
        last_err = None
        for attempt in range(3):
            try:
                result = self.tts.synthesize(
                    text, voice,
                    speed=float(ln.get("speed", 1.0)),
                    emotion=str(ln.get("emotion", "")),
                    pitch=str(ln.get("pitch", "正常")),
                    emphasis=ln.get("emphasis"),
                )
                if not result.audio_bytes:
                    # 空音频多半是内容审核/配额/连接失败，写 0 字节文件会让下一阶段
                    # 报一个无关的 ffmpeg 错误，这里直接给出真实原因。
                    raise RuntimeError("TTS 返回空音频")
                fmt = result.fmt or "wav"
                out = self.dir / "lines" / f"{line_id}.{fmt}"
                out.write_bytes(result.audio_bytes)
                # 旧扩展名文件作废清理（换 provider / 格式变化时避免残留被复用）
                if ext and ext != fmt and (self.dir / "lines" / f"{line_id}.{ext}").exists():
                    (self.dir / "lines" / f"{line_id}.{ext}").unlink()
                return out
            except Exception as e:  # 指数退避重试
                last_err = e
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"合成失败 {line_id}: {last_err}")

    def _concat_pages(self, pages: list, stage: str, page_done: int | None = None) -> None:
        num_pages = sum(1 for _ in store.iter_page_images(self.book_id))
        for i, page in enumerate(pages, start=1):
            progress_done = page_done if page_done is not None else i
            page_num = page["page_num"]
            if not page["lines"]:
                # 无台词页（封面/目录被过滤）：不产出音频，仅写空时间戳占位
                store.write_json_atomic(
                    self.dir / "timings" / f"page_{page_num:03d}.json",
                    {"page_num": page_num, "mode": "single", "segments": []})
                self._bump(progress={"stage": stage, "page_done": progress_done, "page_total": num_pages})
                continue
            mix_input = []
            for ln in page["lines"]:
                path, ext = self._line_file(ln["line_id"])
                if path is None:
                    raise FileNotFoundError(f"缺少台词音频: {ln['line_id']}")
                mix_input.append({
                    "line_id": ln["line_id"],
                    "audio_bytes": path.read_bytes(),
                    "fmt": ext,
                    "character": ln.get("character", ""),
                    "text": ln.get("text", ""),
                    "pause_after_ms": int(ln.get("pause_after_ms", 0) or 0),
                    "audio_file": f"lines/{path.name}",
                })
            page_bytes, segments, mode, out_fmt = self.mixer.synth_page_audio(mix_input)

            page_num = page["page_num"]
            if mode == "single":
                audio_path = self.dir / "audio" / f"page_{page_num:03d}.{out_fmt}"
                audio_path.write_bytes(page_bytes)
                audio_file = f"audio/{audio_path.name}"
                timings = {
                    "page_num": page_num,
                    "audio_file": audio_file,
                    "mode": "single",
                }
            else:
                audio_file = None
                timings = {"page_num": page_num, "mode": "sequence"}
            timings["segments"] = segments
            store.write_json_atomic(
                self.dir / "timings" / f"page_{page_num:03d}.json", timings)
            self._bump(progress={"stage": stage, "page_done": progress_done, "page_total": num_pages})