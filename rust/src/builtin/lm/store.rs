//! Local models: the standard Hugging Face hub cache (shared with `hf`,
//! `transformers` and every other tool) plus models converted by `ul lm
//! convert`, which live in `storage.root/models` because they are not repos.

use std::env;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use super::engine::Engine;
use crate::util::{close_matches, home};

/// What a model is for; decides which library (and engine) runs it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    Text,
    Vision,
    Embedding,
    /// Speech to text (Whisper, Parakeet, Qwen3-ASR...).
    Stt,
    /// Text to speech (Qwen3-TTS, Dia, Spark...).
    Tts,
    Music,
    Image,
    Video,
    /// GGUF-only repos: downloadable, but MLX cannot run them.
    Gguf,
    /// No weights MLX can load (datasets of files, PyTorch .bin only...).
    Other,
}

impl Kind {
    pub fn name(self) -> &'static str {
        match self {
            Kind::Text => "text",
            Kind::Vision => "vision",
            Kind::Embedding => "embedding",
            Kind::Stt => "stt",
            Kind::Tts => "tts",
            Kind::Music => "music",
            Kind::Image => "image",
            Kind::Video => "video",
            Kind::Gguf => "gguf",
            Kind::Other => "other",
        }
    }

    pub fn describe(self) -> &'static str {
        match self {
            Kind::Text => "chat",
            Kind::Vision => "chat with images",
            Kind::Embedding => "embeddings",
            Kind::Stt => "speech to text",
            Kind::Tts => "text to speech",
            Kind::Music => "music",
            Kind::Image => "image generation",
            Kind::Video => "video generation",
            Kind::Gguf => "GGUF (not for MLX)",
            Kind::Other => "files",
        }
    }

    pub fn runnable(self) -> bool {
        !matches!(self, Kind::Gguf | Kind::Other)
    }

    /// Chat and completion models.
    pub fn generates(self) -> bool {
        matches!(self, Kind::Text | Kind::Vision)
    }

    /// The worker process a model runs in: chat never waits behind a long
    /// transcription, an embedding batch or a video.
    pub fn lane(self) -> &'static str {
        match self {
            Kind::Text | Kind::Vision => "chat",
            Kind::Embedding | Kind::Stt | Kind::Tts | Kind::Music => "helper",
            Kind::Image => "image",
            Kind::Video => "video",
            Kind::Gguf | Kind::Other => "none",
        }
    }
}

#[derive(Clone, Debug)]
pub struct Model {
    /// `owner/repo` for hub models, `local/<name>` for converted ones.
    pub id: String,
    pub path: PathBuf,
    pub kind: Kind,
    pub bytes: u64,
    /// Some blobs are still `.incomplete`: `ul lm pull` again resumes them.
    pub partial: bool,
    /// The hub cache folder (`models--owner--repo`) or the converted folder.
    pub root: PathBuf,
}

impl Model {
    pub fn engine(&self) -> Engine {
        if self.kind != Kind::Image {
            Engine::Core
        } else if self.path.join("transformer-packed-mflux").is_dir() {
            Engine::Bonsai
        } else {
            Engine::Image
        }
    }

    /// The worker process: engine plus lane.
    pub fn lane(&self) -> String {
        format!("{}:{}", self.engine().name(), self.kind.lane())
    }
}

pub fn hub_cache() -> PathBuf {
    if let Some(cache) = env::var_os("HF_HUB_CACHE").filter(|value| !value.is_empty()) {
        return PathBuf::from(cache);
    }
    if let Some(hf_home) = env::var_os("HF_HOME").filter(|value| !value.is_empty()) {
        return PathBuf::from(hf_home).join("hub");
    }
    home().join(".cache").join("huggingface").join("hub")
}

pub fn local_models(storage: &Path) -> PathBuf {
    storage.join("models")
}

/// `models--owner--repo` → `owner/repo`; hub names never contain `--` at the edges.
fn repo_id(folder: &str) -> Option<String> {
    let rest = folder.strip_prefix("models--")?;
    let (owner, name) = rest.split_once("--")?;
    (!owner.is_empty() && !name.is_empty()).then(|| format!("{owner}/{name}"))
}

