"""`ul lm` as a black box: a fake MLX worker speaking the real protocol and a
fake Hugging Face cache, so nothing touches the network, MLX or real models."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
import wave
from pathlib import Path

from tests.ulbin import CoreTestCase, binary

HERE = Path(__file__).resolve().parent

FAKE_WORKER = r'''
import json, os, sys, threading
out = os.fdopen(os.dup(1), "w", buffering=1)
os.dup2(2, 1)
def emit(event): out.write(json.dumps(event) + "\n"); out.flush()
if sys.argv[1] == "hub":
    action, args = sys.argv[2], json.loads(sys.argv[3])
    if action == "search":
        emit({"result": [{"id": "mlx-community/Fake-4bit", "downloads": 42, "task": "text-generation", "mlx": True, "gguf": False}]})
    elif action == "pull":
        if args["repo"] == "nobody/missing":
            print("nobody/missing was not found on Hugging Face", file=sys.stderr); sys.exit(4)
        cache = args["cache"]
        root = os.path.join(cache, "models--" + args["repo"].replace("/", "--"))
        snap = os.path.join(root, "snapshots", "rev1")
        os.makedirs(snap, exist_ok=True); os.makedirs(os.path.join(root, "refs"), exist_ok=True)
        open(os.path.join(root, "refs", "main"), "w").write("rev1")
        open(os.path.join(snap, "model-Q4.gguf"), "w").write("g")
        emit({"result": {"path": snap}})
    elif action == "delete":
        import shutil
        report = []
        for repo in args["repos"]:
            root = os.path.join(args["cache"], "models--" + repo.replace("/", "--"))
            report.append({"repo": repo, "freed": 7, "found": os.path.isdir(root)})
            shutil.rmtree(root, ignore_errors=True)
        emit({"result": report})
    elif action == "prune":
        import glob
        unfinished = glob.glob(os.path.join(args["cache"], "models--*", "blobs", "*.incomplete"))
        if not args["dry_run"]:
            for path in unfinished:
                os.unlink(path)
        emit({"result": {"incomplete": len(unfinished), "incomplete_bytes": 5 * len(unfinished), "shared": 0, "shared_bytes": 0, "revisions": 0}})
    sys.exit(0)
cancelled = set(); jobs = []; cv = threading.Condition()
def reader():
    for line in sys.stdin:
        job = json.loads(line)
        with cv:
            if job.get("op") == "cancel": cancelled.add(job["target"])
            else: jobs.append(job)
            cv.notify()
    os._exit(0)
threading.Thread(target=reader, daemon=True).start()
while True:
    with cv:
        while not jobs: cv.wait()
        job = jobs.pop(0)
    ident, op, model = job["id"], job["op"], job.get("model", {})
    emit({"loaded": [model.get("id")]})
    if op in ("chat", "complete"):
        text = job.get("prompt") if op == "complete" else job["messages"][-1]["content"]
        if text == "crash":
            os._exit(9)
        thought = "hmm local" if job.get("local") else "hmm"
        emit({"id": ident, "event": "token", "channel": "reasoning", "text": thought})
        answer = "echo: " + text + (" +img" if job.get("messages", [{}])[-1].get("images") else "")
        for piece in (answer[:5], answer[5:]):
            emit({"id": ident, "event": "token", "channel": "content", "text": piece})
        calls = [{"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{\"x\": 1}"}}] if job.get("tools") else []
        emit({"id": ident, "event": "done", "model": model["id"], "text": answer, "reasoning": thought, "tool_calls": calls,
              "finish_reason": "tool_calls" if calls else "stop", "usage": {"prompt_tokens": 3, "completion_tokens": 2},
              "stats": {"generation_tps": 10.0, "seconds": 0.1}, "echo": job})
    elif op == "embed":
        inputs = job["input"] if isinstance(job["input"], list) else [job["input"]]
        emit({"id": ident, "event": "done", "model": model["id"], "embeddings": [[float(len(t)), 1.0] for t in inputs], "usage": {"prompt_tokens": len(inputs)}})
    elif op == "transcribe":
        emit({"id": ident, "event": "done", "model": model["id"], "text": "heard " + os.path.basename(job["path"]).split(".")[-1], "language": "en",
              "segments": [{"start": 0.0, "end": 1.25, "text": "heard"}]})
    elif op in ("speak", "image", "video", "music"):
        emit({"id": ident, "event": "progress", "step": 1, "total": 2})
        os.makedirs(os.path.dirname(job["output"]), exist_ok=True)
        open(job["output"], "w").write(op + ":" + (job.get("text") or job.get("prompt") or ""))
        emit({"id": ident, "event": "done", "model": model["id"], "path": job["output"], "seed": 5, "width": job.get("width"),
              "height": job.get("height"), "frames": job.get("frames"), "voice": job.get("voice") or "v1", "voices": ["v1", "v2"],
              "audio_seconds": 1.0, "stats": {"seconds": 0.1}, "echo": job})
    else:
        emit({"id": ident, "event": "done", "loaded": [model.get("id")]})
'''


def gguf_header(architecture: str) -> bytes:
    """A GGUF v3 file with only `general.architecture` in its metadata."""
    key = b"general.architecture"
    value = architecture.encode()
    return (b"GGUF" + (3).to_bytes(4, "little") + (0).to_bytes(8, "little") + (1).to_bytes(8, "little")
            + len(key).to_bytes(8, "little") + key + (8).to_bytes(4, "little") + len(value).to_bytes(8, "little") + value)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class LmTestCase(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.cache = self.root / "hf-cache"
        worker = self.root / "fake_worker.py"
        worker.write_text(FAKE_WORKER, encoding="utf-8")
        self.env.update(
            {
                "HF_HUB_CACHE": str(self.cache),
                "UNLAW_LM_PYTHON": sys.executable,
                "UNLAW_LM_WORKER": str(worker),
                "UNLAW_LM_LLAMA_SERVER": "/fake/llama-server",
            }
        )
        # Never talk to a real `ul lm serve` that may be running on the default port.
        self.ok("config", "set", "lm.port", str(free_port()))
        self.text = self.repo("mlx-community/Tiny-4bit", {"config.json": '{"model_type":"qwen3","quantization":{"bits":4}}', "model.safetensors": "1234"})
        self.repo("mlx-community/Eye-4bit", {"config.json": '{"model_type":"smolvlm","vision_config":{}}', "model.safetensors": "12"})
        self.repo("mlx-community/all-MiniLM-L6-v2-4bit", {"config.json": '{"model_type":"bert","architectures":["BertModel"]}', "model.safetensors": "1"})
        self.repo("mlx-community/whisper-tiny", {"config.json": '{"n_audio_ctx":1500}', "weights.safetensors": "1"})
        card = "---\npipeline_tag: {}\n---\n"
        self.repo("mlx-community/Voice-TTS", {"config.json": "{}", "model.safetensors": "1", "README.md": card.format("text-to-speech")})
        self.repo("mlx-community/Song-Music", {"config.json": "{}", "model.safetensors": "1", "README.md": card.format("text-to-audio")})
        self.repo("prism-ml/bonsai-image-ternary", {"model_index.json": "{}", "vae/x.safetensors": "1", "transformer-packed-mflux/t.safetensors": "1"})
        self.repo("someone/Wan-Video", {"config.json": "{}", "model.safetensors": "1", "t5_encoder.safetensors": "1", "vae.safetensors": "1"})
        self.repo("someone/Big-GGUF", {"big-Q4_K_M.gguf": "g"})

    def repo(self, repo_id: str, files: dict[str, str]) -> Path:
        root = self.cache / ("models--" + repo_id.replace("/", "--"))
        snapshot = root / "snapshots" / "abc"
        snapshot.mkdir(parents=True)
        (root / "blobs").mkdir()
        (root / "refs").mkdir()
        (root / "refs" / "main").write_text("abc")
        for index, (name, content) in enumerate(files.items()):
            blob = root / "blobs" / f"b{index}"
            blob.write_text(content)
            target = snapshot / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to("../" * name.count("/") + f"../../blobs/b{index}")
        return snapshot


class LmCliTests(LmTestCase):
    def test_help_has_no_side_effects(self) -> None:
        for flag in ("--help", "-h"):
            result = self.ok("lm", flag)
            self.assertIn("Run local AI models on this Mac with MLX", result.stdout)
            self.assertIn("lm.idle_minutes", result.stdout)
        self.assertIn("Usage:", self.ok("lm", "serve", "--help").stdout)
        self.assertFalse((self.unlaw / "data" / "runtime" / "lm-engine").exists())
        self.assertEqual(self.ok("which", "lm").stdout, "lm: builtin (Rust)\n")
        self.assertIn("lm               Run local AI models", self.ok("commands", "--describe").stdout)

    def test_list_info_use_and_rm(self) -> None:
        listing = self.ok("lm", "list").stdout
        self.assertIn("mlx-community/Tiny-4bit", listing)
        self.assertIn("GGUF no bundled engine runs", listing)
        rows = {row["id"]: row for row in json.loads(self.ok("lm", "list", "--json").stdout)}
        self.assertEqual(rows["mlx-community/Eye-4bit"]["type"], "vision")
        self.assertEqual(rows["mlx-community/whisper-tiny"]["type"], "stt")
        kinds = {row["id"]: row["type"] for row in rows.values()}
        self.assertEqual(
            [kinds[m] for m in ("mlx-community/Voice-TTS", "mlx-community/Song-Music", "prism-ml/bonsai-image-ternary", "someone/Wan-Video")],
            ["tts", "music", "image", "video"],
        )
        self.assertFalse(rows["someone/Big-GGUF"]["runnable"])
        self.assertFalse(rows["mlx-community/Tiny-4bit"]["default"], "two chat models and no default")
        self.assertTrue(rows["mlx-community/Voice-TTS"]["default"], "the only speech model is the default")

        info = self.ok("lm", "info", "tiny").stdout
        self.assertIn("Quantized:    4-bit", info)
        self.assertIn(str(self.text), info)
        self.assertEqual(self.ok("lm", "use", "tiny-4bit").stdout, "Default chat model: mlx-community/Tiny-4bit (lm.model)\n")
        self.assertIn("(lm.stt_model)", self.ok("lm", "use", "whisper").stdout)
        self.assertEqual(self.ok("config", "get", "lm.stt_model").stdout, "mlx-community/whisper-tiny\n")
        self.assertEqual(self.ok("config", "get", "lm.model").stdout, "mlx-community/Tiny-4bit\n")
        rows = {row["id"]: row for row in json.loads(self.ok("lm", "list", "--json").stdout)}
        self.assertTrue(rows["mlx-community/Tiny-4bit"]["default"])
        bad = self.ul("lm", "use", "big-gguf")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("cannot be a default", bad.stderr)
        wrong = self.ul("lm", "-m", "minilm", "hi")
        self.assertIn("is an embedding model (embeddings); this request needs a chat model", wrong.stderr)

        refused = self.ul("lm", "rm", "big-gguf")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("--yes", refused.stderr)
        self.assertIn("freed", self.ok("lm", "rm", "big-gguf", "--yes").stdout)
        self.assertFalse((self.cache / "models--someone--Big-GGUF").exists())
        self.assertIn("did you mean", self.ul("lm", "info", "tiny-8bit").stderr)

    def test_prompts_stream_through_the_worker(self) -> None:
        result = self.ok("lm", "-m", "tiny", "hello", "there")
        # Reasoning is hidden when stdout is not a terminal.
        self.assertEqual(result.stdout, "echo: hello there\n")
        piped = self.ok("lm", "-m", "tiny", "fix:", input="code here\n")
        self.assertEqual(piped.stdout, "echo: fix:\n\ncode here\n")
        image = self.root / "pic.png"
        image.write_bytes(b"\x89PNG")
        self.assertEqual(self.ok("lm", "-m", "eye", "-i", str(image), "what?").stdout, "echo: what? +img\n")
        no_vision = self.ul("lm", "-m", "tiny", "-i", str(image), "what?")
        self.assertIn("cannot see images", no_vision.stderr)
        self.assertIn("Image not found", self.ul("lm", "-m", "eye", "-i", "nope.png", "x").stderr)

        ambiguous = self.ul("lm", "hi")
        self.assertEqual(ambiguous.returncode, 1)
        self.assertIn("2 chat models are downloaded (mlx-community/Eye-4bit, mlx-community/Tiny-4bit)", ambiguous.stderr)
        self.ok("config", "set", "lm.model", "eye")
        self.assertEqual(self.ok("lm", "hi").stdout, "echo: hi\n")
        missing = self.ul("lm", "-m", "nothing-like-it", "hi")
        self.assertIn("is not downloaded", missing.stderr)
        self.assertIn("download it with `ul lm pull nothing-like-it`", missing.stderr)
        gguf = self.ul("lm", "-m", "big-gguf", "hi")
        self.assertIn("is a GGUF no bundled engine runs", gguf.stderr)
        self.assertIn("ul lm search Big --mlx", gguf.stderr)

    def test_a_crashing_worker_is_reported(self) -> None:
        crashed = self.ul("lm", "-m", "tiny", "crash")
        self.assertEqual(crashed.returncode, 1)
        self.assertIn("MLX worker was killed", crashed.stderr)

    def test_chat_commands(self) -> None:
        image = self.root / "pic.png"
        image.write_bytes(b"\x89PNG")
        script = f"first\n/model eye\n/image {image}\nsecond\n/models\n/think off\n/clear\n/bogus\n/save {self.root / 'c.md'}\n/exit\n"
        result = self.ok("lm", "chat", "tiny", input=script)
        self.assertIn("ul lm · mlx-community/Tiny-4bit", result.stdout)
        self.assertIn("echo: first", result.stdout)
        self.assertIn("echo: second +img", result.stdout)
        self.assertIn("* mlx-community/Eye-4bit (vision)", result.stdout)
        self.assertIn("Reasoning: off", result.stdout)
        self.assertIn("Context cleared.", result.stdout)
        self.assertIn("Unknown command /bogus", result.stderr)
        saved = (self.root / "c.md").read_text()
        self.assertIn("# Chat with mlx-community/Eye-4bit", saved)

    def test_embed_transcribe_search_and_pull(self) -> None:
        self.assertEqual(self.ok("lm", "embed", "ab", "abc").stdout, "[2.0,1.0]\n[3.0,1.0]\n")
        audio = self.root / "note.m4a"
        audio.write_bytes(b"x")
        # Formats the recognisers cannot read are converted to WAV first.
        if shutil.which("afconvert"):
            wav = self.root / "note.wav"
            with wave.open(str(wav), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(16000)
                handle.writeframes(b"\0\0" * 1600)
            subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", str(wav), str(audio)], check=True)
            self.assertEqual(self.ok("lm", "transcribe", str(audio)).stdout, "heard wav\n")
        self.assertEqual(self.ok("lm", "transcribe", str(self.root / "note.wav") if shutil.which("afconvert") else str(audio)).stdout.split()[0], "heard")
        self.assertEqual(self.ok("lm", "transcribe", "--srt", str(self.root / "note.wav")).stdout, "1\n00:00:00,000 --> 00:00:01,250\nheard\n\n")
        self.assertIn("Audio file not found", self.ul("lm", "transcribe", "missing.wav").stderr)
        search = self.ok("lm", "search", "fake", "--mlx").stdout
        self.assertIn("mlx-community/Fake-4bit", search)
        self.assertIn("MLX", search)
        pulled = self.ok("lm", "pull", "https://huggingface.co/new/Thing-GGUF/tree/main")
        self.assertIn("Downloaded new/Thing-GGUF (gguf", pulled.stdout)
        self.assertIn("ul lm search Thing --mlx", pulled.stdout)
        failed = self.ul("lm", "pull", "nobody/missing")
        self.assertEqual(failed.returncode, 4)
        self.assertIn("was not found", failed.stderr)
        self.assertEqual(self.ul("lm", "pull", "just-a-name").returncode, 2)

    def test_rm_clean_open_and_where(self) -> None:
        self.ok("lm", "use", "eye")
        removed = self.ok("lm", "rm", "eye", "big-gguf", "--yes").stdout
        self.assertIn("Deleted mlx-community/Eye-4bit", removed)
        self.assertIn("lm.model was this model; now auto", removed)
        self.assertIn("freed in total", removed)
        self.assertEqual(self.ok("config", "get", "lm.model").stdout, "auto\n")
        self.assertFalse((self.cache / "models--someone--Big-GGUF").exists())
        self.assertIn("without names: choose from a list", self.ul("lm", "rm").stderr)
        self.assertIn("No downloaded model matches", self.ul("lm", "rm", "nothing-at-all", "--yes").stderr)

        # Leftovers go through huggingface_hub's prune; the chunk cache is ours.
        (self.cache / "models--mlx-community--Tiny-4bit" / "blobs" / "y.incomplete").write_text("12345")
        xet = self.root / "xet"
        (xet / "chunks").mkdir(parents=True)
        (xet / "chunks" / "c").write_text("x" * 10)
        env = {"HF_XET_CACHE": str(xet)}
        self.assertEqual(self.ul("lm", "clean", env=env).returncode, 1, "asks first, so stdin-less runs keep everything")
        self.assertTrue(xet.exists())
        cleaned = self.ok("lm", "clean", "--yes", env=env).stdout
        self.assertIn("unfinished downloads (1)", cleaned)
        self.assertIn("download chunk cache", cleaned)
        self.assertFalse(xet.exists() or (self.cache / "models--mlx-community--Tiny-4bit" / "blobs" / "y.incomplete").exists())
        self.assertTrue((self.cache / "models--mlx-community--Tiny-4bit").exists(), "working models stay")
        self.assertEqual(self.ok("lm", "clean", "--yes", env=env).stdout, "Nothing to clean.\n")

        self.assertEqual(self.ok("lm", "where").stdout.strip(), str(self.cache))
        self.assertEqual(self.ok("lm", "where", "tiny").stdout.strip(), str(self.text))
        generated = self.ok("lm", "open", "generated", "--print").stdout.strip()
        self.assertEqual(generated, str(self.unlaw / "data" / "generated"))
        self.assertTrue(Path(generated).is_dir())
        self.assertIn("No downloaded model matches", self.ul("lm", "where", "nope-nope").stderr)

    def test_gguf_models_run_on_llama_cpp_and_transcribe_cpp(self) -> None:
        chat = self.cache / "models--someone--Chat-GGUF" / "snapshots" / "r1"
        chat.mkdir(parents=True)
        (chat / "model-Q8_0.gguf").write_bytes(gguf_header("qwen35"))
        (chat / "model-Q4_K_M.gguf").write_bytes(gguf_header("qwen35"))
        asr = self.cache / "models--someone--Asr-GGUF" / "snapshots" / "r1"
        asr.mkdir(parents=True)
        (asr / "parakeet-Q8_0.gguf").write_bytes(gguf_header("parakeet"))
        rows = {row["id"]: row for row in json.loads(self.ok("lm", "list", "--json").stdout)}
        self.assertEqual((rows["someone/Chat-GGUF"]["type"], rows["someone/Chat-GGUF"]["format"]), ("text", "gguf"))
        self.assertEqual(rows["someone/Asr-GGUF"]["type"], "stt")
        self.assertEqual(rows["someone/Big-GGUF"]["type"], "gguf", "an unreadable GGUF is listed but not runnable")
        listing = self.ok("lm", "list").stdout
        self.assertIn("chat · GGUF (llama.cpp)", listing)
        self.assertIn("speech to text · GGUF (transcribe.cpp)", listing)
        info = self.ok("lm", "info", "chat-gguf").stdout
        self.assertIn("model-Q4_K_M.gguf (qwen35, runs on llama.cpp)", info)
        self.assertEqual(self.ok("lm", "-m", "chat-gguf", "hi").stdout, "echo: hi\n")
        audio = self.root / "a.wav"
        audio.write_bytes(b"RIFF")
        self.assertEqual(self.ok("lm", "transcribe", "-m", "asr-gguf", str(audio)).stdout, "heard wav\n")

    def test_media_commands_write_files_and_never_overwrite(self) -> None:
        generated = self.unlaw / "data" / "generated"
        speak = self.ok("lm", "speak", "Hello", "there", "--voice", "v2")
        path = Path(speak.stdout.strip())
        self.assertEqual(path.parent, generated / "speech")
        self.assertTrue(path.name.endswith("-hello-there.wav"), path.name)
        self.assertEqual(path.read_text(), "speak:Hello there")
        image = Path(self.ok("lm", "image", "a red fox", "--size", "512x384", "--seed", "9").stdout.strip())
        self.assertEqual((image.parent.name, image.suffix), ("images", ".png"))
        target = self.root / "out.png"
        target.write_text("keep me")
        again = Path(self.ok("lm", "image", "fox", "-o", str(target)).stdout.strip())
        self.assertEqual(again, self.root / "out 2.png")
        self.assertEqual(target.read_text(), "keep me")
        video = Path(self.ok("lm", "video", "waves", "--seconds", "2", "--size", "832x480").stdout.strip())
        self.assertEqual(video.suffix, ".mp4")
        song = Path(self.ok("lm", "music", "lo-fi piano", "--lyrics", "la la").stdout.strip())
        self.assertEqual(song.read_text(), "music:lo-fi piano")
        self.assertIn("Usage: ul lm image", self.ul("lm", "image").stderr)
        self.assertIn("Image not found", self.ul("lm", "image", "x", "-i", "missing.png").stderr)
        self.assertIn("needs an image model", self.ul("lm", "image", "-m", "tiny", "x").stderr)

    def test_old_lm_studio_seed_and_settings_are_retired(self) -> None:
        legacy = self.unlaw / "commands" / "lm" / "main.py"
        legacy.parent.mkdir(parents=True)
        legacy.write_text((HERE / "fixtures" / "lm-3.0.0-seed.py").read_text())
        (legacy.parent / "__pycache__").mkdir()
        (legacy.parent / "__pycache__" / "main.cpython-312.pyc").write_bytes(b"x")
        self.ok("init")
        self.assertFalse(legacy.parent.exists(), "the untouched LM Studio seed is removed")
        config = self.unlaw / "config.toml"
        config.write_text(config.read_text().replace("[lm]\n", '[lm]\nbase_url = "http://127.0.0.1:1234/v1"\ntimeout = 120\n'))
        self.ok("doctor", "--fix", env={"PATH": str(self.bin)})
        text = config.read_text()
        self.assertNotIn("base_url", text)
        self.assertNotIn("timeout = 120", text)
        self.assertIn("idle_minutes = 10", text)
        edited = self.command("lm", "print('my own lm')\n")
        self.assertEqual(self.ok("lm").stdout, "my own lm\n")
        self.assertTrue(edited.exists())


class LmServerTests(LmTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.port = free_port()
        self.ok("config", "set", "lm.model", "tiny")
        self.server = subprocess.Popen(
            [str(binary()), "lm", "serve", "--port", str(self.port)],
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(self.stop)
        banner = self.server.stdout.readline()
        self.assertIn(f"http://127.0.0.1:{self.port}", banner)

    def stop(self) -> None:
        self.server.kill()
        self.server.wait()
        self.server.stdout.close()
        self.server.stderr.close()

    def call(self, path: str, body: object | None = None, raw: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[int, bytes]:
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    def test_openai_endpoints(self) -> None:
        status, body = self.call("/v1/models")
        ids = [model["id"] for model in json.loads(body)["data"]]
        self.assertEqual(status, 200)
        self.assertIn("mlx-community/Tiny-4bit", ids)
        self.assertNotIn("someone/Big-GGUF", ids)

        status, body = self.call("/v1/chat/completions", {"messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}], "max_tokens": 7, "temperature": 0.1, "stop": "x"})
        answer = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(answer["model"], "mlx-community/Tiny-4bit")
        self.assertEqual(answer["choices"][0]["message"], {"role": "assistant", "content": "echo: hi", "reasoning_content": "hmm"})
        self.assertEqual(answer["usage"], {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5})

        status, body = self.call("/v1/chat/completions", {"model": "tiny", "stream": True, "stream_options": {"include_usage": True}, "messages": [{"role": "user", "content": "yo"}], "tools": [{"type": "function", "function": {"name": "f"}}]})
        events = [line[6:] for line in body.decode().splitlines() if line.startswith("data: ")]
        self.assertEqual(events[-1], "[DONE]")
        chunks = [json.loads(event) for event in events[:-1]]
        content = "".join(c["choices"][0]["delta"].get("content", "") for c in chunks if c["choices"])
        self.assertEqual(content, "echo: yo")
        self.assertEqual(chunks[1]["choices"][0]["delta"], {"reasoning_content": "hmm"})
        final = [c for c in chunks if c["choices"] and c["choices"][0]["finish_reason"]][0]
        self.assertEqual(final["choices"][0]["finish_reason"], "tool_calls")
        self.assertEqual(final["choices"][0]["delta"]["tool_calls"][0]["index"], 0)
        self.assertEqual(chunks[-1]["usage"]["total_tokens"], 5)

        status, body = self.call("/v1/completions", {"prompt": "abc"})
        self.assertEqual(json.loads(body)["choices"][0]["text"], "echo: abc")
        status, body = self.call("/v1/embeddings", {"input": ["ab"], "model": "minilm"})
        self.assertEqual(json.loads(body)["data"][0]["embedding"], [2.0, 1.0])
        status, body = self.call("/v1/embeddings", {"input": "ab", "model": "minilm", "encoding_format": "base64"})
        self.assertEqual(json.loads(body)["data"][0]["embedding"], "AAAAQAAAgD8=")

        boundary = "BOUNDARY"
        form = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\nwhisper\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.mp3\"\r\n\r\nAUDIO\r\n--{boundary}--\r\n"
        ).encode()
        status, body = self.call("/v1/audio/transcriptions", raw=form, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        self.assertEqual(json.loads(body), {"text": "heard mp3", "language": "en"})

    def test_errors_are_json_and_the_server_survives(self) -> None:
        status, body = self.call("/v1/chat/completions", {"model": "nope-model", "messages": [{"role": "user", "content": "x"}]})
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body)["error"]["code"], "model_not_found")
        status, body = self.call("/v1/chat/completions", raw=b"{not json")
        self.assertEqual((status, json.loads(body)["error"]["code"]), (400, "invalid_request"))
        status, body = self.call("/v1/embeddings", {"input": "x", "model": "tiny"})
        self.assertEqual(status, 400)
        self.assertIn("needs an embedding model", json.loads(body)["error"]["message"])
        self.assertEqual(self.call("/nowhere")[0], 404)
        status, body = self.call("/v1/chat/completions", {"messages": [{"role": "user", "content": "crash"}]})
        self.assertEqual((status, json.loads(body)["error"]["code"]), (503, "worker_crashed"))
        status, body = self.call("/v1/chat/completions", {"messages": [{"role": "user", "content": "again"}]})
        self.assertEqual((status, json.loads(body)["choices"][0]["message"]["content"]), (200, "echo: again"))
        with socket.create_connection(("127.0.0.1", self.port)) as raw:
            raw.sendall(b"POST /v1/chat/completions HTTP/1.1\r\nContent-Length: 999999999999\r\n\r\n")
            reply = b""
            while b"\r\n" not in reply:
                chunk = raw.recv(100)
                if not chunk:
                    break
                reply += chunk
            self.assertIn(b"413", reply)
        self.assertIsNone(self.server.poll())

    def test_media_endpoints(self) -> None:
        status, body = self.call("/v1/images/generations", {"prompt": "fox", "size": "512x512"})
        image = json.loads(body)
        self.assertEqual(status, 200)
        import base64

        self.assertEqual(base64.b64decode(image["data"][0]["b64_json"]), b"image:fox")
        self.assertEqual(self.call("/v1/images/generations", {"prompt": "fox", "n": 2})[0], 400)
        status, body = self.call("/v1/audio/speech", {"input": "hi", "voice": "v1"})
        self.assertEqual((status, body), (200, b"speak:hi"))
        self.assertEqual(self.call("/v1/audio/speech", {"input": "hi", "response_format": "aiff"})[0], 400)
        status, body = self.call("/v1/videos", {"prompt": "waves", "seconds": "2"})
        job = json.loads(body)
        self.assertEqual((status, job["object"]), (200, "video"))
        for _ in range(50):
            job = json.loads(self.call(f"/v1/videos/{job['id']}")[1])
            if job["status"] == "completed":
                break
            time.sleep(0.1)
        self.assertEqual(job["status"], "completed")
        self.assertEqual(self.call(f"/v1/videos/{job['id']}/content"), (200, b"video:waves"))
        self.assertEqual(self.call("/v1/videos/video-nope")[0], 404)

    def test_only_local_pages_and_names_get_in(self) -> None:
        status, body = self.call("/v1/models", headers={"Host": "evil.example:1234"})
        self.assertEqual((status, json.loads(body)["error"]["type"]), (403, "forbidden"))
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/v1/models")
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))
        # Jobs from the API may not name local files; the terminal's may.
        status, body = self.call("/v1/chat/completions", {"model": "eye", "messages": [{"role": "user", "content": "x"}]})
        self.assertEqual(json.loads(body)["choices"][0]["message"]["reasoning_content"], "hmm")
        status, body = self.call("/ul/job", {"model": "mlx-community/Eye-4bit", "job": {"op": "chat", "messages": [{"role": "user", "content": "x"}]}})
        self.assertIn('"text": "hmm local"'.replace(" ", ""), body.decode().replace(" ", ""))

    def test_gguf_jobs_carry_the_engine(self) -> None:
        chat = self.cache / "models--someone--Chat-GGUF" / "snapshots" / "r1"
        chat.mkdir(parents=True)
        (chat / "model-Q4_K_M.gguf").write_bytes(gguf_header("llama"))
        time.sleep(2.1)  # the server rescans its model list every 2 s
        status, body = self.call("/ul/job", {"model": "someone/Chat-GGUF", "job": {"op": "chat", "messages": [{"role": "user", "content": "x"}]}})
        done = json.loads(body.decode().strip().splitlines()[-1])
        spec = done["echo"]["model"]["gguf"]
        self.assertEqual((spec["runtime"], spec["server"], spec["architecture"]), ("llama", "/fake/llama-server", "llama"))
        self.assertTrue(spec["file"].endswith("model-Q4_K_M.gguf"))

    def test_ollama_endpoints(self) -> None:
        status, body = self.call("/api/tags")
        self.assertIn("mlx-community/Tiny-4bit", [m["name"] for m in json.loads(body)["models"]])
        status, body = self.call("/api/chat", {"model": "tiny", "messages": [{"role": "user", "content": "hey", "images": ["AAAA"]}], "stream": False})
        answer = json.loads(body)
        self.assertEqual((answer["message"]["content"], answer["done"]), ("echo: hey +img", True))
        status, body = self.call("/api/generate", {"model": "tiny", "prompt": "p", "system": "s"})
        lines = [json.loads(line) for line in body.decode().splitlines()]
        self.assertEqual("".join(line.get("response", "") for line in lines), "echo: p")
        self.assertEqual(lines[0]["thinking"], "hmm")
        self.assertTrue(lines[-1]["done"])
        status, body = self.call("/api/generate", {"model": "tiny"})
        self.assertEqual(json.loads(body)["done_reason"], "load")
        status, body = self.call("/api/embed", {"model": "minilm", "input": ["abc"]})
        self.assertEqual(json.loads(body)["embeddings"], [[3.0, 1.0]])
        status, body = self.call("/api/embeddings", {"model": "minilm", "prompt": "a"})
        self.assertEqual(json.loads(body)["embedding"], [1.0, 1.0])
        self.assertEqual(json.loads(self.call("/api/ps")[1])["models"][0]["name"], "mlx-community/all-MiniLM-L6-v2-4bit")
        self.assertEqual(self.call("/api/version")[0], 200)

    def test_cli_uses_the_running_server(self) -> None:
        self.ok("config", "set", "lm.port", str(self.port))
        ps = self.ok("lm", "ps").stdout
        self.assertIn(f"Server: http://127.0.0.1:{self.port}", ps)
        self.assertEqual(self.ok("lm", "via", "server").stdout, "echo: via server\n")
        self.assertIn("mlx-community/Tiny-4bit", self.ok("lm", "ps").stdout)
        busy = self.ul("lm", "serve")
        self.assertEqual(busy.returncode, 1)
        self.assertIn(f"Port {self.port} is already in use", busy.stderr)
        time.sleep(0.1)
        self.assertIn("POST /ul/job", "".join(self.read_log()))

    def read_log(self) -> list[str]:
        self.server.kill()
        self.server.wait()
        return self.server.stderr.readlines()


if __name__ == "__main__":
    unittest.main()
