//! What the CLI and the HTTP server share: settings, one worker process per
//! lane (chat, helper models, images, video), memory accounting across them,
//! and choosing a model by name or the configured default.

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::{Arc, Mutex, PoisonError};
use std::time::{Duration, Instant};

use serde_json::{json, Value};

use super::engine;
use super::store::{self, human_size, Kind, Lookup, Model};
use super::worker::{physical_memory, Failure, Supervisor};
use crate::config::{Config, Value as ConfigValue};

#[derive(Clone, Debug)]
pub struct Settings {
    /// `lm.model`; empty or "auto" means "pick one".
    pub model: String,
    /// Defaults for the other purposes (`lm.<purpose>_model`).
    pub defaults: HashMap<&'static str, String>,
    pub port: u16,
    pub idle_minutes: u64,
    pub system_prompt: String,
    pub temperature: f64,
    pub max_tokens: i64,
}

impl Settings {
    pub fn from_config(config: &Config) -> Settings {
        let temperature = match config.get("lm.temperature") {
            Some(ConfigValue::Float(value)) => *value,
            Some(ConfigValue::Int(value)) => *value as f64,
            _ => 0.7,
        };
        let defaults = Purpose::ALL
            .iter()
            .filter_map(|purpose| purpose.setting())
            .map(|key| (key, config.string(key)))
            .collect();
        Settings {
            model: config.string("lm.model"),
            defaults,
            port: u16::try_from(config.int("lm.port")).ok().filter(|port| *port > 0).unwrap_or(1234),
            idle_minutes: u64::try_from(config.int("lm.idle_minutes")).unwrap_or(10),
            system_prompt: config.string("lm.system_prompt"),
            temperature,
            max_tokens: config.int("lm.max_tokens").max(1),
        }
    }

    pub fn default_model(&self) -> Option<&str> {
        self.default_for(Purpose::Chat)
    }

    pub fn default_for(&self, purpose: Purpose) -> Option<&str> {
        let configured = match purpose.setting() {
            None => self.model.as_str(),
            Some(key) => self.defaults.get(key).map(String::as_str).unwrap_or(""),
        };
        let configured = configured.trim();
        (!configured.is_empty() && configured != "auto").then_some(configured)
    }
}

/// What a request needs the model for.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Purpose {
    Chat,
    Embed,
    Transcribe,
    Speak,
    Music,
    Image,
    Video,
}

impl Purpose {
    pub const ALL: [Purpose; 7] =
        [Purpose::Chat, Purpose::Embed, Purpose::Transcribe, Purpose::Speak, Purpose::Music, Purpose::Image, Purpose::Video];

    pub fn accepts(self, kind: Kind) -> bool {
        match self {
            Purpose::Chat => kind.generates(),
            Purpose::Embed => kind == Kind::Embedding,
            Purpose::Transcribe => kind == Kind::Stt,
            Purpose::Speak => kind == Kind::Tts,
            Purpose::Music => kind == Kind::Music,
            Purpose::Image => kind == Kind::Image,
            Purpose::Video => kind == Kind::Video,
        }
    }

    pub fn for_kind(kind: Kind) -> Option<Purpose> {
        Purpose::ALL.into_iter().find(|purpose| purpose.accepts(kind))
    }

    pub fn noun(self) -> &'static str {
        match self {
            Purpose::Chat => "chat",
            Purpose::Embed => "embedding",
            Purpose::Transcribe => "speech-to-text",
            Purpose::Speak => "text-to-speech",
            Purpose::Music => "music",
            Purpose::Image => "image",
            Purpose::Video => "video",
        }
    }

    /// The config key of this purpose's default model; chat uses `lm.model`.
    pub fn setting(self) -> Option<&'static str> {
        match self {
            Purpose::Chat => None,
            Purpose::Embed => Some("lm.embedding_model"),
            Purpose::Transcribe => Some("lm.stt_model"),
            Purpose::Speak => Some("lm.tts_model"),
            Purpose::Music => Some("lm.music_model"),
            Purpose::Image => Some("lm.image_model"),
            Purpose::Video => Some("lm.video_model"),
        }
    }

    /// A search that finds MLX models for this purpose.
    fn search_hint(self) -> &'static str {
        match self {
            Purpose::Chat => "ul lm search qwen3 --mlx",
            Purpose::Embed => "ul lm search embedding --mlx",
            Purpose::Transcribe => "ul lm search whisper --mlx",
            Purpose::Speak => "ul lm search Qwen3-TTS --mlx",
            Purpose::Music => "ul lm search music --mlx",
            Purpose::Image => "ul lm search bonsai-image",
            Purpose::Video => "ul lm search Wan2.2 --mlx",
        }
    }
}

fn article(word: &str) -> &'static str {
    if word.starts_with(['a', 'e', 'i', 'o', 'u']) {
        "an"
    } else {
        "a"
    }
}