#[cfg(test)]
pub fn cache_folder(id: &str) -> String {
    format!("models--{}", id.replace('/', "--"))
}

/// The snapshot `refs/main` points at, else the most recently changed one.
fn snapshot(root: &Path) -> Option<PathBuf> {
    let snapshots = root.join("snapshots");
    if let Ok(reference) = fs::read_to_string(root.join("refs").join("main")) {
        let candidate = snapshots.join(reference.trim());
        if candidate.is_dir() {
            return Some(candidate);
        }
    }
    fs::read_dir(&snapshots)
        .ok()?
        .flatten()
        .filter(|entry| entry.path().is_dir())
        .max_by_key(|entry| entry.metadata().and_then(|meta| meta.modified()).ok())
        .map(|entry| entry.path())
}

/// Total size of the files a snapshot links to (symlinks are followed).
fn size(directory: &Path) -> u64 {
    let Ok(entries) = fs::read_dir(directory) else { return 0 };
    entries
        .flatten()
        .map(|entry| {
            let path = entry.path();
            match fs::metadata(&path) {
                Ok(meta) if meta.is_dir() => size(&path),
                Ok(meta) => meta.len(),
                Err(_) => 0,
            }
        })
        .sum()
}

fn has_incomplete(root: &Path) -> bool {
    fs::read_dir(root.join("blobs"))
        .map(|entries| entries.flatten().any(|entry| entry.file_name().to_string_lossy().ends_with(".incomplete")))
        .unwrap_or(false)
}

fn files_with(directory: &Path, suffix: &str) -> bool {
    fs::read_dir(directory)
        .map(|entries| entries.flatten().any(|entry| entry.file_name().to_string_lossy().ends_with(suffix)))
        .unwrap_or(false)
}

/// Weights at the top or one folder down (diffusers keep them per component).
fn has_weights(directory: &Path) -> bool {
    if files_with(directory, ".safetensors") {
        return true;
    }
    fs::read_dir(directory)
        .map(|entries| entries.flatten().any(|entry| entry.path().is_dir() && files_with(&entry.path(), ".safetensors")))
        .unwrap_or(false)
}

/// `pipeline_tag`, `library_name` and tags from a model card's YAML header.
pub fn card(directory: &Path) -> (String, String, Vec<String>) {
    let text = fs::read_to_string(directory.join("README.md")).unwrap_or_default();
    let Some(header) = text.strip_prefix("---").and_then(|rest| rest.split_once("\n---")).map(|(header, _)| header) else {
        return (String::new(), String::new(), Vec::new());
    };
    let mut pipeline = String::new();
    let mut library = String::new();
    let mut tags = Vec::new();
    let mut in_tags = false;
    for line in header.lines() {
        let trimmed = line.trim();
        if let Some(value) = trimmed.strip_prefix("pipeline_tag:") {
            pipeline = value.trim().trim_matches(['"', '\'']).to_ascii_lowercase();
        } else if let Some(value) = trimmed.strip_prefix("library_name:") {
            library = value.trim().trim_matches(['"', '\'']).to_ascii_lowercase();
        }
        if !line.starts_with(' ') && !line.starts_with('-') {
            in_tags = trimmed == "tags:";
        } else if in_tags {
            if let Some(tag) = trimmed.strip_prefix("- ") {
                tags.push(tag.trim().trim_matches(['"', '\'']).to_ascii_lowercase());
            }
        }
    }
    (pipeline, library, tags)
}

