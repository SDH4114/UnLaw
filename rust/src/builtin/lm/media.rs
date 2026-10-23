//! Files around generation: where results go (never overwriting), turning
//! any recording or video into audio the recognisers read, and base64.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use crate::util::which;

/// `storage.root/generated/<kind>/<stamp>-<slug>.<ext>`.
pub fn output_path(storage: &Path, kind: &str, prompt: &str, extension: &str) -> PathBuf {
    let slug: String = prompt
        .chars()
        .map(|c| if c.is_alphanumeric() { c.to_lowercase().next().unwrap_or(c) } else { '-' })
        .collect::<String>()
        .split('-')
        .filter(|part| !part.is_empty())
        .take(6)
        .collect::<Vec<_>>()
        .join("-");
    let slug: String = slug.chars().take(48).collect();
    let name = format!("{}-{}.{extension}", stamp(), if slug.is_empty() { kind } else { &slug });
    unique(&storage.join("generated").join(kind).join(name))
}

/// `name.ext`, else `name 2.ext`, `name 3.ext`... like the rest of Unlaw.
pub fn unique(path: &Path) -> PathBuf {
    if !path.exists() {
        return path.to_path_buf();
    }
    let stem = path.file_stem().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default();
    let extension = path.extension().map(|e| format!(".{}", e.to_string_lossy())).unwrap_or_default();
    (2..)
        .map(|n| path.with_file_name(format!("{stem} {n}{extension}")))
        .find(|candidate| !candidate.exists())
        .expect("an unused name exists")
}

/// Local time as `YYYYMMDD-HHMMSS`.
pub fn stamp() -> String {
    let seconds = super::server::now() as libc::time_t;
    // SAFETY: localtime_r writes into the zeroed tm we own.
    let mut tm: libc::tm = unsafe { std::mem::zeroed() };
    unsafe { libc::localtime_r(&seconds, &mut tm) };
    format!("{:04}{:02}{:02}-{:02}{:02}{:02}", tm.tm_year + 1900, tm.tm_mon + 1, tm.tm_mday, tm.tm_hour, tm.tm_min, tm.tm_sec)
}

/// Formats the speech libraries decode themselves.
const READABLE: [&str; 5] = ["wav", "mp3", "flac", "ogg", "oga"];

/// A recording in a format the recognisers read: m4a, aac, caf, aiff, mp4,
/// mov... are converted to 16 kHz mono WAV with macOS' own afconvert (ffmpeg
/// for anything it cannot open). Returns the path and whether it is temporary.
pub fn readable_audio(input: &Path, scratch: &Path) -> Result<(PathBuf, bool), String> {
    let extension = input.extension().map(|e| e.to_string_lossy().to_ascii_lowercase()).unwrap_or_default();
    if READABLE.contains(&extension.as_str()) {
        return Ok((input.to_path_buf(), false));
    }
    fs::create_dir_all(scratch).map_err(|error| error.to_string())?;
    let output = unique(&scratch.join(format!("audio-{}-{}.wav", std::process::id(), stamp())));
    let quiet = |command: &mut Command| command.stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null()).status();
    let converted = which("afconvert").is_some_and(|tool| {
        quiet(Command::new(tool).args(["-f", "WAVE", "-d", "LEI16@16000", "-c", "1"]).arg(input).arg(&output))
            .is_ok_and(|status| status.success())
    });
    if converted {
        return Ok((output, true));
    }
    if let Some(ffmpeg) = which("ffmpeg") {
        let status = quiet(Command::new(ffmpeg).args(["-y", "-v", "error", "-i"]).arg(input).args(["-vn", "-ac", "1", "-ar", "16000"]).arg(&output));
        if status.is_ok_and(|status| status.success()) {
            return Ok((output, true));
        }
    }
    let _ = fs::remove_file(&output);
    Err(format!("Cannot read the audio of {} (install ffmpeg for unusual formats)", input.display()))
}

pub fn base64(bytes: &[u8]) -> String {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let n = (u32::from(chunk[0]) << 16) | (u32::from(*chunk.get(1).unwrap_or(&0)) << 8) | u32::from(*chunk.get(2).unwrap_or(&0));
        for (index, shift) in [18, 12, 6, 0].into_iter().enumerate() {
            if index <= chunk.len() {
                out.push(TABLE[((n >> shift) & 63) as usize] as char);
            } else {
                out.push('=');
            }
        }
    }
    out
}

/// "1024x768" → (1024, 768).
pub fn parse_size(text: &str) -> Option<(u32, u32)> {
    let (width, height) = text.trim().split_once(['x', 'X', '*'])?;
    let width: u32 = width.trim().parse().ok()?;
    let height: u32 = height.trim().parse().ok()?;
    ((64..=4096).contains(&width) && (64..=4096).contains(&height)).then_some((width, height))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn outputs_are_named_from_the_prompt_and_never_overwrite() {
        let dir = super::super::store::tests::scratch("media");
        let first = output_path(&dir, "images", "A Red fox, in the snow!! at dawn — very cold night", "png");
        assert!(first.starts_with(dir.join("generated").join("images")));
        let name = first.file_name().unwrap().to_string_lossy().into_owned();
        assert!(name.ends_with("-a-red-fox-in-the-snow.png"), "{name}");
        fs::create_dir_all(first.parent().unwrap()).unwrap();
        fs::write(&first, "x").unwrap();
        let second = unique(&first);
        assert!(second.to_string_lossy().ends_with("snow 2.png"));
        assert!(output_path(&dir, "speech", "!!!", "wav").to_string_lossy().ends_with("-speech.wav"));
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn helpers() {
        assert_eq!(base64(b"Man"), "TWFu");
        assert_eq!(base64(b"Ma"), "TWE=");
        assert_eq!(base64(b"M"), "TQ==");
        assert_eq!(parse_size("1024x768"), Some((1024, 768)));
        assert_eq!(parse_size(" 512 X 512 "), Some((512, 512)));
        assert_eq!(parse_size("10x10"), None);
        assert_eq!(parse_size("big"), None);
        let dir = super::super::store::tests::scratch("audio");
        let wav = dir.join("a.wav");
        assert_eq!(readable_audio(&wav, &dir).unwrap(), (wav, false));
        assert!(readable_audio(&dir.join("missing.m4a"), &dir).is_err());
        fs::remove_dir_all(dir).unwrap();
    }
}
