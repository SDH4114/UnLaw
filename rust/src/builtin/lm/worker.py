"""MLX worker for `ul lm`, run by the Rust core inside one of its private venvs.

`worker.py serve` reads one JSON job per line on stdin and writes JSON events
on stdout; everything else (library prints, progress bars, warnings) goes to
stderr, which the core sends to worker.log. `worker.py hub <action>` runs the
Hugging Face side: search, pull, import from LM Studio and convert.

The core starts this file; editing it by hand is pointless because the core
rewrites it from its embedded copy.
"""

from __future__ import annotations

import base64
import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

# Protocol output gets the real stdout; anything printed by libraries goes to
# stderr so it can never corrupt the JSON stream.
_PROTOCOL = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8")
os.dup2(2, 1)
sys.stdout = sys.stderr

_WRITE_LOCK = threading.Lock()

CHAT_KINDS = {"text", "vision"}
KINDS = {"text", "vision", "embedding", "stt", "tts", "music", "image", "video"}


def emit(event: dict) -> None:
    line = json.dumps(event, ensure_ascii=False)
    with _WRITE_LOCK:
        _PROTOCOL.write(line + "\n")
        _PROTOCOL.flush()


class JobError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def read_json(path: str | os.PathLike) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def named_path(spec: dict) -> Path:
    """A symlink named after the repo: several libraries (mlx-audio, mflux)
    recognise the model family from the folder name, and a cache snapshot is
    only named by its commit hash."""
    ident = str(spec.get("id") or "model")
    target = Path(spec["path"])
    link = Path(tempfile.gettempdir()) / "ul-lm-links" / ident.replace("/", "--") / ident.rsplit("/", 1)[-1]
    try:
        if link.is_symlink() and os.readlink(link) == str(target):
            return link
        link.parent.mkdir(parents=True, exist_ok=True)
        temporary = link.with_name(link.name + f".{os.getpid()}")
        if temporary.is_symlink():
            temporary.unlink()
        temporary.symlink_to(target, target_is_directory=True)
        os.replace(temporary, link)
        return link
    except OSError:
        return target


# --------------------------------------------------------------------------
# Inputs


def image_file(source: str, scratch: list[str], allow_paths: bool) -> str:
    """Data URLs and raw base64 become temp files; local paths only when the
    job comes from the terminal (the HTTP API never reads arbitrary files)."""
    if source.startswith("file://"):
        source = source[7:]
    if source.startswith(("http://", "https://")):
        raise JobError("bad_image", "Remote image URLs are not fetched; send a data: URL or base64")
    if allow_paths and os.path.isfile(source):
        return source
    payload = source.split(",", 1)[1] if source.startswith("data:") else source
    try:
        data = base64.b64decode(payload, validate=True)
    except (ValueError, TypeError):
        hint = "a data: URL, base64" + (" or a local path" if allow_paths else "")
        raise JobError("bad_image", f"Image must be {hint}") from None
    if not data:
        raise JobError("bad_image", "Image data is empty")
    handle = tempfile.NamedTemporaryFile(prefix="ul-lm-", suffix=".img", delete=False)
    handle.write(data)
    handle.close()
    scratch.append(handle.name)
    return handle.name


# --------------------------------------------------------------------------
# Streaming text: content, reasoning (<think>) and tool calls, stop strings


class Splitter:
    """Route generated text to content, reasoning or tool-call buffers, holding
    back only the few characters that might be the start of a tag."""

    def __init__(self, think: tuple[str, str] | None, tool: tuple[str, str] | None, reasoning: bool) -> None:
        self.tags = {}
        if think and think[0] and think[1]:
            self.tags["think"] = think
        if tool and tool[0] and tool[1]:
            self.tags["tool"] = tool
        self.state = "reasoning" if reasoning else "content"
        self.pending = ""
        self.tool_text = ""
        self.tool_calls: list[str] = []

    def _closing(self) -> str | None:
        if self.state == "reasoning":
            return self.tags.get("think", ("", "</think>"))[1]
        if self.state == "tool":
            return self.tags["tool"][1]
        return None

    def _openings(self) -> list[tuple[str, str]]:
        found = []
        if "think" in self.tags:
            found.append((self.tags["think"][0], "reasoning"))
        if "tool" in self.tags:
            found.append((self.tags["tool"][0], "tool"))
        return found

    def feed(self, text: str, final: bool = False) -> list[tuple[str, str]]:
        """Return (channel, text) pieces ready to stream."""
        self.pending += text
        out: list[tuple[str, str]] = []
        while self.pending:
            closing = self._closing()
            candidates = [(closing, "content")] if closing else self._openings()
            best = None
            for tag, target in candidates:
                index = self.pending.find(tag)
                if index != -1 and (best is None or index < best[0]):
                    best = (index, tag, target)
            if best is not None:
                index, tag, target = best
                self._route(self.pending[:index], out)
                if self.state == "tool":
                    self.tool_calls.append(self.tool_text)
                    self.tool_text = ""
                self.pending = self.pending[index + len(tag):]
                self.state = target
                continue
            keep = 0
            if not final:
                for tag, _ in candidates:
                    for size in range(min(len(tag) - 1, len(self.pending)), 0, -1):
                        if tag.startswith(self.pending[-size:]):
                            keep = max(keep, size)
                            break
            ready, self.pending = self.pending[: len(self.pending) - keep], self.pending[len(self.pending) - keep:]
            self._route(ready, out)
            break
        if final and self.state == "tool" and self.tool_text:
            self.tool_calls.append(self.tool_text)
            self.tool_text = ""
        return out

    def _route(self, text: str, out: list[tuple[str, str]]) -> None:
        if not text:
            return
        if self.state == "tool":
            self.tool_text += text
        else:
            out.append((self.state, text))


class StopFilter:
    """Hold back content that could still become a stop string, so a stop
    sequence is never streamed to the client."""

    def __init__(self, stops: list[str]) -> None:
        self.stops = [stop for stop in stops if stop]
        self.held = ""
        self.hit = False

    def feed(self, text: str, final: bool = False) -> str:
        if not self.stops:
            return text
        if self.hit:
            return ""
        self.held += text
        positions = [self.held.find(stop) for stop in self.stops]
        hits = [index for index in positions if index != -1]
        if hits:
            self.hit = True
            ready, self.held = self.held[: min(hits)], ""
            return ready
        if final:
            ready, self.held = self.held, ""
            return ready
        keep = 0
        for stop in self.stops:
            for size in range(min(len(stop) - 1, len(self.held)), 0, -1):
                if stop.startswith(self.held[-size:]):
                    keep = max(keep, size)
                    break
        ready, self.held = self.held[: len(self.held) - keep], self.held[len(self.held) - keep:]
        return ready


# --------------------------------------------------------------------------
# Child processes for heavy one-shot generators (video, mflux images)

_PROGRESS = re.compile(r"(\d+)\s*/\s*(\d+)")