/// Classify a model folder from its card, config and files, without loading it.
pub fn classify(directory: &Path, id: &str) -> Kind {
    let lowered = id.to_ascii_lowercase();
    let exists = |name: &str| directory.join(name).exists();
    let (pipeline, _library, tags) = card(directory);
    let config = fs::read_to_string(directory.join("config.json"))
        .ok()
        .and_then(|text| serde_json::from_str::<serde_json::Value>(&text).ok())
        .unwrap_or(serde_json::Value::Null);
    let mentions = |word: &str| lowered.contains(word) || tags.iter().any(|tag| tag.contains(word));

    // Generators are recognised by their layout first: their cards vary.
    if exists("model_index.json") || exists("transformer-packed-mflux") || (exists("transformer") && exists("vae")) {
        return if pipeline.contains("video") { Kind::Video } else { Kind::Image };
    }
    if (exists("t5_encoder.safetensors") && exists("vae.safetensors")) || exists("connector.safetensors") {
        return Kind::Video;
    }
    if !has_weights(directory) {
        return if files_with(directory, ".gguf") { Kind::Gguf } else { Kind::Other };
    }
    let by_card = match pipeline.as_str() {
        "text-to-image" | "image-to-image" | "unconditional-image-generation" => Some(Kind::Image),
        "text-to-video" | "image-to-video" => Some(Kind::Video),
        "text-to-speech" => Some(Kind::Tts),
        "text-to-audio" => Some(if mentions("music") || mentions("song") { Kind::Music } else { Kind::Tts }),
        "automatic-speech-recognition" => Some(Kind::Stt),
        "feature-extraction" | "sentence-similarity" => Some(Kind::Embedding),
        "image-text-to-text" | "video-text-to-text" | "visual-question-answering" | "image-to-text" | "any-to-any" => Some(Kind::Vision),
        "text-generation" | "text2text-generation" | "conversational" if lowered.contains("embedding") => Some(Kind::Embedding),
        "text-generation" | "text2text-generation" | "conversational" => Some(Kind::Text),
        _ => None,
    };
    if let Some(kind) = by_card {
        return kind;
    }
    let text = |key: &str| config.get(key).and_then(|value| value.as_str()).unwrap_or("").to_ascii_lowercase();
    let architectures: Vec<String> = config
        .get("architectures")
        .and_then(|value| value.as_array())
        .map(|items| items.iter().filter_map(|item| item.as_str()).map(str::to_ascii_lowercase).collect())
        .unwrap_or_default();
    let model_type = text("model_type");
    if model_type == "whisper" || config.get("n_audio_ctx").is_some() || architectures.iter().any(|arch| arch.contains("whisper")) || mentions("asr") {
        return Kind::Stt;
    }
    if mentions("tts") || mentions("kokoro") || model_type.contains("tts") {
        return Kind::Tts;
    }
    if config.get("vision_config").is_some()
        || architectures.iter().any(|arch| arch.contains("vision") || arch.contains("vl") && arch.contains("conditional"))
    {
        return Kind::Vision;
    }
    let encoder = ["bert", "roberta", "xlm-roberta", "nomic_bert", "modernbert", "e5", "gte"];
    if exists("modules.json")
        || exists("sentence_bert_config.json")
        || encoder.contains(&model_type.as_str())
        || architectures.iter().any(|arch| arch.ends_with("model") && (arch.contains("bert") || arch.contains("roberta")))
        || lowered.contains("embed")
    {
        return Kind::Embedding;
    }
    if config.is_null() {
        return Kind::Other;
    }
    Kind::Text
}

fn model_at(id: String, root: PathBuf, path: PathBuf) -> Model {
    let kind = classify(&path, &id);
    let bytes = size(&path);
    let partial = has_incomplete(&root);
    Model { id, path, kind, bytes, partial, root }
}

/// Every downloaded or converted model, sorted by id.
pub fn scan(storage: &Path) -> Vec<Model> {
    scan_in(&hub_cache(), storage)
}

pub fn scan_in(cache: &Path, storage: &Path) -> Vec<Model> {
    let mut models = Vec::new();
    if let Ok(entries) = fs::read_dir(cache) {
        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().into_owned();
            let Some(id) = repo_id(&name) else { continue };
            let root = entry.path();
            if let Some(path) = snapshot(&root) {
                models.push(model_at(id, root, path));
            }
        }
    }
    if let Ok(entries) = fs::read_dir(local_models(storage)) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                let id = format!("local/{}", entry.file_name().to_string_lossy());
                models.push(model_at(id, path.clone(), path));
            }
        }
    }
    models.sort_by_key(|model| model.id.to_ascii_lowercase());
    models
}