/// Ignore names that clients send to mean "whatever is set up".
fn requested(name: Option<&str>) -> Option<&str> {
    let name = name?.trim();
    (!name.is_empty() && !["default", "auto", "local-model", "local"].contains(&name.to_ascii_lowercase().as_str())).then_some(name)
}

pub struct Service {
    pub storage: PathBuf,
    pub settings: Settings,
    pub trust_remote_code: bool,
    config: Config,
    lanes: Mutex<HashMap<String, Arc<Supervisor>>>,
    /// Scanning the cache stats every file; requests reuse it for a moment.
    scanned: Mutex<Option<(Instant, Vec<Model>)>>,
    memory_limit: u64,
}

impl Service {
    pub fn new(config: &Config, trust_remote_code: bool) -> Service {
        let memory = physical_memory();
        Service {
            storage: config.storage_root(),
            settings: Settings::from_config(config),
            trust_remote_code,
            config: config.clone(),
            lanes: Mutex::new(HashMap::new()),
            scanned: Mutex::new(None),
            memory_limit: if memory == 0 { u64::MAX } else { memory / 4 * 3 },
        }
    }

    pub fn models(&self) -> Vec<Model> {
        let mut scanned = self.scanned.lock().unwrap_or_else(PoisonError::into_inner);
        if let Some((when, models)) = scanned.as_ref() {
            if when.elapsed() < Duration::from_secs(2) {
                return models.clone();
            }
        }
        let models = store::scan(&self.storage);
        *scanned = Some((Instant::now(), models.clone()));
        models
    }

    fn check(&self, model: Model, purpose: Purpose) -> Result<Model, Failure> {
        if model.partial {
            return Err(Failure::new(
                "model_not_found",
                format!("{} is not fully downloaded; resume with `ul lm pull {}`", model.id, model.id),
            ));
        }
        match model.kind {
            Kind::Gguf => Err(Failure::new(
                "unsupported_model",
                format!(
                    "{} is a GGUF model, which MLX cannot run. Find an MLX build with `ul lm search {} --mlx`",
                    model.id,
                    model.id.rsplit('/').next().unwrap_or(&model.id).replace("-GGUF", "").replace("-gguf", "")
                ),
            )),
            Kind::Other => Err(Failure::new(
                "unsupported_model",
                format!("{} has no MLX-loadable weights; convert it with `ul lm convert {}`", model.id, model.id),
            )),
            kind if !purpose.accepts(kind) => Err(Failure::new(
                "unsupported_model",
                format!(
                    "{} is {} {} model ({}); this request needs {} {} model",
                    model.id,
                    article(kind.name()),
                    kind.name(),
                    kind.describe(),
                    article(purpose.noun()),
                    purpose.noun()
                ),
            )),
            _ => Ok(model),
        }
    }

    /// The model a request asked for, else the configured default, else the
    /// loaded one, else the only suitable model.
    pub fn resolve(&self, name: Option<&str>, purpose: Purpose) -> Result<Model, Failure> {
        let models = self.models();
        let wanted = requested(name).or(self.settings.default_for(purpose));
        if let Some(wanted) = wanted {
            return match store::find(&models, wanted, |m| purpose.accepts(m.kind)) {
                Lookup::Found(model) => self.check(model, purpose),
                Lookup::Ambiguous(ids) => {
                    Err(Failure::new("model_not_found", format!("'{wanted}' matches several models: {}", ids.join(", "))))
                }
                Lookup::Missing(close) => {
                    let hint = if close.is_empty() {
                        format!("download it with `ul lm pull {wanted}`")
                    } else {
                        format!("did you mean {}? Or download it with `ul lm pull {wanted}`", close.join(", "))
                    };
                    Err(Failure::new("model_not_found", format!("Model '{wanted}' is not downloaded; {hint}")))
                }
            };
        }
        let suitable: Vec<&Model> = models.iter().filter(|m| purpose.accepts(m.kind) && !m.partial).collect();
        let loaded = self.loaded();
        if let Some(model) = suitable.iter().find(|m| loaded.contains(&m.id)) {
            return Ok((*model).clone());
        }
        match suitable.as_slice() {
            [only] => Ok((*only).clone()),
            [] => Err(Failure::new(
                "model_not_found",
                format!("No {} model is downloaded; find one with `{}`, then `ul lm pull <repo>`", purpose.noun(), purpose.search_hint()),
            )),
            many => Err(Failure::new(
                "model_not_found",
                format!(
                    "{} {} models are downloaded ({}); name one (\"model\": \"...\") or set a default with `ul lm use <model>`",
                    many.len(),
                    purpose.noun(),
                    many.iter().map(|m| m.id.as_str()).collect::<Vec<_>>().join(", ")
                ),
            )),
        }
    }