def run_child(ident: int, command: list[str], cancelled: set, env: dict | None = None) -> None:
    """Run a generator in its own process: progress bars become progress
    events, cancellation kills it, and its memory returns to macOS at exit."""
    print("running: " + " ".join(command), file=sys.stderr)
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**os.environ, **(env or {})},
    )
    import select

    tail: list[str] = []
    buffer = b""
    last = None
    descriptor = process.stdout.fileno()
    while True:
        if ident in cancelled:
            process.kill()
            process.wait()
            raise JobError("cancelled", "Cancelled")
        readable, _, _ = select.select([descriptor], [], [], 0.25)
        if not readable:
            continue
        chunk = os.read(descriptor, 65536)
        if not chunk:
            break
        sys.stderr.buffer.write(chunk)
        sys.stderr.flush()
        buffer += chunk
        *lines, buffer = re.split(rb"[\r\n]", buffer)
        for raw in lines:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            tail = (tail + [line])[-6:]
            match = _PROGRESS.search(line) if "%" in line or "it/s" in line or "s/it" in line or "step" in line.lower() else None
            if match:
                step, total = int(match.group(1)), int(match.group(2))
                if 0 < total < 100000 and (step, total) != last:
                    last = (step, total)
                    emit({"id": ident, "event": "progress", "step": step, "total": total})
    code = process.wait()
    if code != 0:
        detail = " | ".join(line for line in tail if "Traceback" not in line)[-600:]
        lowered = detail.lower()
        kind = "out_of_memory" if "memory" in lowered or code == -9 else "generation_failed"
        raise JobError(kind, f"The generator failed (exit {code}): {detail}")


# --------------------------------------------------------------------------
# Models


class Loaded:
    def __init__(self, ident: str, kind: str, path: str) -> None:
        self.id = ident
        self.kind = kind
        self.path = path
        self.model = None
        self.processor = None
        self.config = None
        self.generation = read_json(os.path.join(path, "generation_config.json"))
        # Text models: the KV cache of the last chat and the tokens it holds.
        self.cache = None
        self.cache_tokens: list[int] = []
        # Vision models: mlx-vlm keeps its own prefix cache.
        self.vision_cache = None


def _group(kind: str) -> str:
    return "chat" if kind in CHAT_KINDS else kind


def _whisper_format(path: str) -> bool:
    return not any(os.path.exists(os.path.join(path, name)) for name in ("preprocessor_config.json", "tokenizer.json", "tokenizer_config.json"))


def _packed_bonsai_image(path: str) -> bool:
    return os.path.isdir(os.path.join(path, "transformer-packed-mflux"))


