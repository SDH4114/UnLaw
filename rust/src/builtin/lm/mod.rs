//! `ul lm`: local models on Apple Silicon through MLX. Downloads from Hugging
//! Face into its standard cache, chats in the terminal, transcribes, speaks,
//! draws and films, and serves OpenAI- and Ollama-compatible APIs on
//! 127.0.0.1. Rust does the CLI, HTTP, supervision and model store; private
//! Python workers do the MLX math.

mod chat;
mod engine;
mod http;
mod media;
mod ollama;
mod openai;
mod server;
mod service;
mod store;
mod worker;

use std::io::{self, IsTerminal, Read, Write};
use std::path::{Path, PathBuf};
use std::time::Duration;

use serde_json::{json, Value};

use crate::config::Config;
use chat::Options;
use engine::Engine;
use service::{Purpose, Service, Settings};
use store::{human_size, Kind, Lookup};

pub const HELP: &str = r#"Run local AI models on this Mac with MLX: chat, vision, speech, images, video.
Usage:
  ul lm                           Chat with the default model (lm.model)
  ul lm "<prompt>" [options]      Answer once, streamed; piped stdin is appended
  ul lm chat [model] [options]    Interactive chat (/help inside for commands)
  ul lm image "<prompt>" [--size 1024x1024] [--steps N] [--seed N] [-i init.png]
  ul lm video "<prompt>" [--size 832x480] [--seconds 2 | --frames 49] [-i start.png]
  ul lm speak "<text>" [--voice NAME] [--speed 1.0] [-l ru] [--play]
  ul lm music "<style>" [--lyrics TEXT|FILE] [--seconds 30]   (no lyrics: instrumental)
  ul lm transcribe <audio|video> [-l ru] [--srt | --json]
  ul lm embed "<text>"...         Embedding vectors as JSON lines
  ul lm pull <repo|url> [--include <glob>]... [--revision <rev>] [--convert [--bits 4]]
  ul lm convert <model> [--bits 2|3|4|5|6|8|0]   Make an MLX (quantized) copy
  ul lm search <query> [--mlx] [--task <tag>] [--limit N]
  ul lm list [--json] | info <model> | use <model> | rm <model> [--yes]
  ul lm serve [--port N] [--ollama] [--cors] [--trust-remote-code]
  ul lm ps                        Models loaded by the running server
  ul lm import-lmstudio [--dry-run] [--from <dir>]
  ul lm doctor [--repair]         Check (or rebuild) the engines