#[derive(Debug)]
pub enum Lookup {
    Found(Model),
    Ambiguous(Vec<String>),
    Missing(Vec<String>),
}

/// Resolve `owner/repo`, a repo name, its beginning, or a unique fragment,
/// ignoring case. Among several matches, models `fits` (right kind for the
/// request) win, then runnable ones (an MLX build over its GGUF twin).
pub fn find(models: &[Model], query: &str, fits: impl Fn(&Model) -> bool) -> Lookup {
    let wanted = query.trim().trim_end_matches('/').to_ascii_lowercase();
    let wanted = wanted.strip_prefix("https://huggingface.co/").unwrap_or(&wanted).to_string();
    let pick = |matches: Vec<&Model>| -> Option<Lookup> {
        if matches.is_empty() {
            return None;
        }
        for narrowed in [
            matches.clone(),
            matches.iter().copied().filter(|m| fits(m) && m.kind.runnable()).collect(),
            matches.iter().copied().filter(|m| fits(m)).collect(),
            matches.iter().copied().filter(|m| m.kind.runnable()).collect(),
        ] {
            if narrowed.len() == 1 {
                return Some(Lookup::Found(narrowed[0].clone()));
            }
        }
        Some(Lookup::Ambiguous(matches.iter().map(|m| m.id.clone()).collect()))
    };
    let short = |model: &Model| model.id.rsplit('/').next().unwrap_or(&model.id).to_ascii_lowercase();
    let stages: [&dyn Fn(&Model) -> bool; 4] = [
        &|m| m.id.to_ascii_lowercase() == wanted,
        &|m| short(m) == wanted,
        &|m| short(m).starts_with(&wanted),
        &|m| m.id.to_ascii_lowercase().contains(&wanted),
    ];
    for stage in stages {
        if let Some(found) = pick(models.iter().filter(|m| stage(m)).collect()) {
            return found;
        }
    }
    let names: Vec<String> = models.iter().map(short).collect();
    let close = close_matches(&wanted, &names, 3, 0.5);
    Lookup::Missing(models.iter().filter(|m| close.contains(&short(m))).map(|m| m.id.clone()).collect())
}

/// Delete a converted model (its own folder; hub models go through
/// huggingface_hub, which tracks blobs shared with other repos).
pub fn remove_local(model: &Model) -> io::Result<u64> {
    let bytes = disk_size(&model.root);
    fs::remove_dir_all(&model.root)?;
    Ok(bytes)
}

/// Bytes a folder really takes (symlinks are not followed).
pub fn disk_size(path: &Path) -> u64 {
    let Ok(meta) = fs::symlink_metadata(path) else { return 0 };
    if !meta.is_dir() {
        return if meta.file_type().is_symlink() { 0 } else { meta.len() };
    }
    fs::read_dir(path).map(|entries| entries.flatten().map(|entry| disk_size(&entry.path())).sum()).unwrap_or(0)
}

/// huggingface_hub's download chunk cache (hf_xet); safe to delete.
pub fn xet_cache() -> PathBuf {
    if let Some(cache) = env::var_os("HF_XET_CACHE").filter(|value| !value.is_empty()) {
        return PathBuf::from(cache);
    }
    if let Some(hf_home) = env::var_os("HF_HOME").filter(|value| !value.is_empty()) {
        return PathBuf::from(hf_home).join("xet");
    }
    home().join(".cache").join("huggingface").join("xet")
}

pub fn human_size(bytes: u64) -> String {
    const UNITS: [&str; 5] = ["B", "KB", "MB", "GB", "TB"];
    let mut value = bytes as f64;
    let mut unit = 0;
    while value >= 1024.0 && unit < UNITS.len() - 1 {
        value /= 1024.0;
        unit += 1;
    }
    if unit == 0 {
        format!("{bytes} B")
    } else {
        format!("{value:.1} {}", UNITS[unit])
    }
}

#[cfg(test)]
pub mod tests {
    use super::*;
    use std::os::unix::fs::symlink;

