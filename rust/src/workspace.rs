//! Saved project templates: `templates/projects/<name>.toml` with exactly
//! `path`, `app` and `ai`.

use std::collections::BTreeMap;
use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};

use toml_edit::DocumentMut;

use crate::config::templates_dir;
use crate::util::{create_new_atomic, Json};

#[derive(Debug)]
pub struct TemplateError(pub String);

impl fmt::Display for TemplateError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

pub type Result<T> = std::result::Result<T, TemplateError>;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Template {
    pub name: String,
    pub path: PathBuf,
    pub app: String,
    pub ai: bool,
}

pub const ALLOWED_APPS: [&str; 2] = ["obsidian", "zed"];

/// `^[a-z][a-z0-9_-]*$`, shared with command names.
pub fn valid_name(name: &str) -> bool {
    let mut chars = name.chars();
    matches!(chars.next(), Some('a'..='z'))
        && chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_' || c == '-')
}

pub fn validate_name(name: &str) -> Result<()> {
    if valid_name(name) {
        Ok(())
    } else {
        Err(TemplateError(
            "Invalid template name: use a lowercase letter followed by lowercase letters, numbers, '-' or '_'.".into(),
        ))
    }
}

pub fn templates_projects_dir() -> PathBuf {
    templates_dir().join("projects")
}

pub fn manifest_path(name: &str) -> Result<PathBuf> {
    validate_name(name)?;
    Ok(templates_projects_dir().join(format!("{name}.toml")))
}

fn invalid(name: &str, detail: &str) -> TemplateError {
    TemplateError(format!("Invalid template {name}: {detail}"))
}

fn from_document(name: &str, document: &DocumentMut) -> Result<Template> {
    const FIELDS: [&str; 3] = ["ai", "app", "path"];
    let keys: Vec<&str> = document.iter().map(|(key, _)| key).collect();
    let mut unknown: Vec<&str> = keys.iter().copied().filter(|key| !FIELDS.contains(key)).collect();
    if !unknown.is_empty() {
        unknown.sort_unstable();
        return Err(invalid(name, &format!("unknown fields: {}", unknown.join(", "))));
    }
    let missing: Vec<&str> = FIELDS.iter().copied().filter(|field| !keys.contains(field)).collect();
    if !missing.is_empty() {
        return Err(invalid(name, &format!("missing fields: {}", missing.join(", "))));
    }
    let path = document["path"].as_str().filter(|path| Path::new(path).is_absolute());
    let Some(path) = path else {
        return Err(invalid(name, "path must be absolute"));
    };
    let app = document["app"].as_str().filter(|app| ALLOWED_APPS.contains(app));
    let Some(app) = app else {
        return Err(invalid(name, "app must be zed or obsidian"));
    };
    let Some(ai) = document["ai"].as_bool() else {
        return Err(invalid(name, "ai must be true or false"));
    };
    Ok(Template { name: name.into(), path: path.into(), app: app.into(), ai })
}

pub fn load(name: &str) -> Result<Template> {
    let path = manifest_path(name)?;
    let document = fs::read_to_string(&path)
        .map_err(|error| error.to_string())
        .and_then(|text| text.parse::<DocumentMut>().map_err(|error| error.to_string().trim_end().to_string()))
        .map_err(|error| TemplateError(format!("Could not read template {name}: {error}")))?;
    from_document(name, &document)
}

pub fn exists(name: &str) -> bool {
    valid_name(name) && templates_projects_dir().join(format!("{name}.toml")).is_file()
}

pub fn discover() -> Result<BTreeMap<String, Template>> {
    let mut found = BTreeMap::new();
    let Ok(entries) = fs::read_dir(templates_projects_dir()) else {
        return Ok(found);
    };
    let mut names: Vec<String> = entries
        .flatten()
        .filter_map(|entry| entry.file_name().to_str()?.strip_suffix(".toml").map(str::to_string))
        .filter(|stem| !stem.is_empty())
        .collect();
    names.sort();
    for name in names {
        validate_name(&name)?;
        let template = load(&name)?;
        found.insert(name, template);
    }
    Ok(found)
}

pub fn create(name: &str, path: &Path, app: &str, ai: bool) -> Result<Template> {
    validate_name(name)?;
    let resolved = fs::canonicalize(path)
        .ok()
        .filter(|resolved| resolved.is_dir())
        .ok_or_else(|| TemplateError(format!("Project directory does not exist: {}", path.display())))?;
    if !ALLOWED_APPS.contains(&app) {
        return Err(invalid(name, "app must be zed or obsidian"));
    }
    let destination = manifest_path(name)?;
    if destination.exists() {
        return Err(TemplateError(format!("Template already exists: {name}")));
    }
    let text = format!(
        "path = {}\napp = {}\nai = {ai}\n",
        Json::str(resolved.to_string_lossy()).render(),
        Json::str(app).render()
    );
    create_new_atomic(&destination, &text, &format!(".{name}.")).map_err(|error| {
        if error.kind() == std::io::ErrorKind::AlreadyExists {
            TemplateError(format!("Template already exists: {name}"))
        } else {
            TemplateError(error.to_string())
        }
    })?;
    Ok(Template { name: name.into(), path: resolved, app: app.into(), ai })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parse(text: &str) -> Result<Template> {
        from_document("demo", &text.parse().unwrap())
    }

    #[test]
    fn names_follow_the_command_pattern() {
        assert!(valid_name("hear-me_2"));
        assert!(!valid_name("Bad Name"));
        assert!(!valid_name("2fast"));
        assert!(!valid_name(""));
    }

    #[test]
    fn manifests_are_strict() {
        assert!(parse("path = \"/tmp\"\napp = \"zed\"\nai = true\n").is_ok());
        assert!(parse("path = \"/tmp\"\napp = \"zed\"\nai = true\nextra = 1\n").unwrap_err().0.contains("unknown"));
        assert!(parse("path = \"/tmp\"\napp = \"zed\"\n").unwrap_err().0.contains("missing fields: ai"));
        assert!(parse("path = \"tmp\"\napp = \"zed\"\nai = true\n").unwrap_err().0.contains("absolute"));
        assert!(parse("path = \"/tmp\"\napp = \"code\"\nai = true\n").unwrap_err().0.contains("app"));
        assert!(parse("path = \"/tmp\"\napp = \"zed\"\nai = \"yes\"\n").unwrap_err().0.contains("ai"));
    }

    #[test]
    fn create_validates_before_writing() {
        assert!(create("Bad Name", Path::new("/tmp"), "zed", false).unwrap_err().0.contains("Invalid template name"));
        assert!(create("demo", Path::new("/nonexistent/dir"), "zed", false).unwrap_err().0.contains("does not exist"));
        assert!(create("demo", Path::new("/tmp"), "code", false).unwrap_err().0.contains("app must be zed or obsidian"));
        assert!(manifest_path("../x").is_err());
        assert!(!exists("Bad Name"));
    }
}