Options:
  -m, --model <name>    owner/repo, repo name or a unique part of it
  -i, --image <file>    Image to look at (vision chat) or start from (image, video)
  -s, --system <text>   System prompt; for speak: voice instructions
  -t, --temperature <n> 0-2 (default: the model's own recommendation, then lm.temperature)
  -n, --max-tokens <n>  Answer length limit (default: lm.max_tokens)
  --think / --no-think  Reasoning on or off for models that support it
  -o, --output <path>   File or folder for results (never overwritten; default
                        storage.root/generated/<images|videos|speech|music>)
  --open, --play        Open the image/video or play the audio when done
  -q, --quantize 4|8    Quantize an image model while loading (saves memory)
Model types (ul lm list): text, vision (chat), embedding, stt (speech to text),
tts (text to speech), music, image, video; gguf and other files are kept but MLX
cannot run them. Any repo can be downloaded. Images run on mflux (FLUX.1/2/3,
Qwen-Image, Z-Image, FIBO...; Bonsai Image through PrismML's mflux), video on
mlx-video (Wan 2.x, LTX-2), speech on mlx-audio and mlx-whisper. Recordings in
any format (m4a, mov, mp4...) are converted with afconvert.
API (ul lm serve, 127.0.0.1 only):
  OpenAI:  /v1/models /v1/chat/completions /v1/completions /v1/embeddings
           /v1/audio/transcriptions /v1/audio/speech /v1/images/generations
           /v1/videos (job; GET /v1/videos/{id}[/content])
  Ollama:  /api/tags chat generate embed show ps version (--ollama adds :11434)
  Browser pages are refused unless --cors; other hostnames are always refused.
  With a server running, `ul lm` in the terminal shares its loaded models.
Models live in the Hugging Face cache (HF_HUB_CACHE, HF_HOME/hub or
~/.cache/huggingface/hub); converted ones in storage.root/models. A model larger
than 75% of RAM is refused before loading; chat, helper models, images and
video run in separate processes, are freed after lm.idle_minutes idle, and a
crash in one never stops the others. There is no cloud fallback.
Engines are created on first use in storage.root/runtime/lm-engine with uv
(Python 3.13, about 1.2 GB; images and Bonsai Image add 1.5 GB each), else
Python 3.11+. Apple Silicon only. Downloads need network; gated repos need
`hf auth login`.
Settings: lm.model (auto), lm.embedding_model, lm.stt_model, lm.tts_model,
lm.image_model, lm.video_model, lm.music_model (auto), lm.port (1234),
lm.idle_minutes (10), lm.system_prompt, lm.temperature (0.7), lm.max_tokens (4096).
Examples:
  ul lm search qwen3 --mlx
  ul lm pull prism-ml/Ternary-Bonsai-2-9B-mlx-2bit && ul lm use Bonsai-2-9B
  ul lm "explain this error" < build.log
  ul lm -i photo.jpg "what is in the picture?"
  ul lm image "a bonsai tree in morning light" --open
  ul lm speak "Привет!" -m Qwen3-TTS --play
  ul lm transcribe voice.m4a --srt > voice.srt
  ul lm convert Qwen/Qwen3-4B --bits 4
  ul lm serve --ollama
"#;

const SUBCOMMANDS: [&str; 20] = [
    "chat", "pull", "search", "list", "ls", "info", "use", "rm", "serve", "ps", "embed", "transcribe", "import-lmstudio", "doctor", "image",
    "video", "speak", "music", "convert", "say",
];

fn fail(message: impl std::fmt::Display) -> i32 {
    eprintln!("unlaw lm: {message}");
    1
}

fn usage(text: &str) -> i32 {
    eprintln!("Usage: {text}");
    2
}

/// Parse options; everything else is the words of the prompt or the inputs.
fn parse_options(args: &[String]) -> Result<(Options, Vec<String>), String> {
    let mut options = Options::default();
    let mut words = Vec::new();
    let mut iter = args.iter();
    let mut literal = false;
    while let Some(arg) = iter.next() {
        if literal {
            words.push(arg.clone());
            continue;
        }
        let mut value = |name: &str| iter.next().cloned().ok_or_else(|| format!("{name} needs a value"));
        let number = |name: &str, raw: String| raw.trim().parse::<f64>().map_err(|_| format!("Invalid {name}: {raw}"));
        match arg.as_str() {
            "--" => literal = true,
            "-m" | "--model" => options.model = Some(value(arg)?),
            "-i" | "--image" => options.images.push(value(arg)?),
            "-s" | "--system" | "--instructions" => options.system = Some(value(arg)?),
            "-t" | "--temperature" => {
                let temperature = number("temperature", value(arg)?)?;
                if !(0.0..=2.0).contains(&temperature) {
                    return Err("Temperature must be between 0 and 2".into());
                }
                options.temperature = Some(temperature);
            }
            "-n" | "--max-tokens" => {
                let raw = value(arg)?;
                options.max_tokens = Some(raw.parse().ok().filter(|n: &i64| *n > 0).ok_or(format!("Invalid max tokens: {raw}"))?);
            }
            "-l" | "--language" => options.language = Some(value(arg)?),
            "-o" | "--output" => options.output = Some(value(arg)?),
            "--size" => {
                let raw = value(arg)?;
                options.size = Some(media::parse_size(&raw).ok_or(format!("Invalid size {raw}; use WIDTHxHEIGHT, e.g. 1024x768"))?);
            }
            "--steps" => options.steps = Some(number("steps", value(arg)?)? as u64).filter(|n| *n > 0),
            "--seed" => options.seed = Some(number("seed", value(arg)?)? as u64),
            "--frames" => options.frames = Some(number("frames", value(arg)?)? as u64).filter(|n| *n > 0),
            "--seconds" | "--duration" => options.seconds = Some(number("seconds", value(arg)?)?).filter(|n| *n > 0.0),
            "--voice" => options.voice = Some(value(arg)?),
            "--speed" => options.speed = Some(number("speed", value(arg)?)?).filter(|n| *n > 0.0),
            "--lyrics" => options.lyrics = Some(value(arg)?),
            "--strength" => options.strength = Some(number("strength", value(arg)?)?),
            "-q" | "--quantize" => {
                let raw = value(arg)?;
                options.quantize = Some(raw.parse().ok().filter(|b| [3, 4, 5, 6, 8].contains(b)).ok_or(format!("Invalid quantize {raw}; use 4 or 8"))?);
            }
            "--open" | "--play" => options.open = true,
            "--srt" => options.srt = true,
            "--json" => options.json = true,
            "--think" => options.think = Some(true),
            "--no-think" => options.think = Some(false),
            flag if flag.starts_with('-') && flag.len() > 1 && words.is_empty() => return Err(format!("Unknown option {flag}")),
            _ => words.push(arg.clone()),
        }
    }
    Ok((options, words))
}

fn list(config: &Config, args: &[String]) -> i32 {
    let as_json = match args {
        [] => false,
        [flag] if flag == "--json" => true,
        _ => return usage("ul lm list [--json]"),
    };
    let service = Service::new(config, false);
    let models = service.models();
    let defaults: Vec<String> = Purpose::ALL.iter().filter_map(|purpose| service.resolve(None, *purpose).ok()).map(|m| m.id).collect();
    if as_json {
        let rows: Vec<Value> = models
            .iter()
            .map(|m| {
                json!({"id": m.id, "type": m.kind.name(), "runnable": m.kind.runnable() && !m.partial,
                       "bytes": m.bytes, "path": m.path, "partial": m.partial, "default": defaults.contains(&m.id)})
            })
            .collect();
        println!("{}", Value::Array(rows));
        return 0;
    }
    if models.is_empty() {
        println!("No models yet. Find one with `ul lm search <name> --mlx`, then `ul lm pull <repo>`.");
        return 0;
    }
    let width = models.iter().map(|m| m.id.len()).max().unwrap_or(5).max(5);
    println!("  {:width$}  {:9}  {:>9}  STATUS", "MODEL", "TYPE", "SIZE");
    for model in &models {
        let mark = if defaults.contains(&model.id) { "*" } else { " " };
        let status = if model.partial {
            "incomplete: run `ul lm pull` again"
        } else if model.kind == Kind::Gguf {
            "GGUF: MLX cannot run it"
        } else if !model.kind.runnable() {
            "not loadable by MLX"
        } else {
            model.kind.describe()
        };
        println!("{mark} {:width$}  {:9}  {:>9}  {status}", model.id, model.kind.name(), human_size(model.bytes));
    }
    println!("* = default for its type. Cache: {}", store::hub_cache().display());
    0
}

fn find_model(service: &Service, name: &str) -> Result<store::Model, String> {
    match store::find(&service.models(), name, |m| m.kind.runnable()) {
        Lookup::Found(model) => Ok(model),
        Lookup::Ambiguous(ids) => Err(format!("'{name}' matches several models: {}", ids.join(", "))),
        Lookup::Missing(close) if close.is_empty() => Err(format!("No downloaded model matches '{name}'")),
        Lookup::Missing(close) => Err(format!("No downloaded model matches '{name}'; did you mean {}?", close.join(", "))),
    }
}

fn info(config: &Config, args: &[String]) -> i32 {
    let [name] = args else { return usage("ul lm info <model>") };
    let service = Service::new(config, false);
    let model = match find_model(&service, name) {
        Ok(model) => model,
        Err(message) => return fail(message),
    };
    let config_json: Value = std::fs::read_to_string(model.path.join("config.json"))
        .ok()
        .and_then(|text| serde_json::from_str(&text).ok())
        .unwrap_or(Value::Null);
    let text_config = if config_json["text_config"].is_object() { &config_json["text_config"] } else { &config_json };
    println!("Model:        {}", model.id);
    println!("Type:         {} ({}){}", model.kind.name(), model.kind.describe(), if model.kind.runnable() { "" } else { ", not runnable with MLX" });
    println!("Size:         {}{}", human_size(model.bytes), if model.partial { " (incomplete download)" } else { "" });
    println!("Path:         {}", model.path.display());
    if model.kind.runnable() {
        println!("Engine:       {}", model.engine().name());
    }
    if let Some(architecture) = config_json["architectures"][0].as_str().or(config_json["model_type"].as_str()) {
        println!("Architecture: {architecture}");
    }
    if let Some(bits) = config_json["quantization"]["bits"].as_u64() {
        println!("Quantized:    {bits}-bit");
    }
    if let Some(context) = text_config["max_position_embeddings"].as_u64() {
        println!("Context:      {context} tokens");
    }
    let generation: Value = std::fs::read_to_string(model.path.join("generation_config.json"))
        .ok()
        .and_then(|text| serde_json::from_str(&text).ok())
        .unwrap_or(Value::Null);
    let sampling: Vec<String> = ["temperature", "top_p", "top_k", "min_p", "presence_penalty"]
        .iter()
        .filter_map(|key| generation.get(*key).filter(|v| v.is_number()).map(|v| format!("{key}={v}")))
        .collect();
    if !sampling.is_empty() {
        println!("Sampling:     {} (the model's recommendation, used by default)", sampling.join(" "));
    }
    if model.id.contains('/') && !model.id.starts_with("local/") {
        println!("Hub:          https://huggingface.co/{}", model.id);
    }
    0
}

fn use_model(config: &Config, args: &[String]) -> i32 {
    let [name] = args else { return usage("ul lm use <model>") };
    let service = Service::new(config, false);
    let model = match find_model(&service, name) {
        Ok(model) => model,
        Err(message) => return fail(message),
    };
    let Some(purpose) = Purpose::for_kind(model.kind) else {
        return fail(format!("{} is {} and cannot be a default", model.id, model.kind.describe()));
    };
    let key = purpose.setting().unwrap_or("lm.model");
    match crate::config::set(key, toml_edit::Item::Value(model.id.as_str().into())) {
        Ok(()) => {
            println!("Default {} model: {} ({key})", purpose.noun(), model.id);
            0
        }
        Err(error) => fail(error),
    }
}

fn confirm(question: &str) -> bool {
    eprint!("{question} [y/N] ");
    let _ = io::stderr().flush();
    let mut answer = String::new();
    io::stdin().read_line(&mut answer).is_ok() && matches!(answer.trim(), "y" | "Y" | "yes")
}

fn remove(config: &Config, args: &[String]) -> i32 {
    let yes = args.iter().any(|arg| arg == "--yes" || arg == "-y");
    let names: Vec<&String> = args.iter().filter(|arg| !arg.starts_with('-')).collect();
    let [name] = names.as_slice() else { return usage("ul lm rm <model> [--yes]") };
    let service = Service::new(config, false);
    let model = match find_model(&service, name) {
        Ok(model) => model,
        Err(message) => return fail(message),
    };
    if !yes {
        if !io::stdin().is_terminal() {
            return fail(format!("Pass --yes to delete {} without a prompt", model.id));
        }
        if !confirm(&format!("Delete {} ({}) from {}?", model.id, human_size(model.bytes), model.root.display())) {
            println!("Kept.");
            return 1;
        }
    }
    match store::remove(&model) {
        Ok(freed) => {
            println!("Deleted {}; {} freed.", model.id, human_size(freed));
            0
        }
        Err(error) => fail(format!("Cannot delete {}: {error}", model.root.display())),
    }
}

fn engine_launch(config: &Config, engine: Engine) -> Result<worker::Launch, i32> {
    engine::ensure(&config.storage_root(), config, engine).map_err(fail)
}

/// `owner/repo` from a repo id or a huggingface.co URL.
fn repo_name(raw: &str) -> Option<String> {
    let trimmed = raw.trim().trim_end_matches('/');
    let path = trimmed.strip_prefix("https://huggingface.co/").or(trimmed.strip_prefix("hf://")).unwrap_or(trimmed);
    let path = path.split("/tree/").next().unwrap_or(path).split("/blob/").next().unwrap_or(path);
    let parts: Vec<&str> = path.split('/').collect();
    match parts.as_slice() {
        [owner, name] if !owner.is_empty() && !name.is_empty() && !path.contains(' ') => Some(format!("{owner}/{name}")),
        _ => None,
    }
}

/// Convert a downloaded model into `storage.root/models/<name>-mlx-<bits>bit`.
fn convert_model(config: &Config, model: &store::Model, bits: u8, trust: bool) -> i32 {
    if !model.kind.runnable() && model.kind != Kind::Other {
        return fail(format!("{} is {}; MLX converters need safetensors weights", model.id, model.kind.describe()));
    }
    let kind = if model.kind == Kind::Other { store::classify(&model.path, &model.id) } else { model.kind };
    if kind == Kind::Video {
        return fail("Video models are converted by mlx-video's own tools; download an MLX build instead (ul lm search Wan2.2 --mlx)");
    }
    let engine = if kind == Kind::Image { Engine::Image } else { Engine::Core };
    let launch = match engine_launch(config, engine) {
        Ok(launch) => launch,
        Err(code) => return code,
    };
    let base = model.id.rsplit('/').next().unwrap_or(&model.id);
    let suffix = if bits == 0 { "mlx".to_string() } else { format!("mlx-{bits}bit") };
    let name = format!("{base}-{suffix}");
    let output = media::unique(&store::local_models(&config.storage_root()).join(&name));
    let name = output.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or(name);
    eprintln!("Converting {} to MLX{} in {}", model.id, if bits == 0 { String::new() } else { format!(" {bits}-bit") }, output.display());
    let args = json!({"source": model.path, "id": model.id, "output": output, "bits": bits, "kind": kind.name(), "trust_remote_code": trust});
    if let Err(code) = engine::hub(&launch, "convert", &args) {
        return code;
    }
    let size = human_size(store::scan(&config.storage_root()).into_iter().find(|m| m.id == format!("local/{name}")).map(|m| m.bytes).unwrap_or(0));
    println!("Ready: local/{name} ({size}). Use it with -m local/{name}");
    0
}

fn convert(config: &Config, args: &[String]) -> i32 {
    let mut name = None;
    let mut bits = 4u8;
    let mut trust = false;
    let mut iter = args.iter();
    while let Some(arg) = iter.next() {
        match arg.as_str() {
            "--bits" | "-b" => match iter.next().and_then(|b| b.parse().ok()).filter(|b| [0, 2, 3, 4, 5, 6, 8].contains(b)) {
                Some(value) => bits = value,
                None => return usage("ul lm convert <model> --bits 2|3|4|5|6|8|0 (0 keeps 16-bit)"),
            },
            "--trust-remote-code" => trust = true,
            other if name.is_none() && !other.starts_with('-') => name = Some(other.to_string()),
            other => return fail(format!("Unexpected argument {other}")),
        }
    }
    let Some(name) = name else { return usage("ul lm convert <model> [--bits 4]") };
    let service = Service::new(config, false);
    let model = match store::find(&service.models(), &name, |_| true) {
        Lookup::Found(model) => model,
        _ => match repo_name(&name) {
            // Not downloaded yet: fetch it first.
            Some(repo) => {
                let code = pull(config, std::slice::from_ref(&repo));
                if code != 0 {
                    return code;
                }
                match store::scan(&config.storage_root()).into_iter().find(|m| m.id == repo) {
                    Some(model) => model,
                    None => return fail(format!("{repo} did not appear in the cache")),
                }
            }
            None => return fail(format!("No downloaded model matches '{name}'; give owner/repo to download it")),
        },
    };
    convert_model(config, &model, bits, trust)
}

fn pull(config: &Config, args: &[String]) -> i32 {
    let mut repo = None;
    let mut include = Vec::new();
    let mut revision = None;
    let mut convert = false;
    let mut bits = 4u8;
    let mut trust = false;
    let mut iter = args.iter();
    while let Some(arg) = iter.next() {
        match arg.as_str() {
            "--include" => match iter.next() {
                Some(glob) => include.push(glob.clone()),
                None => return usage("ul lm pull <repo> --include <glob>"),
            },
            "--revision" => revision = iter.next().cloned(),
            "--convert" => convert = true,
            "--bits" => match iter.next().and_then(|b| b.parse().ok()).filter(|b| [0, 2, 3, 4, 5, 6, 8].contains(b)) {
                Some(value) => bits = value,
                None => return usage("ul lm pull <repo> --convert --bits 2|3|4|5|6|8|0"),
            },
            "--trust-remote-code" => trust = true,
            other if repo.is_none() && !other.starts_with('-') => repo = Some(other.to_string()),
            other => return fail(format!("Unexpected argument {other}")),
        }
    }
    let Some(repo) = repo.as_deref().and_then(repo_name) else {
        return usage("ul lm pull <owner/repo | https://huggingface.co/owner/repo> [--include <glob>] [--convert [--bits N]]");
    };
    let launch = match engine_launch(config, Engine::Core) {
        Ok(launch) => launch,
        Err(code) => return code,
    };
    let cache = store::hub_cache();
    eprintln!("Downloading {repo} into {}", cache.display());
    let result = match engine::hub(&launch, "pull", &json!({"repo": repo, "include": include, "revision": revision, "cache": cache})) {
        Ok(result) => result,
        Err(code) => return code,
    };
    let path = PathBuf::from(result["path"].as_str().unwrap_or(""));
    let Some(model) = store::scan(&config.storage_root()).into_iter().find(|m| m.id == repo) else {
        return fail(format!("{repo} did not appear in {}", cache.display()));
    };
    println!("Downloaded {repo} ({}, {}).", model.kind.name(), human_size(model.bytes));
    if convert {
        return convert_model(config, &model, bits, trust);
    }
    let base = repo.rsplit('/').next().unwrap_or(&repo).to_string();
    match model.kind {
        Kind::Gguf => {
            let base = base.replace("-GGUF", "").replace("-gguf", "");
            println!("GGUF files cannot run on MLX. Look for an MLX build: ul lm search {base} --mlx");
        }
        Kind::Other => println!("No MLX-loadable weights; if it has PyTorch weights try `ul lm convert {repo}`."),
        Kind::Embedding => println!("Use it: ul lm embed -m {base} \"text\"   or POST /v1/embeddings"),
        Kind::Stt => println!("Use it: ul lm transcribe -m {base} recording.m4a"),
        Kind::Tts => println!("Use it: ul lm speak -m {base} \"Hello\" --play"),
        Kind::Music => println!("Use it: ul lm music -m {base} \"lo-fi piano\" --play"),
        Kind::Image => println!("Use it: ul lm image -m {base} \"a red fox in snow\" --open"),
        Kind::Video => println!("Use it: ul lm video -m {base} \"waves at sunset\" --open"),
        Kind::Text | Kind::Vision => {
            let quantized = std::fs::read_to_string(path.join("config.json")).is_ok_and(|text| text.contains("\"quantization\""));
            if !quantized && model.bytes > 6 << 30 {
                println!("Note: unquantized weights need a lot of memory; consider `ul lm convert {repo} --bits 4`.");
            }
            println!("Chat: ul lm -m {base} \"hello\"   Default: ul lm use {base}");
        }
    }
    0
}

fn search(config: &Config, args: &[String]) -> i32 {
    let mut query = Vec::new();
    let mut mlx = false;
    let mut task = None;
    let mut limit = 20u32;
    let mut iter = args.iter();
    while let Some(arg) = iter.next() {
        match arg.as_str() {
            "--mlx" => mlx = true,
            "--task" => task = iter.next().cloned(),
            "--limit" => match iter.next().and_then(|n| n.parse().ok()).filter(|n| (1..=200).contains(n)) {
                Some(n) => limit = n,
                None => return usage("ul lm search <query> [--mlx] [--task <pipeline tag>] [--limit 1-200]"),
            },
            word => query.push(word.to_string()),
        }
    }
    if query.is_empty() {
        return usage("ul lm search <query> [--mlx] [--task text-to-image] [--limit N]");
    }
    let launch = match engine_launch(config, Engine::Core) {
        Ok(launch) => launch,
        Err(code) => return code,
    };
    let rows = match engine::hub(&launch, "search", &json!({"query": query.join(" "), "limit": limit, "mlx": mlx, "task": task})) {
        Ok(rows) => rows,
        Err(code) => return code,
    };
    let rows = rows.as_array().cloned().unwrap_or_default();
    if rows.is_empty() {
        println!("Nothing found{}.", if mlx { " in MLX format; try without --mlx" } else { "" });
        return 0;
    }
    let local: Vec<String> = store::scan(&config.storage_root()).into_iter().map(|m| m.id).collect();
    let width = rows.iter().filter_map(|r| r["id"].as_str()).map(str::len).max().unwrap_or(5);
    println!("  {:width$}  {:>10}  {:6}  TASK", "REPO", "DOWNLOADS", "FORMAT");
    for row in rows {
        let id = row["id"].as_str().unwrap_or("");
        let format = if row["mlx"].as_bool().unwrap_or(false) {
            "MLX"
        } else if row["gguf"].as_bool().unwrap_or(false) {
            "GGUF"
        } else {
            ""
        };
        let mark = if local.iter().any(|l| l == id) { "✓" } else { " " };
        println!("{mark} {id:width$}  {:>10}  {format:6}  {}", row["downloads"].as_u64().unwrap_or(0), row["task"].as_str().unwrap_or(""));
    }
    println!("✓ = downloaded. Get one: ul lm pull <repo>");
    0
}

fn serve(config: &Config, args: &[String]) -> i32 {
    let mut port = None;
    let mut ollama = false;
    let mut trust = false;
    let mut iter = args.iter();
    while let Some(arg) = iter.next() {
        match arg.as_str() {
            "--port" | "-p" => match iter.next().and_then(|p| p.parse::<u16>().ok()).filter(|p| *p > 0) {
                Some(value) => port = Some(value),
                None => return usage("ul lm serve [--port 1-65535] [--ollama] [--cors] [--trust-remote-code]"),
            },
            "--ollama" => ollama = true,
            "--cors" => http::enable_cors(),
            "--trust-remote-code" => trust = true,
            other => return fail(format!("Unknown option {other}")),
        }
    }
    let mut service = Service::new(config, trust);
    if let Some(port) = port {
        service.settings.port = port;
    }
    let mut listeners = Vec::new();
    for port in [Some(service.settings.port), (ollama && service.settings.port != 11434).then_some(11434)].into_iter().flatten() {
        match server::bind(port) {
            Ok(listener) => listeners.push(listener),
            Err(message) => return fail(message),
        }
    }
    // Build the core engine now: the first request should not wait for it.
    if let Err(message) = engine::ensure(&service.storage, config, Engine::Core) {
        return fail(message);
    }
    server::serve(service, listeners)
}

fn ps(config: &Config) -> i32 {
    let port = Settings::from_config(config).port;
    match http::fetch(port, "GET", "/ul/ps", None, Duration::from_millis(500)) {
        Ok(response) if response.header("x-unlaw") == Some("lm") => {
            let body: Value = serde_json::from_slice(&response.body).unwrap_or(Value::Null);
            println!("Server: http://127.0.0.1:{port} (pid {})", body["pid"]);
            let lanes = body["lanes"].as_array().cloned().unwrap_or_default();
            if lanes.iter().all(|lane| lane["loaded"].as_array().is_none_or(Vec::is_empty)) {
                println!("No model loaded (they load on the first request).");
            }
            for lane in lanes {
                for id in lane["loaded"].as_array().into_iter().flatten().filter_map(Value::as_str) {
                    let busy = if lane["busy"].as_u64().unwrap_or(0) > 0 { " (working)" } else { "" };
                    println!("  {id}  [{}]{busy}", lane["lane"].as_str().unwrap_or(""));
                }
            }
            0
        }
        _ => {
            println!("No `ul lm serve` on port {port}. Models load on demand in `ul lm` sessions.");
            0
        }
    }
}

fn import_lmstudio(config: &Config, args: &[String]) -> i32 {
    let mut dry_run = false;
    let mut source = crate::util::home().join(".lmstudio").join("models");
    let mut iter = args.iter();
    while let Some(arg) = iter.next() {
        match arg.as_str() {
            "--dry-run" | "-n" => dry_run = true,
            "--from" => match iter.next() {
                Some(dir) => source = crate::util::expand_user(dir),
                None => return usage("ul lm import-lmstudio [--dry-run] [--from <dir>]"),
            },
            other => return fail(format!("Unknown option {other}")),
        }
    }
    if !source.is_dir() {
        println!("Nothing to import: {} does not exist.", source.display());
        return 0;
    }
    let launch = match engine_launch(config, Engine::Core) {
        Ok(launch) => launch,
        Err(code) => return code,
    };
    let storage = config.storage_root();
    let args = json!({"source": source, "cache": store::hub_cache(), "local": store::local_models(&storage), "dry_run": dry_run});
    let report = match engine::hub(&launch, "import", &args) {
        Ok(report) => report,
        Err(code) => return code,
    };
    let entries = report.as_array().cloned().unwrap_or_default();
    if entries.is_empty() {
        println!("No models found in {}.", source.display());
        return 0;
    }
    for entry in &entries {
        let repo = entry["repo"].as_str().unwrap_or("");
        if entry["kept_local"].as_bool().unwrap_or(false) {
            println!(
                "{} {repo}: not on Hugging Face, {} local/{}",
                if dry_run { "would keep" } else { "kept" },
                if dry_run { "as" } else { "now" },
                repo.rsplit('/').next().unwrap_or(repo)
            );
        } else {
            let skipped = entry["skipped"].as_u64().unwrap_or(0);
            println!(
                "{} {repo}: {} file(s) verified and moved, {} re-downloaded{}",
                if dry_run { "would import" } else { "imported" },
                entry["moved"],
                entry["downloaded"],
                if skipped > 0 { format!(", {skipped} not in the repo dropped") } else { String::new() }
            );
        }
    }
    if dry_run {
        println!("Dry run: nothing changed. Run without --dry-run to import.");
    } else {
        println!("Done. LM Studio is no longer needed: delete ~/.lmstudio and /Applications/LM Studio.app when you like.");
    }
    0
}

fn doctor(config: &Config, args: &[String]) -> i32 {
    let repair = match args {
        [] => false,
        [flag] if flag == "--repair" => true,
        _ => return usage("ul lm doctor [--repair]"),
    };
    let storage = config.storage_root();
    let mut healthy = true;
    for engine in Engine::ALL {
        let needed = engine == Engine::Core || engine::is_ready(&storage, engine);
        if repair && needed {
            if let Err(error) = engine::reset(&storage, engine) {
                return fail(format!("Cannot remove the {} engine: {error}", engine.name()));
            }
        }
        if !needed {
            println!("INFO  {:13} created when a model needs it ({})", engine.name(), engine.size_hint());
            continue;
        }
        let launch = match engine::ensure(&storage, config, engine) {
            Ok(launch) => launch,
            Err(message) => {
                println!("FAIL  {:13} {message}", engine.name());
                healthy = false;
                continue;
            }
        };
        let probe = match engine {
            Engine::Core => "import mlx.core as mx, mlx_lm, mlx_vlm, mlx_embeddings, mlx_audio, mlx_whisper, mlx_video; print(mx.__version__, 'lm', mlx_lm.__version__, 'vlm', mlx_vlm.__version__, 'metal' if mx.metal.is_available() else 'NO METAL')",
            Engine::Image | Engine::Bonsai => "import mlx.core as mx, mflux; from importlib.metadata import version; print(mx.__version__, 'mflux', version('mflux'), 'metal' if mx.metal.is_available() else 'NO METAL')",
        };
        match std::process::Command::new(&launch.python).args(["-c", probe]).output() {
            Ok(output) if output.status.success() => {
                println!("OK    {:13} mlx {}", engine.name(), String::from_utf8_lossy(&output.stdout).trim())
            }
            Ok(output) => {
                healthy = false;
                let error = String::from_utf8_lossy(&output.stderr);
                println!("FAIL  {:13} {} (fix: ul lm doctor --repair)", engine.name(), error.trim().lines().last().unwrap_or("import failed"));
            }
            Err(error) => {
                healthy = false;
                println!("FAIL  {:13} {error}", engine.name());
            }
        }
    }
    let service = Service::new(config, false);
    let models = service.models();
    let runnable = models.iter().filter(|m| m.kind.runnable() && !m.partial).count();
    println!("OK    {:13} {runnable} runnable of {} in {}", "models", models.len(), store::hub_cache().display());
    for purpose in Purpose::ALL {
        if let Ok(model) = service.resolve(None, purpose) {
            println!("OK    {:13} {} ({})", "default", model.id, purpose.noun());
        }
    }
    let settings = Settings::from_config(config);
    if chat::running_server(settings.port) {
        println!("OK    {:13} http://127.0.0.1:{}/v1", "server", settings.port);
    } else {
        println!("INFO  {:13} not running (ul lm serve)", "server");
    }
    let memory = worker::physical_memory();
    println!("INFO  {:13} {} RAM; models up to {} load", "memory", human_size(memory), human_size(memory / 4 * 3 / 6 * 5));
    println!("INFO  {:13} {}", "logs", engine::engine_dir(&storage).join("worker*.log").display());
    if healthy {
        0
    } else {
        1
    }
}

/// `ul doctor` row: is the core engine installed with the current pins?
pub fn engine_status(storage: &Path) -> (bool, String) {
    if engine::is_ready(storage, Engine::Core) {
        (true, engine::engine_dir(storage).display().to_string())
    } else {
        (false, "created on first `ul lm` use (about 1.2 GB)".into())
    }
}

/// `ul doctor` row: is a `ul lm serve` answering on lm.port?
pub fn server_status(port: u16) -> (bool, String) {
    if chat::running_server(port) {
        (true, format!("listening at 127.0.0.1:{port}"))
    } else {
        (false, format!("not running on port {port}; start with `ul lm serve`"))
    }
}

/// The prompt from the arguments, plus piped stdin when there is any.
fn prompt_with_stdin(words: &[String]) -> String {
    let mut prompt = words.join(" ");
    if !io::stdin().is_terminal() {
        let mut piped = String::new();
        if io::stdin().read_to_string(&mut piped).is_ok() && !piped.trim().is_empty() {
            let piped = piped.trim_end();
            prompt = if prompt.is_empty() { piped.to_string() } else { format!("{prompt}\n\n{piped}") };
        }
    }
    prompt
}

pub fn run(args: &[String], config: &Config) -> i32 {
    if args.iter().any(|arg| arg == "-h" || arg == "--help") || args.first().is_some_and(|arg| arg == "help") {
        print!("{HELP}");
        return 0;
    }
    let (first, rest) = match args.split_first() {
        Some((first, rest)) if SUBCOMMANDS.contains(&first.as_str()) => (first.as_str(), rest),
        _ => ("", args),
    };
    match first {
        "list" | "ls" => return list(config, rest),
        "info" => return info(config, rest),
        "use" => return use_model(config, rest),
        "rm" => return remove(config, rest),
        "pull" => return pull(config, rest),
        "convert" => return convert(config, rest),
        "search" => return search(config, rest),
        "serve" => return serve(config, rest),
        "ps" => return ps(config),
        "import-lmstudio" => return import_lmstudio(config, rest),
        "doctor" => return doctor(config, rest),
        _ => {}
    }
    let (mut options, words) = match parse_options(rest) {
        Ok(parsed) => parsed,
        Err(message) => return fail(message),
    };
    let service = Service::new(config, false);
    match first {
        "embed" if words.is_empty() => usage("ul lm embed \"<text>\"... [-m <model>]"),
        "embed" => chat::embed(&service, words, &options),
        "transcribe" => match words.as_slice() {
            [audio] => chat::transcribe(&service, Path::new(audio), &options),
            _ => usage("ul lm transcribe <audio|video> [-m <model>] [-l <language>] [--srt|--json]"),
        },
        "image" | "video" | "speak" | "say" | "music" => {
            let prompt = prompt_with_stdin(&words);
            if prompt.trim().is_empty() {
                return usage(&format!("ul lm {first} \"<{}>\" [options]", if matches!(first, "speak" | "say") { "text" } else { "prompt" }));
            }
            match first {
                "image" => chat::image(&service, &prompt, &options),
                "video" => chat::video(&service, &prompt, &options),
                "music" => chat::music(&service, &prompt, &options),
                _ => chat::speak(&service, &prompt, &options),
            }
        }
        "chat" => {
            if let [model] = words.as_slice() {
                options.model = Some(model.clone());
            } else if !words.is_empty() {
                return usage("ul lm chat [model] [options]");
            }
            chat::interactive(&service, options)
        }
        _ => {
            let prompt = prompt_with_stdin(&words);
            if !prompt.trim().is_empty() {
                chat::one_shot(&service, prompt, &options)
            } else if io::stdin().is_terminal() {
                chat::interactive(&service, options)
            } else {
                usage("ul lm \"<prompt>\" (stdin was empty)")
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn words(items: &[&str]) -> Vec<String> {
        items.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn options_and_prompt_words_are_separated() {
        let (options, prompt) = parse_options(&words(&["-m", "qwen", "-i", "a.png", "--no-think", "-t", "0.2", "what", "is", "-x"])).unwrap();
        assert_eq!(options.model.as_deref(), Some("qwen"));
        assert_eq!(options.images, ["a.png"]);
        assert_eq!((options.think, options.temperature), (Some(false), Some(0.2)));
        // Once the prompt started, dashes are just words.
        assert_eq!(prompt, ["what", "is", "-x"]);
        let (_, prompt) = parse_options(&words(&["--", "-m", "is a word"])).unwrap();
        assert_eq!(prompt, ["-m", "is a word"]);
        let (media, _) = parse_options(&words(&["--size", "832x480", "--seconds", "2", "--voice", "serena", "-q", "4", "--open", "--srt"])).unwrap();
        assert_eq!((media.size, media.seconds, media.voice.as_deref(), media.quantize), (Some((832, 480)), Some(2.0), Some("serena"), Some(4)));
        assert!(media.open && media.srt);
        for bad in [&["--bogus"][..], &["-t", "3"], &["-n", "0"], &["-m"], &["--size", "huge"], &["-q", "7"], &["--steps", "x"]] {
            assert!(parse_options(&words(bad)).is_err(), "{bad:?}");
        }
    }

    #[test]
    fn repo_names_come_from_ids_and_urls() {
        assert_eq!(repo_name("mlx-community/Qwen3-8B-4bit").as_deref(), Some("mlx-community/Qwen3-8B-4bit"));
        assert_eq!(repo_name("https://huggingface.co/mlx-community/Qwen3-8B-4bit/tree/main").as_deref(), Some("mlx-community/Qwen3-8B-4bit"));
        assert_eq!(repo_name("hf://a/b/").as_deref(), Some("a/b"));
        assert_eq!(repo_name("qwen"), None);
        assert_eq!(repo_name("a/b/c"), None);
    }
}