class Engine:
    def __init__(self) -> None:
        # One model per group (chat, embedding, stt, tts, music, image) in this
        # process; the core runs separate processes for unrelated work.
        self.slots: dict[str, Loaded] = {}
        self.cancelled: set[int] = set()

    def loaded_ids(self) -> list[str]:
        return [slot.id for slot in self.slots.values()]

    def _free(self, group: str) -> None:
        if self.slots.pop(group, None) is not None:
            import gc

            import mlx.core as mx

            gc.collect()
            mx.clear_cache()

    def get(self, spec: dict) -> Loaded:
        ident, kind, path = spec.get("id"), spec.get("kind"), spec.get("path")
        if not ident or not path or kind not in KINDS:
            raise JobError("invalid_request", "Job has no runnable model")
        group = _group(kind)
        current = self.slots.get(group)
        if current is not None and current.id == ident:
            return current
        self._free(group)
        loaded = Loaded(ident, kind, path)
        trust = bool(spec.get("trust_remote_code"))
        started = time.time()
        try:
            self._load(loaded, spec, trust)
        except JobError:
            raise
        except ImportError as error:
            raise JobError("load_failed", f"{ident} needs a library the engine does not ship: {error}") from None
        except Exception as error:  # noqa: BLE001 - every loader failure becomes a clear job error
            raise JobError("load_failed", f"Could not load {ident}: {type(error).__name__}: {error}") from None
        print(f"loaded {ident} ({kind}) in {time.time() - started:.1f}s", file=sys.stderr)
        self.slots[group] = loaded
        emit({"loaded": self.loaded_ids()})
        return loaded

    def _load(self, loaded: Loaded, spec: dict, trust: bool) -> None:
        kind, path = loaded.kind, loaded.path
        if kind == "text":
            try:
                from mlx_lm import load

                loaded.model, loaded.processor = load(path, tokenizer_config={"trust_remote_code": trust})
                return
            except ValueError as error:
                # Some multimodal checkpoints are tagged text-generation but
                # only mlx-vlm knows their architecture.
                if "not supported" not in str(error).lower():
                    raise
                print(f"mlx-lm cannot load {loaded.id} ({error}); trying mlx-vlm", file=sys.stderr)
                loaded.kind = "vision"
        if loaded.kind == "vision":
            from mlx_vlm import load
            from mlx_vlm.generate.common import PromptCacheState
            from mlx_vlm.utils import load_config

            loaded.model, loaded.processor = load(path, trust_remote_code=trust)
            loaded.config = load_config(path)
            loaded.vision_cache = PromptCacheState()
        elif kind == "embedding":
            from mlx_embeddings.utils import load

            loaded.model, loaded.processor = load(path)
        elif kind == "stt":
            if _whisper_format(path):
                # Original MLX Whisper folders (config.json + weights only)
                # are run by mlx_whisper, which caches the model itself.
                import mlx_whisper  # noqa: F401
            else:
                from mlx_audio.stt.utils import load_model

                loaded.model = load_model(named_path(spec))
        elif kind == "tts":
            from mlx_audio.tts.utils import load_model

            loaded.model = load_model(named_path(spec))
        elif kind == "music":
            from mlx_audio.music.utils import load_model

            loaded.model = load_model(str(named_path(spec)))
        elif kind == "image" and _packed_bonsai_image(path):
            loaded.model = _load_bonsai_image(path)
        # Other image and video models run in a child process per job.

    def unload(self) -> None:
        self.slots.clear()
        import mlx.core as mx

        mx.clear_cache()
        emit({"loaded": []})

    # ----------------------------------------------------------------------
    # Chat and completion

    @staticmethod
    def _params(loaded: Loaded, job: dict) -> dict:
        """Request values win, then the model's own generation_config.json
        (its authors' recommended sampling), then the user's lm.* settings."""
        explicit = {key: value for key, value in (job.get("params") or {}).items() if value is not None}
        recommended = {
            key: loaded.generation[key]
            for key in ("temperature", "top_p", "top_k", "min_p", "repetition_penalty", "presence_penalty")
            if isinstance(loaded.generation.get(key), (int, float))
        }
        fallback = {key: value for key, value in (job.get("defaults") or {}).items() if value is not None}
        return {**fallback, **recommended, **explicit}

    @staticmethod
    def _sampling(params: dict):
        from mlx_lm.sample_utils import make_logits_processors, make_sampler

        sampler = make_sampler(
            temp=float(params.get("temperature", 0.7)),
            top_p=float(params.get("top_p") or 0.0),
            min_p=float(params.get("min_p") or 0.0),
            top_k=int(params.get("top_k") or 0),
        )
        processors = make_logits_processors(
            repetition_penalty=params.get("repetition_penalty"),
            presence_penalty=params.get("presence_penalty"),
            frequency_penalty=params.get("frequency_penalty"),
        )
        return sampler, processors

    @staticmethod
    def _template_kwargs(job: dict) -> dict:
        kwargs = {}
        if job.get("tools"):
            kwargs["tools"] = job["tools"]
        if job.get("think") is not None:
            kwargs["enable_thinking"] = bool(job["think"])
        return kwargs

    def _text_prompt(self, loaded: Loaded, job: dict) -> tuple[list[int], str]:
        tokenizer = loaded.processor
        if job.get("op") == "complete":
            prompt = str(job.get("prompt", ""))
            return tokenizer.encode(prompt), prompt
        messages = job.get("messages") or []
        if getattr(tokenizer, "chat_template", None):
            try:
                prompt = tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=False, **self._template_kwargs(job))
            except Exception as error:  # noqa: BLE001
                raise JobError("invalid_request", f"The chat template rejected the messages: {error}") from None
        else:
            prompt = "\n".join(f"{m.get('role')}: {m.get('content')}" for m in messages) + "\nassistant:"
        return tokenizer.encode(prompt, add_special_tokens=False), prompt

    @staticmethod
    def _reuse_cache(loaded: Loaded, tokens: list[int]) -> list[int]:
        """Keep the KV cache for the longest shared prefix; return the tokens
        that still have to be processed."""
        from mlx_lm.models.cache import can_trim_prompt_cache, make_prompt_cache, trim_prompt_cache

        common = 0
        for old, new in zip(loaded.cache_tokens, tokens):
            if old != new:
                break
            common += 1
        common = min(common, len(tokens) - 1)
        if loaded.cache is not None and common > 0 and can_trim_prompt_cache(loaded.cache):
            trim_prompt_cache(loaded.cache, len(loaded.cache_tokens) - common)
            return tokens[common:]
        loaded.cache = make_prompt_cache(loaded.model)
        return tokens

    @staticmethod
    def _starts_reasoning(prompt: str, think: tuple[str, str] | None) -> bool:
        # Templates of reasoning models often open <think> themselves.
        if not think:
            return False
        return prompt.rfind(think[0]) > prompt.rfind(think[1])

    def generate(self, job: dict) -> None:
        ident = job["id"]
        loaded = self.get(job.get("model") or {})
        if loaded.kind not in CHAT_KINDS:
            raise JobError("unsupported_model", f"{loaded.id} is a {loaded.kind} model; it cannot chat")
        params = self._params(loaded, job)
        max_tokens = int(params.get("max_tokens") or 4096)
        stops = StopFilter([s for s in (params.get("stop") or []) if isinstance(s, str)])
        if params.get("seed") is not None:
            import mlx.core as mx

            mx.random.seed(int(params["seed"]))
        scratch: list[str] = []
        started = time.time()
        text = ""
        reasoning = ""
        finish = "stop"
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        stats: dict = {}

        def send(channel: str, piece: str) -> None:
            nonlocal text, reasoning
            if channel == "content":
                piece = stops.feed(piece)
                text += piece
            else:
                reasoning += piece
            if piece:
                emit({"id": ident, "event": "token", "channel": channel, "text": piece})

        try:
            if loaded.kind == "text":
                stream, splitter, prompt_tokens = self._text_stream(loaded, job, params, max_tokens)
            else:
                stream, splitter, prompt_tokens = self._vision_stream(loaded, job, params, max_tokens, scratch)
            generated: list[int] = []
            for response in stream:
                if ident in self.cancelled:
                    finish = "cancelled"
                    break
                token = getattr(response, "token", None)
                if token is not None:
                    generated.append(int(token))
                # The whole prompt, even when the cache spared recomputing most of it.
                usage["prompt_tokens"] = prompt_tokens or int(getattr(response, "prompt_tokens", 0) or 0)
                usage["completion_tokens"] = int(getattr(response, "generation_tokens", 0) or len(generated))
                stats = {
                    "prompt_tps": round(float(getattr(response, "prompt_tps", 0) or 0), 1),
                    "generation_tps": round(float(getattr(response, "generation_tps", 0) or 0), 1),
                    "peak_memory_gb": round(float(getattr(response, "peak_memory", 0) or 0), 2),
                }
                for channel, piece in splitter.feed(response.text or ""):
                    send(channel, piece)
                if stops.hit:
                    finish = "stop"
                    break
                if getattr(response, "finish_reason", None):
                    finish = response.finish_reason
            for channel, piece in splitter.feed("", final=True):
                send(channel, piece)
            tail = stops.feed("", final=True)
            if tail:
                text += tail
                emit({"id": ident, "event": "token", "channel": "content", "text": tail})
            if loaded.kind == "text" and loaded.cache is not None:
                # The cache holds exactly `offset` tokens (the last sampled
                # token may not have been fed back); trust it, not our count.
                offset = getattr(loaded.cache[0], "offset", None)
                full = loaded.cache_tokens + generated
                if isinstance(offset, int) and 0 < offset <= len(full):
                    loaded.cache_tokens = full[:offset]
                else:
                    loaded.cache = None
                    loaded.cache_tokens = []
            tool_calls = self._tool_calls(loaded, splitter, job.get("tools"))
            if tool_calls and finish == "stop":
                finish = "tool_calls"
        except Exception:
            # The cache may hold a half-processed prompt; start clean next time.
            loaded.cache = None
            loaded.cache_tokens = []
            if loaded.vision_cache is not None:
                from mlx_vlm.generate.common import PromptCacheState

                loaded.vision_cache = PromptCacheState()
            raise
        finally:
            for path in scratch:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            self.cancelled.discard(ident)
        emit(
            {
                "id": ident,
                "event": "done",
                "model": loaded.id,
                "text": text,
                "reasoning": reasoning,
                "tool_calls": tool_calls,
                "finish_reason": finish,
                "usage": usage,
                "stats": {**stats, "seconds": round(time.time() - started, 2)},
            }
        )

    def _text_stream(self, loaded: Loaded, job: dict, params: dict, max_tokens: int):
        from mlx_lm import stream_generate

        tokenizer = loaded.processor
        tokens, prompt = self._text_prompt(loaded, job)
        if not tokens:
            raise JobError("invalid_request", "The prompt is empty")
        remaining = self._reuse_cache(loaded, tokens)
        loaded.cache_tokens = tokens
        sampler, processors = self._sampling(params)
        think = (tokenizer.think_start, tokenizer.think_end) if getattr(tokenizer, "has_thinking", False) else None
        tool = None
        if getattr(tokenizer, "has_tool_calling", False) and job.get("tools"):
            tool = (tokenizer.tool_call_start, tokenizer.tool_call_end)
        kv_bits = params.get("kv_bits")
        stream = stream_generate(
            loaded.model,
            tokenizer,
            remaining,
            max_tokens=max_tokens,
            sampler=sampler,
            logits_processors=processors,
            prompt_cache=loaded.cache,
            **({"kv_bits": int(kv_bits), "kv_group_size": 64} if kv_bits else {}),
        )
        return stream, Splitter(think, tool, self._starts_reasoning(prompt, think)), len(tokens)

    def _vision_stream(self, loaded: Loaded, job: dict, params: dict, max_tokens: int, scratch: list[str]):
        from mlx_vlm import stream_generate
        from mlx_vlm.prompt_utils import apply_chat_template

        allow_paths = bool(job.get("local"))
        messages = job.get("messages") or []
        images = [image_file(source, scratch, allow_paths) for message in messages for source in message.get("images") or []]
        plain = [{"role": m.get("role", "user"), "content": m.get("content") or ""} for m in messages]
        if job.get("op") == "complete":
            plain = [{"role": "user", "content": str(job.get("prompt", ""))}]
        kwargs = self._template_kwargs(job)
        kwargs.pop("tools", None)
        try:
            prompt = apply_chat_template(loaded.processor, loaded.config, plain, num_images=len(images), **kwargs)
        except TypeError:
            prompt = apply_chat_template(loaded.processor, loaded.config, plain, num_images=len(images))
        sampling = {
            key: params[key]
            for key in ("temperature", "top_p", "top_k", "min_p", "repetition_penalty", "presence_penalty", "frequency_penalty")
            if params.get(key) is not None
        }
        stream = stream_generate(
            loaded.model,
            loaded.processor,
            prompt,
            image=images or None,
            max_tokens=max_tokens,
            prompt_cache_state=loaded.vision_cache,
            **sampling,
        )
        think = ("<think>", "</think>")
        tool_start = getattr(getattr(loaded.processor, "tokenizer", loaded.processor), "tool_call_start", None)
        tool = (tool_start, "</tool_call>") if tool_start and job.get("tools") else None
        return stream, Splitter(think, tool, self._starts_reasoning(prompt, think)), 0

    @staticmethod
    def _tool_calls(loaded: Loaded, splitter: Splitter, tools) -> list[dict]:
        tokenizer = getattr(loaded.processor, "tokenizer", loaded.processor)
        parser = getattr(loaded.processor, "tool_parser", None) or getattr(tokenizer, "tool_parser", None)
        calls = []
        for text in splitter.tool_calls:
            parsed = None
            if parser is not None:
                try:
                    parsed = parser(text, tools)
                except (ValueError, json.JSONDecodeError) as error:
                    print(f"tool call not parsed: {error}", file=sys.stderr)
            if parsed is None:
                try:
                    parsed = json.loads(text)
                except ValueError:
                    continue
            for call in parsed if isinstance(parsed, list) else [parsed]:
                if not isinstance(call, dict):
                    continue
                arguments = call.get("arguments", call.get("parameters", {}))
                calls.append(
                    {
                        "id": call.get("id") or f"call_{uuid.uuid4().hex[:24]}",
                        "type": "function",
                        "function": {
                            "name": call.get("name", ""),
                            "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False),
                        },
                    }
                )
        return calls

    # ----------------------------------------------------------------------
    # Embeddings and speech recognition

    def embed(self, job: dict) -> None:
        import mlx.core as mx
        from mlx_embeddings.utils import generate

        loaded = self.get(job.get("model") or {})
        if loaded.kind != "embedding":
            raise JobError("unsupported_model", f"{loaded.id} is a {loaded.kind} model; embeddings need an embedding model")
        texts = job.get("input")
        texts = [texts] if isinstance(texts, str) else list(texts or [])
        if not texts or not all(isinstance(text, str) for text in texts):
            raise JobError("invalid_request", "input must be a string or a list of strings")
        vectors: list[list[float]] = []
        tokens = 0
        for start in range(0, len(texts), 32):
            batch = texts[start : start + 32]
            output = generate(loaded.model, loaded.processor, texts=batch, max_length=int(job.get("max_length", 512)))
            embeds = getattr(output, "text_embeds", None)
            if embeds is None:
                hidden = output.last_hidden_state
                embeds = mx.mean(hidden, axis=1)
                embeds = embeds / mx.linalg.norm(embeds, axis=-1, keepdims=True)
            vectors.extend(embeds.astype(mx.float32).tolist())
            tokens += sum(len(loaded.processor.encode(text)) for text in batch)
        emit({"id": job["id"], "event": "done", "model": loaded.id, "embeddings": vectors, "usage": {"prompt_tokens": tokens}})

    def transcribe(self, job: dict) -> None:
        loaded = self.get(job.get("model") or {})
        if loaded.kind != "stt":
            raise JobError("unsupported_model", f"{loaded.id} is a {loaded.kind} model; transcription needs a speech-to-text model like Whisper")
        path = job.get("path")
        if not path or not os.path.isfile(path):
            raise JobError("invalid_request", "Audio file not found")
        started = time.time()
        # Greedy decoding without conditioning on earlier text: sampling at
        # higher temperatures makes small Whisper models hallucinate.
        whisper_options = {"condition_on_previous_text": False, "temperature": 0.0}
        language = job.get("language") or None
        try:
            if loaded.model is None:
                import mlx_whisper
                from mlx_audio.stt.utils import load_audio

                result = mlx_whisper.transcribe(load_audio(path, 16000), path_or_hf_repo=loaded.path, language=language, **whisper_options)
            else:
                try:
                    result = loaded.model.generate(path, language=language, **whisper_options)
                except TypeError:
                    # Non-Whisper recognisers (Parakeet, Qwen3-ASR...) take fewer options.
                    result = loaded.model.generate(path, **({"language": language} if language else {}))
        except (OSError, RuntimeError) as error:
            raise JobError("invalid_request", f"Could not read the audio: {error}") from None
        text = result.get("text", "") if isinstance(result, dict) else getattr(result, "text", "")
        detected = result.get("language") if isinstance(result, dict) else getattr(result, "language", None)
        segments = result.get("segments") if isinstance(result, dict) else getattr(result, "segments", None)
        timeline = []
        for segment in segments or []:
            if isinstance(segment, dict) and "start" in segment:
                timeline.append({"start": round(float(segment["start"]), 2), "end": round(float(segment.get("end", 0)), 2), "text": str(segment.get("text", "")).strip()})
        emit({"id": job["id"], "event": "done", "model": loaded.id, "text": (text or "").strip(), "language": detected,
              "segments": timeline, "stats": {"seconds": round(time.time() - started, 2)}})

    # ----------------------------------------------------------------------
    # Generated media: speech, music, images, video

    @staticmethod
    def _write_audio(chunks: list, sample_rate: int, output: str) -> float:
        import mlx.core as mx
        import numpy as np
        from mlx_audio.audio_io import write

        if not chunks:
            raise JobError("generation_failed", "The model produced no audio")
        audio = chunks[0] if len(chunks) == 1 else mx.concatenate(chunks, axis=0)
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        write(output, np.array(audio), sample_rate)
        return round(audio.shape[0] / sample_rate, 2)

    def speak(self, job: dict) -> None:
        loaded = self.get(job.get("model") or {})
        if loaded.kind != "tts":
            raise JobError("unsupported_model", f"{loaded.id} is a {loaded.kind} model; speech needs a text-to-speech model")
        text = str(job.get("text") or "").strip()
        if not text:
            raise JobError("invalid_request", "Nothing to say")
        model = loaded.model
        voices = model.get_supported_speakers() if hasattr(model, "get_supported_speakers") else []
        voice = job.get("voice") or None
        if voice and voices and voice.lower() not in [v.lower() for v in voices]:
            raise JobError("invalid_request", f"Unknown voice '{voice}'; this model has: {', '.join(voices)}")
        if not voice and voices:
            voice = voices[0]
        options = {"text": text, "speed": float(job.get("speed") or 1.0)}
        if voice:
            options["voice"] = voice
        if job.get("language"):
            options["lang_code"] = job["language"]
        if job.get("instructions"):
            options["instruct"] = job["instructions"]
        started = time.time()
        chunks, sample_rate = [], 24000
        for index, result in enumerate(model.generate(**options)):
            if job["id"] in self.cancelled:
                raise JobError("cancelled", "Cancelled")
            chunks.append(result.audio)
            sample_rate = result.sample_rate
            emit({"id": job["id"], "event": "progress", "step": index + 1, "total": 0})
        seconds = self._write_audio(chunks, sample_rate, job["output"])
        emit({"id": job["id"], "event": "done", "model": loaded.id, "path": job["output"], "voice": voice, "voices": voices,
              "audio_seconds": seconds, "stats": {"seconds": round(time.time() - started, 2)}})

    def music(self, job: dict) -> None:
        loaded = self.get(job.get("model") or {})
        if loaded.kind != "music":
            raise JobError("unsupported_model", f"{loaded.id} is a {loaded.kind} model; songs need a music model")
        options = {"text": str(job.get("prompt") or ""), "lyrics": str(job.get("lyrics") or "").strip() or "[instrumental]", "steps": int(job.get("steps") or 30),
                   "seed": int(job.get("seed") or 0)}
        if job.get("duration"):
            options["duration"] = float(job["duration"])
        started = time.time()
        chunks, sample_rate = [], 44100
        for result in loaded.model.generate(**options):
            if job["id"] in self.cancelled:
                raise JobError("cancelled", "Cancelled")
            chunks.append(result.audio)
            sample_rate = result.sample_rate
        seconds = self._write_audio(chunks, sample_rate, job["output"])
        emit({"id": job["id"], "event": "done", "model": loaded.id, "path": job["output"], "audio_seconds": seconds,
              "stats": {"seconds": round(time.time() - started, 2)}})

    def image(self, job: dict) -> None:
        spec = job.get("model") or {}
        loaded = self.get(spec)
        if loaded.kind != "image":
            raise JobError("unsupported_model", f"{loaded.id} is a {loaded.kind} model; pictures need an image model")
        prompt = str(job.get("prompt") or "").strip()
        if not prompt:
            raise JobError("invalid_request", "The prompt is empty")
        width, height = int(job.get("width") or 1024), int(job.get("height") or 1024)
        width, height = max(64, width // 16 * 16), max(64, height // 16 * 16)
        seed = int(job["seed"]) if job.get("seed") is not None else int.from_bytes(os.urandom(3), "big")
        output = job["output"]
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        started = time.time()
        if loaded.model is not None:
            generated = loaded.model.generate_image(
                seed=seed,
                prompt=prompt,
                num_inference_steps=int(job.get("steps") or 4),
                height=height,
                width=width,
                guidance=1.0,
            )
            generated.image.save(output)
        else:
            command = _mflux_command(spec, loaded.path, job, prompt, width, height, seed, output)
            run_child(job["id"], command, self.cancelled, {"HF_HUB_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false"})
        if not os.path.isfile(output):
            raise JobError("generation_failed", "The image model wrote no file")
        emit({"id": job["id"], "event": "done", "model": loaded.id, "path": output, "seed": seed, "width": width, "height": height,
              "stats": {"seconds": round(time.time() - started, 2)}})

    def video(self, job: dict) -> None:
        spec = job.get("model") or {}
        loaded = self.get(spec)
        if loaded.kind != "video":
            raise JobError("unsupported_model", f"{loaded.id} is a {loaded.kind} model; clips need a video model")
        prompt = str(job.get("prompt") or "").strip()
        if not prompt:
            raise JobError("invalid_request", "The prompt is empty")
        output = job["output"]
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        family = _video_family(loaded.path, loaded.id)
        width = max(64, int(job.get("width") or (832 if family == "wan" else 704)) // 32 * 32)
        height = max(64, int(job.get("height") or (480 if family == "wan" else 512)) // 32 * 32)
        frames = int(job.get("frames") or (49 if family == "wan" else 97))
        frames = max(9, (frames - 1) // (4 if family == "wan" else 8) * (4 if family == "wan" else 8) + 1)
        seed = int(job["seed"]) if job.get("seed") is not None else int.from_bytes(os.urandom(3), "big")
        if family == "wan":
            command = [sys.executable, "-m", "mlx_video.models.wan_2.generate", "--model-dir", loaded.path, "--prompt", prompt,
                       "--width", str(width), "--height", str(height), "--num-frames", str(frames), "--seed", str(seed), "--output-path", output]
            if job.get("image"):
                command += ["--image", job["image"]]
        else:
            encoder = next((os.path.join(loaded.path, name) for name in sorted(os.listdir(loaded.path))
                            if os.path.isdir(os.path.join(loaded.path, name)) and name.lower().startswith("gemma")), None)
            command = [sys.executable, "-m", "mlx_video.models.ltx_2.generate", "--model-repo", loaded.path, "--prompt", prompt,
                       "--width", str(width), "--height", str(height), "--num-frames", str(frames), "--seed", str(seed), "--output-path", output]
            if encoder:
                command += ["--text-encoder-repo", encoder]
            if job.get("image"):
                command += ["--image", job["image"]]
        if job.get("steps"):
            command += ["--steps", str(int(job["steps"]))]
        started = time.time()
        run_child(job["id"], command, self.cancelled, {"HF_HUB_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false"})
        if not os.path.isfile(output):
            raise JobError("generation_failed", "The video model wrote no file")
        emit({"id": job["id"], "event": "done", "model": loaded.id, "path": output, "seed": seed, "width": width, "height": height,
              "frames": frames, "stats": {"seconds": round(time.time() - started, 2)}})


# --------------------------------------------------------------------------
# Image and video model families


def _video_family(path: str, ident: str) -> str:
    names = set(os.listdir(path))
    lowered = ident.lower()
    if "t5_encoder.safetensors" in names or "wan" in lowered or str(read_json(os.path.join(path, "config.json")).get("model_type", "")).startswith("wan"):
        return "wan"
    if "connector.safetensors" in names or "embedded_config.json" in names or "ltx" in lowered:
        return "ltx"
    raise JobError("unsupported_model", f"{ident} is not a Wan or LTX video model, the families mlx-video runs")


# mflux generators by registry key prefix (longest prefix wins).
_MFLUX_COMMANDS = {
    "flux2-klein": "mflux-generate-flux2",
    "flux3": "mflux-generate-flux3",
    "dev": "mflux-generate",
    "schnell": "mflux-generate",
    "krea-dev": "mflux-generate",
    "krea-2": "mflux-generate-krea2",
    "qwen-image-2.1": "mflux-generate-qwen-2.1",
    "qwen-image": "mflux-generate-qwen",
    "z-image-turbo": "mflux-generate-z-image-turbo",
    "z-image": "mflux-generate-z-image",
    "fibo": "mflux-generate-fibo",
    "ernie-image-turbo": "mflux-generate-ernie-image-turbo",
    "ernie-image": "mflux-generate-ernie-image",
    "boogu": "mflux-generate-boogu",
    "ming": "mflux-generate-ming",
    "lens": "mflux-generate-lens",
    "ideogram": "mflux-generate-ideogram4",
}

_PIPELINE_KEYS = {
    "Flux2KleinPipeline": "flux2-klein-4b",
    "FluxPipeline": "dev",
    "QwenImagePipeline": "qwen-image",
    "ZImagePipeline": "z-image",
}


def _readme_base_models(path: str) -> list[str]:
    try:
        text = Path(path, "README.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if not text.startswith("---"):
        return []
    header = text.split("---", 2)[1]
    found = re.findall(r"^\s*-\s*([\w.-]+/[\w.-]+)\s*$", header, flags=re.M)
    found += re.findall(r"^base_model:\s*([\w.-]+/[\w.-]+)\s*$", header, flags=re.M)
    return found


def mflux_key(ident: str, path: str) -> str:
    """The mflux registry entry a checkpoint is built on."""
    from mflux.models.common.config.model_config import AVAILABLE_MODELS
    from mflux.models.common.resolution.config_resolution import ConfigResolution

    by_repo = {}
    for key, config in AVAILABLE_MODELS.items():
        by_repo.setdefault(config.model_name.lower(), key)
    for name in [ident] + _readme_base_models(path):
        if name.lower() in by_repo:
            return by_repo[name.lower()]
    normalized = ident.rsplit("/", 1)[-1].lower().replace("flux.2", "flux2").replace("flux.1-", "").replace("flux.1", "")
    inferred = ConfigResolution._infer_from_name(normalized, list(AVAILABLE_MODELS.values()))
    if inferred is not None:
        return next(key for key, config in AVAILABLE_MODELS.items() if config is inferred)
    pipeline = read_json(os.path.join(path, "model_index.json")).get("_class_name", "")
    key = _PIPELINE_KEYS.get(pipeline)
    if key == "dev" and "schnell" in ident.lower():
        key = "schnell"
    if key == "z-image" and "turbo" in ident.lower():
        key = "z-image-turbo"
    if key is None:
        raise JobError("unsupported_model", f"mflux does not know which model {ident} is based on (FLUX, Qwen-Image, Z-Image...)")
    return key


def _mflux_command(spec: dict, path: str, job: dict, prompt: str, width: int, height: int, seed: int, output: str) -> list[str]:
    key = mflux_key(str(spec.get("id")), path)
    command = next((cmd for prefix, cmd in sorted(_MFLUX_COMMANDS.items(), key=lambda item: -len(item[0])) if key.startswith(prefix)), None)
    if command is None:
        raise JobError("unsupported_model", f"{spec.get('id')} ({key}) has no text-to-image generator in mflux")
    binary = os.path.join(os.path.dirname(sys.executable), command)
    args = [binary, "--model", str(named_path(spec)), "--base-model", key, "--prompt", prompt, "--width", str(width),
            "--height", str(height), "--seed", str(seed), "--output", output]
    if job.get("steps"):
        args += ["--steps", str(int(job["steps"]))]
    if job.get("quantize"):
        args += ["--quantize", str(int(job["quantize"]))]
    if job.get("image"):
        args += ["--image", job["image"], str(float(job.get("strength") or 0.6))]
    return args


def _load_bonsai_image(path: str):
    """Bonsai Image (FLUX.2 Klein, ternary/binary) through PrismML's mflux fork:
    its fused low-bit transformer plus the bundled 4-bit Qwen3 text encoder.
    The text-encoder swap follows PrismML image-studio (Apache-2.0)."""
    import mlx.core as mx
    import mlx.nn as nn
    from mlx.utils import tree_unflatten
    from mflux.models.flux2.flux2_initializer import Flux2Initializer
    from mflux.models.flux2.model.flux2_text_encoder.qwen3_text_encoder import Qwen3TextEncoder
    from mflux.models.flux2.variants import Flux2Klein

    def load_text_encoder(overrides: dict, model_path: str):
        root = Path(model_path) / "text_encoder-mlx-4bit"
        raw = mx.load(str(root / "model.safetensors"))
        nested = tree_unflatten([(key[len("model."):], value) for key, value in raw.items() if key.startswith("model.")])
        encoder = Qwen3TextEncoder(**overrides)
        nn.quantize(encoder, class_predicate=lambda _, module: hasattr(module, "to_quantized"), bits=4, group_size=64)
        encoder.update(nested)
        return encoder

    original = Flux2Initializer.reload_text_encoder

    def reload_text_encoder(model) -> None:
        model_path = getattr(model, "_model_path", None) or path
        if (Path(model_path) / "text_encoder-mlx-4bit" / "model.safetensors").is_file():
            model.text_encoder = load_text_encoder(model.model_config.text_encoder_overrides, model_path)
        else:
            original(model)

    Flux2Initializer.reload_text_encoder = staticmethod(reload_text_encoder)

    # Slim packs ship `transformer-packed-mflux/` instead of `transformer/`,
    # which the stock loader scans for first; build both parts directly.
    from mflux.models.common.resolution.path_resolution import PathResolution
    from mflux.models.common.weights.loading.loaded_weights import LoadedWeights, MetaData
    from mflux.models.common.weights.loading.weight_applier import WeightApplier
    from mflux.models.common.weights.loading.weight_loader import WeightLoader
    from mflux.models.flux2.flux2_initializer import FULL_DECODER_CHANNELS
    from mflux.models.flux2.model.flux2_vae.vae import Flux2VAE
    from mflux.models.flux2.weights.flux2_weight_definition import Flux2KleinWeightDefinition

    original_load = Flux2Initializer.load_transformer_and_vae

    def load_transformer_and_vae(model) -> None:
        root_path = Path(getattr(model, "_model_path", None) or path)
        if (root_path / "transformer").exists() or not (root_path / "transformer-packed-mflux").exists():
            original_load(model)
            return
        if model.vae is None:
            model.vae = Flux2VAE(decoder_block_out_channels=FULL_DECODER_CHANNELS)
            root = PathResolution.resolve(path=str(root_path), patterns=Flux2KleinWeightDefinition.get_download_patterns())
            component = next(c for c in Flux2KleinWeightDefinition.get_components() if c.name == "vae")
            weights, _, _ = WeightLoader._load_component(root, component)
            WeightApplier.apply_and_quantize(
                weights=LoadedWeights(components={"vae": weights}, meta_data=MetaData(quantization_level=None, mflux_version=None)),
                quantize_arg=model._quantize_arg,
                weight_definition=Flux2KleinWeightDefinition,
                models={"vae": model.vae},
            )
        if model.transformer is None:
            Flux2Initializer._load_klein_fast_transformer_weights(model, str(root_path), precision=model._klein_fast_precision)
        mx.clear_cache()

    Flux2Initializer.load_transformer_and_vae = staticmethod(load_transformer_and_vae)
    manifest = read_json(os.path.join(path, "transformer-packed-mflux", "quantization_config.json"))
    bits = manifest.get("bits") or (1 if "binary" in path.lower() else 2)
    precision = "1bit" if int(bits) == 1 else "2bit"
    return Flux2Klein(
        model_path=path,
        use_klein_fast_transformer=True,
        klein_fast_precision=precision,
        vae_variant="full",
        evict_text_encoder=True,
    )


# --------------------------------------------------------------------------
# Serve loop


def serve() -> int:
    engine = Engine()
    jobs: list[dict] = []
    ready = threading.Condition()

    def reader() -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                job = json.loads(line)
            except json.JSONDecodeError:
                continue
            with ready:
                if job.get("op") == "cancel":
                    engine.cancelled.add(job.get("target"))
                else:
                    jobs.append(job)
                ready.notify()
        # The core is gone: exit without waiting for a long generation.
        os._exit(0)

    threading.Thread(target=reader, daemon=True).start()
    import mlx.core as mx

    # MLX keeps freed buffers for reuse; unbounded, that cache pushes a 16-18 GB
    # Mac into swap after a few images. A modest cache keeps chat fast.
    try:
        total = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout.strip() or 0)
    except (OSError, ValueError):
        total = 0
    mx.set_cache_limit(max(1 << 30, total // 16) if total else 2 << 30)
    emit({"event": "ready", "mlx": mx.__version__})
    handlers = {
        "chat": engine.generate,
        "complete": engine.generate,
        "embed": engine.embed,
        "transcribe": engine.transcribe,
        "speak": engine.speak,
        "music": engine.music,
        "image": engine.image,
        "video": engine.video,
    }
    while True:
        with ready:
            while not jobs:
                ready.wait()
            job = jobs.pop(0)
        ident = job.get("id")
        if ident in engine.cancelled:
            engine.cancelled.discard(ident)
            emit({"id": ident, "event": "done", "text": "", "finish_reason": "cancelled", "usage": {}})
            continue
        try:
            op = job.get("op")
            if op in handlers:
                handlers[op](job)
            elif op == "load":
                engine.get(job.get("model") or {})
                emit({"id": ident, "event": "done", "loaded": engine.loaded_ids()})
            elif op == "unload":
                engine.unload()
                emit({"id": ident, "event": "done"})
            elif op == "ping":
                emit({"id": ident, "event": "done", "loaded": engine.loaded_ids()})
            else:
                raise JobError("invalid_request", f"Unknown operation: {op}")
        except JobError as error:
            if error.code == "cancelled":
                emit({"id": ident, "event": "done", "text": "", "finish_reason": "cancelled", "usage": {}})
            else:
                emit({"id": ident, "event": "error", "code": error.code, "message": str(error)})
        except ImportError as error:
            # Optional extras of one model family (Kokoro's misaki, ...).
            missing = str(error).split(". Install", 1)[0]
            emit({"id": ident, "event": "error", "code": "unsupported_model",
                  "message": f"{missing}; the engine does not include it. Use another model of the same kind "
                             "(for speech: mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit, which also speaks Russian)"})
        except MemoryError:
            engine.unload()
            emit({"id": ident, "event": "error", "code": "out_of_memory", "message": "Out of memory; the model was unloaded"})
        except Exception as error:  # noqa: BLE001 - one bad job must not stop the worker
            import traceback

            traceback.print_exc()
            message = f"{type(error).__name__}: {error}"
            code = "out_of_memory" if "memory" in message.lower() else "generation_failed"
            emit({"id": ident, "event": "error", "code": code, "message": message})
        finally:
            engine.cancelled.discard(ident)
            if job.get("op") in {"image", "video", "music", "speak", "transcribe"}:
                # Media jobs leave large scratch buffers; give them back now.
                import gc

                gc.collect()
                mx.clear_cache()


# --------------------------------------------------------------------------
# Hugging Face hub: search, pull, import, convert


def _result(value) -> None:
    emit({"result": value})


def _human(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"


def hub_search(query: str, limit: int, mlx_only: bool, task: str | None) -> int:
    from huggingface_hub import HfApi

    api = HfApi()
    kwargs = {"search": query, "sort": "downloads", "limit": limit, "expand": ["downloads", "likes", "library_name", "pipeline_tag", "tags", "lastModified"]}
    if mlx_only:
        kwargs["filter"] = "mlx"
    if task:
        kwargs["pipeline_tag"] = task
    rows = []
    for info in api.list_models(**kwargs):
        tags = list(getattr(info, "tags", None) or [])
        rows.append(
            {
                "id": info.id,
                "downloads": getattr(info, "downloads", 0) or 0,
                "likes": getattr(info, "likes", 0) or 0,
                "task": getattr(info, "pipeline_tag", None) or "",
                "mlx": getattr(info, "library_name", None) == "mlx" or "mlx" in tags,
                "gguf": "gguf" in tags,
            }
        )
    _result(rows)
    return 0


def hub_pull(repo: str, include: list[str], revision: str | None, cache: str) -> int:
    import shutil

    from huggingface_hub import HfApi, snapshot_download
    from huggingface_hub.errors import GatedRepoError, RepositoryNotFoundError, RevisionNotFoundError

    try:
        info = HfApi().model_info(repo, revision=revision, files_metadata=True)
    except GatedRepoError:
        print(f"{repo} is gated: accept its license on huggingface.co and log in with `hf auth login`", file=sys.stderr)
        return 3
    except RepositoryNotFoundError:
        print(f"{repo} was not found on Hugging Face (private repos need `hf auth login`)", file=sys.stderr)
        return 4
    except RevisionNotFoundError:
        print(f"{repo} has no revision {revision}", file=sys.stderr)
        return 4
    files = [(sibling.rfilename, sibling.size or 0) for sibling in info.siblings or []]
    if include:
        files = [(name, size) for name, size in files if any(fnmatch.fnmatch(name, pattern) for pattern in include)]
        if not files:
            print(f"No file in {repo} matches {', '.join(include)}", file=sys.stderr)
            return 5
    ggufs = [(name, size) for name, size in files if name.endswith(".gguf")]
    weights = [name for name, _ in files if name.endswith(".safetensors")]
    if not include and len(ggufs) > 1 and not weights:
        print(f"{repo} holds {len(ggufs)} GGUF files; pick one with --include, for example:", file=sys.stderr)
        for name, size in sorted(ggufs, key=lambda item: item[1])[:12]:
            print(f"  ul lm pull {repo} --include '{name}'   ({_human(size)})", file=sys.stderr)
        return 6
    total = sum(size for _, size in files)
    os.makedirs(cache, exist_ok=True)
    free = shutil.disk_usage(cache).free
    if total > free - (1 << 30):
        print(f"{repo} needs {_human(total)} but only {_human(free)} is free in {cache}", file=sys.stderr)
        return 7
    print(f"{len(files)} files, {_human(total)}", file=sys.stderr)
    patterns = include or None
    path = snapshot_download(repo, revision=revision, allow_patterns=patterns)
    _result({"path": path, "bytes": total, "task": info.pipeline_tag or "", "library": info.library_name or ""})
    return 0


def _git_blob_sha1(path: str) -> str:
    import hashlib

    digest = hashlib.sha1()
    digest.update(f"blob {os.path.getsize(path)}\0".encode())
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256(path: str) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 22), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _move(source: str, destination: str) -> None:
    import shutil

    os.makedirs(os.path.dirname(destination), exist_ok=True)
    try:
        os.replace(source, destination)
    except OSError:
        shutil.copy2(source, destination)
        os.unlink(source)


def hub_import(source_root: str, cache: str, local_root: str, dry_run: bool) -> int:
    """Move LM Studio model folders into the hub cache layout, verified
    against the repo's real file hashes; mismatches are re-downloaded."""
    import shutil

    from huggingface_hub import HfApi, hf_hub_download
    from huggingface_hub.errors import HfHubHTTPError

    api = HfApi()
    report = []
    if not os.path.isdir(source_root):
        _result(report)
        return 0
    for owner in sorted(os.listdir(source_root)):
        owner_dir = os.path.join(source_root, owner)
        if not os.path.isdir(owner_dir) or owner.startswith("."):
            continue
        for name in sorted(os.listdir(owner_dir)):
            folder = os.path.join(owner_dir, name)
            if not os.path.isdir(folder) or name.startswith("."):
                continue
            repo = f"{owner}/{name}"
            files = []
            for base, _, names in os.walk(folder):
                for file in names:
                    if file != ".DS_Store":
                        files.append(os.path.relpath(os.path.join(base, file), folder))
            entry = {"repo": repo, "files": len(files), "moved": 0, "downloaded": 0, "skipped": 0, "kept_local": False}
            try:
                info = api.model_info(repo, files_metadata=True)
            except HfHubHTTPError as error:
                info = None
                print(f"{repo}: not on Hugging Face ({error.__class__.__name__}); keeping it as a local model", file=sys.stderr)
            if info is None:
                entry["kept_local"] = True
                if not dry_run:
                    target = os.path.join(local_root, name)
                    if os.path.exists(target):
                        target = f"{target}-{owner}"
                    os.makedirs(local_root, exist_ok=True)
                    shutil.move(folder, target)
                report.append(entry)
                continue
            repo_dir = os.path.join(cache, "models--" + repo.replace("/", "--"))
            snapshot = os.path.join(repo_dir, "snapshots", info.sha)
            remote = {sibling.rfilename: sibling for sibling in info.siblings or []}
            for relative in files:
                sibling = remote.get(relative)
                local = os.path.join(folder, relative)
                if sibling is None:
                    # Not part of the repo (LM Studio's own files): dropped.
                    entry["skipped"] += 1
                    continue
                lfs = getattr(sibling, "lfs", None)
                expected = (lfs.sha256 if lfs else None) or getattr(sibling, "blob_id", None)
                if not expected:
                    continue
                actual = _sha256(local) if lfs else _git_blob_sha1(local)
                if actual != expected:
                    continue
                entry["moved"] += 1
                if dry_run:
                    continue
                blob = os.path.join(repo_dir, "blobs", expected)
                if not os.path.exists(blob):
                    _move(local, blob)
                link = os.path.join(snapshot, relative)
                os.makedirs(os.path.dirname(link), exist_ok=True)
                if os.path.lexists(link):
                    os.unlink(link)
                os.symlink(os.path.relpath(blob, os.path.dirname(link)), link)
            # Repo files whose local copy did not match its hash: fetched again.
            entry["downloaded"] = len([name for name in files if name in remote]) - entry["moved"]
            missing = [name for name in remote if name in files and not os.path.lexists(os.path.join(snapshot, name))]
            if not dry_run:
                for relative in missing:
                    hf_hub_download(repo, relative, revision=info.sha)
                os.makedirs(os.path.join(repo_dir, "refs"), exist_ok=True)
                with open(os.path.join(repo_dir, "refs", "main"), "w", encoding="utf-8") as handle:
                    handle.write(info.sha)
                shutil.rmtree(folder, ignore_errors=True)
            report.append(entry)
        if not dry_run:
            try:
                if os.path.exists(os.path.join(owner_dir, ".DS_Store")):
                    os.unlink(os.path.join(owner_dir, ".DS_Store"))
                os.rmdir(owner_dir)
            except OSError:
                pass
    _result(report)
    return 0


def hub_delete(cache: str, repos: list[str]) -> int:
    """Delete whole model repos the way `hf cache rm` does: huggingface_hub
    knows which shared blobs other repos (models or datasets) still use."""
    from huggingface_hub import scan_cache_dir

    info = scan_cache_dir(cache)
    report = []
    for repo_id in repos:
        repo = next((r for r in info.repos if r.repo_id == repo_id and r.repo_type == "model"), None)
        if repo is None:
            report.append({"repo": repo_id, "freed": 0, "found": False})
            continue
        strategy = info.delete_revisions(*[revision.commit_hash for revision in repo.revisions])
        freed = strategy.expected_freed_size
        strategy.execute()
        # A repo with no revisions left (or only refs) is removed entirely.
        if repo.repo_path.exists():
            import shutil

            shutil.rmtree(repo.repo_path, ignore_errors=True)
        report.append({"repo": repo_id, "freed": freed, "found": True})
    _result(report)
    return 0


def hub_prune(cache: str, dry_run: bool) -> int:
    """`hf cache prune`: detached revisions, unfinished downloads and shared
    blobs nothing references any more. Unclear bookkeeping is never deleted."""
    from huggingface_hub import scan_cache_dir
    from huggingface_hub.utils import _shared_blobs

    info = scan_cache_dir(cache)
    revisions = sorted(r.commit_hash for repo in info.repos for r in repo.revisions if len(r.refs) == 0)
    strategy = info.delete_revisions(*revisions)
    incomplete = list(info.incomplete_files)
    unreferenced = _shared_blobs.unreferenced_shared_blobs(info.cache_dir) if info.cache_dir is not None else {}
    summary = {
        "revisions": len(revisions),
        "revision_bytes": strategy.expected_freed_size,
        "incomplete": len(incomplete),
        "incomplete_bytes": info.incomplete_size_on_disk,
        "shared": len(unreferenced),
        "shared_bytes": sum(unreferenced.values()),
    }
    if not dry_run:
        strategy.execute()
        for item in incomplete:
            try:
                item.file_path.unlink()
            except OSError:
                pass
        for store_path in unreferenced:
            _shared_blobs.sweep_shared_blob(store_path, cache_dir=info.cache_dir)
    _result(summary)
    return 0


def hub_convert(source: str, ident: str, output: str, bits: int, kind: str, trust: bool) -> int:
    """Convert a downloaded model to MLX, quantized to `bits` (0 keeps 16-bit)."""
    if os.path.exists(output):
        print(f"{output} already exists", file=sys.stderr)
        return 5
    quantize = {"quantize": bits > 0, "q_bits": bits or None}
    if kind == "image":
        key = mflux_key(ident, source)
        command = [os.path.join(os.path.dirname(sys.executable), "mflux-save"), "--model", str(named_path({"id": ident, "path": source})),
                   "--base-model", key, "--path", output]
        if bits:
            command += ["--quantize", str(bits)]
        return subprocess.call(command, stdout=sys.stderr)
    if kind == "vision":
        from mlx_vlm import convert

        convert(source, mlx_path=output, trust_remote_code=trust, **{**quantize, "q_bits": bits or 4})
    elif kind == "embedding":
        from mlx_embeddings import convert

        convert(source, mlx_path=output, **{**quantize, "q_bits": bits or 4})
    elif kind in {"stt", "tts", "music"}:
        from mlx_audio.convert import convert

        convert(str(named_path({"id": ident, "path": source})), mlx_path=output, **quantize)
    else:
        from mlx_lm import convert

        convert(source, mlx_path=output, trust_remote_code=trust, **quantize)
    _result({"path": output})
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["serve"]:
        return serve()
    if argv[:1] == ["hub"] and len(argv) >= 3:
        args = json.loads(argv[2])
        action = argv[1]
        try:
            if action == "search":
                return hub_search(args["query"], int(args.get("limit", 20)), bool(args.get("mlx")), args.get("task"))
            if action == "pull":
                return hub_pull(args["repo"], list(args.get("include") or []), args.get("revision"), args["cache"])
            if action == "import":
                return hub_import(args["source"], args["cache"], args["local"], bool(args.get("dry_run")))
            if action == "delete":
                return hub_delete(args["cache"], list(args["repos"]))
            if action == "prune":
                return hub_prune(args["cache"], bool(args.get("dry_run")))
            if action == "convert":
                return hub_convert(args["source"], args["id"], args["output"], int(args.get("bits", 4)), args.get("kind", "text"),
                                   bool(args.get("trust_remote_code")))
        except KeyboardInterrupt:
            return 130
        except JobError as error:
            print(str(error), file=sys.stderr)
            return 1
        except Exception as error:  # noqa: BLE001 - shown to the user as one line
            message = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
            print(f"{type(error).__name__}: {message}", file=sys.stderr)
            return 1
    print("usage: worker.py serve | hub <search|pull|import|convert> <json>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