    pub fn model_spec(&self, model: &Model) -> Value {
        json!({
            "id": model.id,
            "path": model.path,
            "kind": model.kind.name(),
            "trust_remote_code": self.trust_remote_code,
        })
    }

    /// Models loaded in any lane.
    pub fn loaded(&self) -> Vec<String> {
        let lanes = self.lanes.lock().unwrap_or_else(PoisonError::into_inner);
        lanes.values().flat_map(|lane| lane.loaded()).collect()
    }

    fn lane(&self, model: &Model) -> Result<Arc<Supervisor>, Failure> {
        let key = model.lane();
        if let Some(lane) = self.lanes.lock().unwrap_or_else(PoisonError::into_inner).get(&key) {
            return Ok(lane.clone());
        }
        // Building an engine can take minutes; never hold the lanes lock then.
        let launch = engine::ensure(&self.storage, &self.config, model.engine())
            .map_err(|message| Failure::new("engine_unavailable", message))?;
        let mut lanes = self.lanes.lock().unwrap_or_else(PoisonError::into_inner);
        let lane = lanes.entry(key).or_insert_with(|| {
            let lane = Supervisor::new(launch);
            lane.reap_when_idle(Duration::from_secs(self.settings.idle_minutes * 60));
            lane
        });
        Ok(lane.clone())
    }

    /// Make room for `model`: models other lanes hold count too, and idle
    /// lanes are stopped (their memory returns at once) when it would not fit.
    fn make_room(&self, model: &Model, target: &Arc<Supervisor>) -> Result<(), Failure> {
        let needed = model.bytes / 5 * 6;
        let sizes: HashMap<String, u64> = self.models().into_iter().map(|m| (m.id, m.bytes / 5 * 6)).collect();
        let lanes: Vec<Arc<Supervisor>> = self.lanes.lock().unwrap_or_else(PoisonError::into_inner).values().cloned().collect();
        let others: Vec<&Arc<Supervisor>> = lanes.iter().filter(|lane| !Arc::ptr_eq(lane, target)).collect();
        let held = || -> u64 {
            others.iter().flat_map(|lane| lane.loaded()).filter(|id| id != &model.id).map(|id| sizes.get(&id).copied().unwrap_or(0)).sum()
        };
        if held() + needed <= self.memory_limit || target.loaded().contains(&model.id) {
            return Ok(());
        }
        for lane in &others {
            lane.stop_if_idle();
        }
        let still = held();
        if still + needed > self.memory_limit {
            return Err(Failure::new(
                "out_of_memory",
                format!(
                    "{} needs about {} but running jobs hold {} (limit {}); wait for them to finish",
                    model.id,
                    human_size(needed),
                    human_size(still),
                    human_size(self.memory_limit)
                ),
            ));
        }
        Ok(())
    }

    /// Run a worker job for `model`, filling in the model spec and defaults.
    pub fn run(&self, mut job: Value, model: &Model, on_event: impl FnMut(&Value) -> bool) -> Result<Value, Failure> {
        let lane = self.lane(model)?;
        self.make_room(model, &lane)?;
        job["model"] = self.model_spec(model);
        if job.get("defaults").is_none() {
            job["defaults"] = json!({"temperature": self.settings.temperature, "max_tokens": self.settings.max_tokens});
        }
        lane.call(job, Some(model), on_event)
    }

    /// Worker processes that exist: (lane, loaded models, jobs in flight).
    pub fn lanes(&self) -> Vec<(String, Vec<String>, usize)> {
        let lanes = self.lanes.lock().unwrap_or_else(PoisonError::into_inner);
        let mut rows: Vec<_> = lanes.iter().map(|(key, lane)| (key.clone(), lane.loaded(), lane.busy())).collect();
        rows.sort();
        rows
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn placeholder_names_mean_default() {
        assert_eq!(requested(Some("  ")), None);
        assert_eq!(requested(Some("local-model")), None);
        assert_eq!(requested(Some("Default")), None);
        assert_eq!(requested(Some("qwen3")), Some("qwen3"));
        assert_eq!(requested(None), None);
    }

    #[test]
    fn purposes_match_kinds_and_settings() {
        assert!(Purpose::Chat.accepts(Kind::Vision) && Purpose::Chat.accepts(Kind::Text));
        assert!(!Purpose::Chat.accepts(Kind::Embedding));
        assert!(Purpose::Embed.accepts(Kind::Embedding) && Purpose::Transcribe.accepts(Kind::Stt));
        assert_eq!(Purpose::for_kind(Kind::Tts), Some(Purpose::Speak));
        assert_eq!(Purpose::for_kind(Kind::Gguf), None);
        assert_eq!(Purpose::Image.setting(), Some("lm.image_model"));
        assert_eq!(article("image"), "an");
    }
}