    pub fn scratch(name: &str) -> PathBuf {
        let path = env::temp_dir().join(format!("unlaw-lm-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&path);
        fs::create_dir_all(&path).unwrap();
        path
    }

    /// A hub-cache repo laid out exactly like huggingface_hub does it.
    pub fn fake_repo(cache: &Path, id: &str, files: &[(&str, &str)]) -> PathBuf {
        let root = cache.join(cache_folder(id));
        let snapshot = root.join("snapshots").join("abc123");
        fs::create_dir_all(root.join("blobs")).unwrap();
        fs::create_dir_all(&snapshot).unwrap();
        fs::create_dir_all(root.join("refs")).unwrap();
        fs::write(root.join("refs").join("main"), "abc123").unwrap();
        for (index, (name, content)) in files.iter().enumerate() {
            let blob = root.join("blobs").join(format!("blob{index}"));
            fs::write(&blob, content).unwrap();
            symlink(format!("../../blobs/blob{index}"), snapshot.join(name)).unwrap();
        }
        snapshot
    }

    #[test]
    fn kinds_are_detected_from_cards_configs_and_layouts() {
        let dir = scratch("kinds");
        let make = |name: &str, files: &[(&str, &str)]| {
            let path = dir.join(name);
            for (file, content) in files {
                let target = path.join(file);
                fs::create_dir_all(target.parent().unwrap()).unwrap();
                fs::write(target, content).unwrap();
            }
            path
        };
        let readme = |tag: &str| format!("---\nlibrary_name: mlx\npipeline_tag: {tag}\ntags:\n- mlx\n- music\n---\n# Model\n");
        type Case<'a> = (&'a str, Vec<(&'a str, String)>, Kind);
        let cases: Vec<Case> = vec![
            ("t", vec![("config.json", r#"{"model_type":"qwen3"}"#.into())], Kind::Text),
            ("v", vec![("config.json", r#"{"model_type":"qwen2_5_vl","vision_config":{}}"#.into())], Kind::Vision),
            ("e", vec![("config.json", r#"{"model_type":"bert","architectures":["BertModel"]}"#.into())], Kind::Embedding),
            ("a", vec![("config.json", r#"{"n_mels":128,"n_audio_ctx":1500}"#.into())], Kind::Stt),
            ("s", vec![("config.json", "{}".into()), ("README.md", readme("text-to-speech"))], Kind::Tts),
            ("m", vec![("config.json", "{}".into()), ("README.md", readme("text-to-audio"))], Kind::Music),
            ("vl", vec![("config.json", "{}".into()), ("README.md", readme("image-text-to-text"))], Kind::Vision),
        ];
        for (name, files, expected) in cases {
            let mut all: Vec<(&str, &str)> = files.iter().map(|(f, c)| (*f, c.as_str())).collect();
            all.push(("model.safetensors", "w"));
            assert_eq!(classify(&make(name, &all), &format!("x/{name}")), expected, "{name}");
        }
        let flux = make("f", &[("model_index.json", "{}"), ("transformer/d.safetensors", "w"), ("vae/d.safetensors", "w")]);
        assert_eq!(classify(&flux, "x/flux"), Kind::Image);
        let bonsai = make("b", &[("transformer-packed-mflux/d.safetensors", "w"), ("vae/x.safetensors", "w")]);
        assert_eq!(classify(&bonsai, "prism-ml/bonsai-image"), Kind::Image);
        let wan = make("w", &[("config.json", "{}"), ("model.safetensors", "w"), ("t5_encoder.safetensors", "w"), ("vae.safetensors", "w")]);
        assert_eq!(classify(&wan, "x/wan"), Kind::Video);
        let gguf = make("g", &[("model-Q4_K_M.gguf", "g"), ("README.md", &readme("text-generation"))]);
        assert_eq!(classify(&gguf, "x/gguf"), Kind::Gguf);
        let bin = make("o", &[("config.json", "{}"), ("pytorch_model.bin", "b")]);
        assert_eq!(classify(&bin, "x/old"), Kind::Other);
        assert_eq!(card(&dir.join("m")).2, ["mlx", "music"]);
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn hub_cache_is_scanned_and_names_resolve() {
        let dir = scratch("scan");
        let cache = dir.join("hub");
        let config = r#"{"model_type":"qwen3"}"#;
        fake_repo(&cache, "mlx-community/Qwen3-0.6B-4bit", &[("config.json", config), ("model.safetensors", "1234")]);
        fake_repo(&cache, "mlx-community/Qwen3-8B-4bit", &[("config.json", config), ("model.safetensors", "12345678")]);
        fake_repo(&cache, "unsloth/Qwen3-8B-GGUF", &[("q.gguf", "g")]);
        fs::write(cache.join(cache_folder("mlx-community/Qwen3-8B-4bit")).join("blobs").join("x.incomplete"), "").unwrap();
        fs::create_dir_all(cache.join("datasets--a--b")).unwrap();
        let storage = dir.join("storage");
        fs::create_dir_all(storage.join("models").join("mine-mlx-4bit")).unwrap();
        let models = scan_in(&cache, &storage);
        let ids: Vec<&str> = models.iter().map(|m| m.id.as_str()).collect();
        assert_eq!(ids, ["local/mine-mlx-4bit", "mlx-community/Qwen3-0.6B-4bit", "mlx-community/Qwen3-8B-4bit", "unsloth/Qwen3-8B-GGUF"]);
        assert_eq!(models[1].bytes, config.len() as u64 + 4);
        assert!(models[2].partial && !models[1].partial);
        assert_eq!(models[3].kind, Kind::Gguf);
        assert_eq!(models[1].lane(), "core:chat");

        let found = |query: &str| match find(&models, query, |_| true) {
            Lookup::Found(model) => model.id,
            other => format!("{other:?}"),
        };
        assert_eq!(found("mlx-community/qwen3-0.6b-4bit"), "mlx-community/Qwen3-0.6B-4bit");
        assert_eq!(found("Qwen3-0.6B-4bit"), "mlx-community/Qwen3-0.6B-4bit");
        assert_eq!(found("https://huggingface.co/mlx-community/Qwen3-0.6B-4bit/"), "mlx-community/Qwen3-0.6B-4bit");
        assert_eq!(found("0.6b"), "mlx-community/Qwen3-0.6B-4bit");
        // The MLX build wins over its GGUF twin; both match "8b".
        assert_eq!(found("8b"), "mlx-community/Qwen3-8B-4bit");
        assert!(matches!(find(&models, "qwen3", |_| true), Lookup::Ambiguous(ids) if ids.len() == 3));
        // The request's purpose breaks ties.
        assert!(matches!(find(&models, "qwen3", |m| m.bytes < 28), Lookup::Found(m) if m.id == "mlx-community/Qwen3-0.6B-4bit"));
        // A name's beginning beats a fragment elsewhere ("whisper-tiny" vs "tiny-4bit").
        assert_eq!(found("qwen3-8b"), "mlx-community/Qwen3-8B-4bit");
        assert!(matches!(find(&models, "qwen3-0.6b-8bit", |_| true), Lookup::Missing(close) if close.contains(&"mlx-community/Qwen3-0.6B-4bit".to_string())));
        assert!(matches!(find(&models, "zzz", |_| true), Lookup::Missing(close) if close.is_empty()));

        assert_eq!(remove_local(&models[0]).unwrap(), 0);
        assert!(!storage.join("models").join("mine-mlx-4bit").exists());
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn folder_names_and_sizes() {
        assert_eq!(repo_id("models--mlx-community--Qwen3-0.6B-4bit").as_deref(), Some("mlx-community/Qwen3-0.6B-4bit"));
        assert_eq!(repo_id("datasets--a--b"), None);
        assert_eq!(repo_id("models--broken"), None);
        assert_eq!(repo_id("blobs"), None);
        assert_eq!(cache_folder("a/b"), "models--a--b");
        assert_eq!(human_size(512), "512 B");
        assert_eq!(human_size(5 * 1024 * 1024 * 1024 / 2), "2.5 GB");
    }
}
