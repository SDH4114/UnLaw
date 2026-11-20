//! ul-rec: the recording engine of `ul capture` on macOS 15+. One process records the screen with
//! ScreenCaptureKit (SCRecordingOutput, with the Mac's sound) and the camera and the microphone with
//! AVFoundation (AVCaptureMovieFileOutput, AVCaptureAudioFileOutput), the way OBS and Cap do it. Every
//! track's start is taken from the same clock, so `capture.py` places the tracks exactly instead of
//! guessing from when separate programs stopped.
//!
//! Usage: ul-rec PLAN.json. SIGINT or SIGTERM ends the recording: every file is finished, then it exits 0.
//! The plan (written by capture.py):
//!   {"events": path, "levels": path,
//!    "screen": {"path", "display": 1-based (1 = main), "area": "X,Y,W,H" points or null, "clicks", "system_audio", "fps"} | null,
//!    "camera": {"path", "device": name|"default", "width", "height", "fps": "30.000000"|null, "bitrate"} | null,
//!    "mic": {"path", "device": name|"default", "format": "wav"|"m4a"} | null}
//! Events, one JSON object per line in `events`:
//!   {"track", "event": "started", "wall": unix seconds} when the track's first data is written,
//!   {"track", "event": "failed", "error"}, {"track", "event": "finished"},
//!   {"event": "ready", "tracks": [...]} once every track started or failed, {"event": "stopped"} at the end.
//! Microphone peaks go to `levels` about ten times a second, in the format of ffmpeg's ametadata filter
//! (`lavfi.astats.Overall.Peak_level=-21.5`), which capture.py already reads.

use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::Path;
use std::sync::atomic::{AtomicBool, AtomicU8, Ordering};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use block2::RcBlock;
use objc2::rc::Retained;
use objc2::runtime::{AnyObject, ProtocolObject};
use objc2::{define_class, msg_send, AllocAnyThread, DefinedClass};
use objc2_av_foundation::{
    AVCaptureAudioFileOutput, AVCaptureDevice, AVCaptureDeviceInput, AVCaptureFileOutput,
    AVCaptureFileOutputRecordingDelegate, AVCaptureMovieFileOutput, AVCaptureSession,
    AVFileTypeAppleM4A, AVFileTypeQuickTimeMovie, AVFileTypeWAVE, AVMediaTypeAudio,
    AVMediaTypeVideo, AVVideoAverageBitRateKey, AVVideoCodecKey, AVVideoCodecTypeH264,
    AVVideoCompressionPropertiesKey,
};
use objc2_core_foundation::{kCFRunLoopDefaultMode, CFRunLoop, CGPoint, CGRect, CGSize};
use objc2_core_media::{CMTime, CMVideoFormatDescriptionGetDimensions};
use objc2_foundation::{
    NSArray, NSCopying, NSDictionary, NSError, NSNumber, NSObject, NSObjectProtocol, NSString,
    NSURL,
};
use objc2_screen_capture_kit::{
    SCContentFilter, SCDisplay, SCRecordingOutput, SCRecordingOutputConfiguration,
    SCRecordingOutputDelegate, SCShareableContent, SCStream, SCStreamConfiguration,
    SCStreamDelegate,
};
use serde_json::{json, Value};

const HELP: &str = "ul-rec: the recording engine of `ul capture` (macOS 15 or later).

Usage: ul-rec PLAN.json

Records the screen with the Mac's sound (ScreenCaptureKit), the camera and the microphone
(AVFoundation) in one process, each to its own file, and logs when each track started.
`ul capture record` writes the plan and starts it; SIGINT or SIGTERM finishes every file.
Set UNLAW_CAPTURE_REC=off to record with screencapture and ffmpeg instead.

Needs: Screen Recording, Camera and Microphone permission for the app that runs ul.
Example: ul capture record --camera   (uses ul-rec when it is installed next to ul)
";

const TRACKS: [&str; 3] = ["screen", "camera", "mic"];
const PENDING: u8 = 0;
const STARTED: u8 = 1;
const FAILED: u8 = 2;
const FINISHED: u8 = 3;
static STATE: [AtomicU8; 3] = [
    AtomicU8::new(PENDING),
    AtomicU8::new(PENDING),
    AtomicU8::new(PENDING),
];
static EVENTS: OnceLock<Mutex<File>> = OnceLock::new();
static STOP: AtomicBool = AtomicBool::new(false);

fn wall() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

fn event(value: Value) {
    if let Some(file) = EVENTS.get() {
        if let Ok(mut file) = file.lock() {
            let _ = writeln!(file, "{value}");
            let _ = file.flush();
        }
    }
}

/// A track moves PENDING -> STARTED -> FINISHED, or to FAILED from either; each change is logged once.
fn mark(track: usize, to: u8, error: Option<String>) {
    let state = &STATE[track];
    let from = state.load(Ordering::SeqCst);
    if from == to || from == FINISHED || from == FAILED {
        return;
    }
    state.store(to, Ordering::SeqCst);
    let name = TRACKS[track];
    match to {
        STARTED => event(json!({"track": name, "event": "started", "wall": wall()})),
        FINISHED => event(json!({"track": name, "event": "finished"})),
        _ => {
            let error = error.unwrap_or_else(|| "it stopped".into());
            eprintln!("ul-rec: the {name} recording failed: {error}");
            event(json!({"track": name, "event": "failed", "error": error}));
        }
    }
}

fn describe(error: &NSError) -> String {
    error.localizedDescription().to_string()
}

struct Ivars {
    track: usize,
}

define_class!(
    #[unsafe(super(NSObject))]
    #[name = "UnlawRecDelegate"]
    #[ivars = Ivars]
    struct Delegate;

    unsafe impl NSObjectProtocol for Delegate {}

    unsafe impl SCRecordingOutputDelegate for Delegate {
        #[unsafe(method(recordingOutputDidStartRecording:))]
        fn sc_started(&self, _output: &SCRecordingOutput) {
            mark(self.ivars().track, STARTED, None);
        }
        #[unsafe(method(recordingOutputDidFinishRecording:))]
        fn sc_finished(&self, _output: &SCRecordingOutput) {
            mark(self.ivars().track, FINISHED, None);
        }
        #[unsafe(method(recordingOutput:didFailWithError:))]
        fn sc_failed(&self, _output: &SCRecordingOutput, error: &NSError) {
            mark(self.ivars().track, FAILED, Some(describe(error)));
        }
    }

    unsafe impl SCStreamDelegate for Delegate {
        #[unsafe(method(stream:didStopWithError:))]
        fn stream_stopped(&self, _stream: &SCStream, error: &NSError) {
            mark(self.ivars().track, FAILED, Some(describe(error)));
        }
    }

    unsafe impl AVCaptureFileOutputRecordingDelegate for Delegate {
        #[unsafe(method(captureOutput:didStartRecordingToOutputFileAtURL:fromConnections:))]
        fn av_started(&self, _output: &AVCaptureFileOutput, _url: &NSURL, _connections: &NSArray) {
            mark(self.ivars().track, STARTED, None);
        }
        #[unsafe(method(captureOutput:didFinishRecordingToOutputFileAtURL:fromConnections:error:))]
        fn av_finished(
            &self,
            _output: &AVCaptureFileOutput,
            _url: &NSURL,
            _connections: &NSArray,
            error: Option<&NSError>,
        ) {
            // AVFoundation reports a stop it was asked for as an "error" with the file still usable,
            // so only a missing file counts as a failure.
            let track = self.ivars().track;
            match error {
                Some(error) if !self.file_written(track) => {
                    mark(track, FAILED, Some(describe(error)))
                }
                _ => mark(track, FINISHED, None),
            }
        }
    }
);

static PATHS: OnceLock<[Option<String>; 3]> = OnceLock::new();

impl Delegate {
    fn new(track: usize) -> Retained<Self> {
        let this = Self::alloc().set_ivars(Ivars { track });
        unsafe { msg_send![super(this), init] }
    }

    fn file_written(&self, track: usize) -> bool {
        PATHS
            .get()
            .and_then(|paths| paths[track].as_ref())
            .is_some_and(|path| std::fs::metadata(path).is_ok_and(|m| m.len() > 0))
    }
}

extern "C" fn on_signal(_: libc::c_int) {
    STOP.store(true, Ordering::SeqCst);
}

#[link(name = "CoreGraphics", kind = "framework")]
unsafe extern "C" {
    fn CGGetActiveDisplayList(max: u32, displays: *mut u32, count: *mut u32) -> i32;
    fn CGDisplayBounds(display: u32) -> CGRect;
}

/// Turn the main run loop for a while: AVFoundation delivers some delegate calls through it.
fn spin(seconds: f64) {
    let end = Instant::now() + Duration::from_secs_f64(seconds);
    while Instant::now() < end {
        CFRunLoop::run_in_mode(unsafe { kCFRunLoopDefaultMode }, 0.02, false);
    }
}

/// Wait (turning the run loop) until `done` or the deadline; true when done.
fn wait_until(seconds: f64, mut done: impl FnMut() -> bool) -> bool {
    let end = Instant::now() + Duration::from_secs_f64(seconds);
    while Instant::now() < end {
        if done() {
            return true;
        }
        CFRunLoop::run_in_mode(unsafe { kCFRunLoopDefaultMode }, 0.02, false);
    }
    done()
}

fn url(path: &str) -> Retained<NSURL> {
    NSURL::fileURLWithPath(&NSString::from_str(path))
}

fn text<'a>(value: &'a Value, key: &str) -> Option<&'a str> {
    value.get(key).and_then(Value::as_str)
}

fn fail(message: &str) -> ! {
    eprintln!("ul-rec: {message}");
    event(json!({"event": "error", "error": message}));
    std::process::exit(1);
}

// ---------------------------------------------------------------- screen

struct Screen {
    stream: Retained<SCStream>,
    _recording: Retained<SCRecordingOutput>,
    _delegate: Retained<Delegate>,
}

/// Displays numbered like `screencapture -D`: 1 is the main display, then the others in CoreGraphics order.
fn display_id(number: usize) -> Result<u32, String> {
    let mut ids = [0u32; 16];
    let mut count = 0u32;
    if unsafe { CGGetActiveDisplayList(16, ids.as_mut_ptr(), &mut count) } != 0 || count == 0 {
        // None active: most likely the screen sleeps or the lid is closed.
        return Err("no display is active (is the screen asleep or the lid closed?)".into());
    }
    let active = &ids[..(count as usize).min(ids.len())];
    number
        .checked_sub(1)
        .and_then(|index| active.get(index))
        .copied()
        .ok_or_else(|| format!("there is no display {number} ({} active)", active.len()))
}

fn shareable_display(id: u32) -> Result<Retained<SCDisplay>, String> {
    let (sender, receiver) = std::sync::mpsc::channel::<Result<Retained<SCDisplay>, String>>();
    let handler = RcBlock::new(
        move |content: *mut SCShareableContent, error: *mut NSError| {
            let answer = if let Some(error) = unsafe { error.as_ref() } {
                Err(describe(error))
            } else if let Some(content) = unsafe { content.as_ref() } {
                let displays = unsafe { content.displays() };
                displays
                    .iter()
                    .find(|display| unsafe { display.displayID() } == id)
                    .ok_or_else(|| format!("display {id} is not shareable"))
            } else {
                Err("no screen content".into())
            };
            let _ = sender.send(answer);
        },
    );
    unsafe { SCShareableContent::getShareableContentWithCompletionHandler(&handler) };
    let mut answer = None;
    wait_until(20.0, || {
        if answer.is_none() {
            answer = receiver.try_recv().ok();
        }
        answer.is_some()
    });
    answer.unwrap_or_else(|| Err("macOS did not list the screens in time".into()))
}

fn setup_screen(plan: &Value, path: &str) -> Result<Screen, String> {
    let number = plan.get("display").and_then(Value::as_u64).unwrap_or(1) as usize;
    let id = display_id(number)?;
    let display = shareable_display(id)?;
    let filter = unsafe {
        SCContentFilter::initWithDisplay_excludingWindows(
            SCContentFilter::alloc(),
            &display,
            &NSArray::new(),
        )
    };
    let scale = f64::from(unsafe { filter.pointPixelScale() }).max(1.0);
    let config = unsafe { SCStreamConfiguration::new() };
    let bounds = unsafe { CGDisplayBounds(id) };
    let mut size = (
        unsafe { display.width() } as f64,
        unsafe { display.height() } as f64,
    );
    if let Some(area) = text(plan, "area") {
        let numbers: Vec<f64> = area
            .split(',')
            .filter_map(|part| part.trim().parse().ok())
            .collect();
        if numbers.len() != 4 || numbers[2] <= 0.0 || numbers[3] <= 0.0 {
            return Err(format!("bad area {area}"));
        }
        // The area is in global points like `screencapture -R`; the stream wants the display's own points.
        let rect = CGRect::new(
            CGPoint::new(numbers[0] - bounds.origin.x, numbers[1] - bounds.origin.y),
            CGSize::new(numbers[2], numbers[3]),
        );
        unsafe { config.setSourceRect(rect) };
        size = (numbers[2], numbers[3]);
    }
    let fps = plan
        .get("fps")
        .and_then(Value::as_i64)
        .unwrap_or(60)
        .clamp(1, 120) as i32;
    // H.264 needs even sizes.
    let even = |value: f64| ((value * scale / 2.0).round() as usize * 2).max(2);
    unsafe {
        config.setWidth(even(size.0));
        config.setHeight(even(size.1));
        config.setMinimumFrameInterval(CMTime::new(1, fps));
        config.setShowsCursor(true);
        config.setShowMouseClicks(plan.get("clicks").and_then(Value::as_bool).unwrap_or(true));
        config.setQueueDepth(8);
        let sound = plan
            .get("system_audio")
            .and_then(Value::as_bool)
            .unwrap_or(true);
        config.setCapturesAudio(sound);
        if sound {
            config.setSampleRate(48_000);
            config.setChannelCount(2);
            config.setExcludesCurrentProcessAudio(true);
        }
    }
    let delegate = Delegate::new(0);
    let stream = unsafe {
        SCStream::initWithFilter_configuration_delegate(
            SCStream::alloc(),
            &filter,
            &config,
            Some(ProtocolObject::from_ref(&*delegate)),
        )
    };
    let output = unsafe { SCRecordingOutputConfiguration::new() };
    unsafe {
        output.setOutputURL(&url(path));
        output.setVideoCodecType(AVVideoCodecTypeH264.ok_or("no H.264 codec")?);
        output.setOutputFileType(AVFileTypeQuickTimeMovie.ok_or("no QuickTime file type")?);
    }
    let recording = unsafe {
        SCRecordingOutput::initWithConfiguration_delegate(
            SCRecordingOutput::alloc(),
            &output,
            ProtocolObject::from_ref(&*delegate),
        )
    };
    unsafe { stream.addRecordingOutput_error(&recording) }.map_err(|error| describe(&error))?;
    Ok(Screen {
        stream,
        _recording: recording,
        _delegate: delegate,
    })
}

fn start_screen(screen: &Screen) {
    let handler = RcBlock::new(move |error: *mut NSError| {
        if let Some(error) = unsafe { error.as_ref() } {
            mark(0, FAILED, Some(describe(error)));
        }
    });
    unsafe {
        screen
            .stream
            .startCaptureWithCompletionHandler(Some(&handler))
    };
}

fn stop_screen(screen: &Screen) {
    let handler = RcBlock::new(move |_error: *mut NSError| {});
    unsafe {
        screen
            .stream
            .stopCaptureWithCompletionHandler(Some(&handler))
    };
}

// ---------------------------------------------------------------- camera and microphone

fn find_device(kind: &str, name: &str) -> Option<Retained<AVCaptureDevice>> {
    let media = if kind == "video" {
        unsafe { AVMediaTypeVideo }
    } else {
        unsafe { AVMediaTypeAudio }
    }?;
    if name == "default" {
        return unsafe { AVCaptureDevice::defaultDeviceWithMediaType(media) };
    }
    #[allow(deprecated)]
    let devices = unsafe { AVCaptureDevice::devicesWithMediaType(media) };
    devices
        .iter()
        .find(|device| unsafe { device.localizedName() }.to_string() == name)
}

/// The camera mode capture.py picked (WIDTHxHEIGHT at a framerate), when the device has it.
fn set_camera_mode(device: &AVCaptureDevice, plan: &Value) {
    let (Some(width), Some(height)) = (
        plan.get("width").and_then(Value::as_i64),
        plan.get("height").and_then(Value::as_i64),
    ) else {
        return;
    };
    let fps: f64 = text(plan, "fps")
        .and_then(|value| value.parse().ok())
        .unwrap_or(30.0);
    let formats = unsafe { device.formats() };
    let chosen = formats.iter().find_map(|format| {
        let size = unsafe { CMVideoFormatDescriptionGetDimensions(&format.formatDescription()) };
        if i64::from(size.width) != width || i64::from(size.height) != height {
            return None;
        }
        let ranges = unsafe { format.videoSupportedFrameRateRanges() };
        let range = ranges.iter().find(|range| unsafe { range.minFrameRate() } - 0.5 <= fps && fps <= unsafe { range.maxFrameRate() } + 0.5)?;
        let duration = if (unsafe { range.maxFrameRate() } - fps).abs() < 0.5 {
            unsafe { range.minFrameDuration() }
        } else {
            unsafe { CMTime::new(1000, (fps * 1000.0).round() as i32) }
        };
        Some((format, duration))
    });
    let Some((format, duration)) = chosen else {
        eprintln!(
            "ul-rec: the camera has no {width}x{height} at {fps} fps; it records its own mode"
        );
        return;
    };
    if unsafe { device.lockForConfiguration() }.is_ok() {
        unsafe {
            device.setActiveFormat(&format);
            device.setActiveVideoMinFrameDuration(duration);
            device.setActiveVideoMaxFrameDuration(duration);
            device.unlockForConfiguration();
        }
    }
}

struct Camera {
    session: Retained<AVCaptureSession>,
    output: Retained<AVCaptureMovieFileOutput>,
    delegate: Retained<Delegate>,
    path: String,
}

fn setup_camera(plan: &Value, path: &str) -> Result<Camera, String> {
    let name = text(plan, "device").unwrap_or("default");
    let device = find_device("video", name).ok_or_else(|| format!("no camera named {name}"))?;
    let input = unsafe { AVCaptureDeviceInput::deviceInputWithDevice_error(&device) }
        .map_err(|error| describe(&error))?;
    let session = unsafe { AVCaptureSession::new() };
    let output = unsafe { AVCaptureMovieFileOutput::new() };
    unsafe {
        session.beginConfiguration();
        if !session.canAddInput(&input) {
            session.commitConfiguration();
            return Err("the camera is busy or not allowed".into());
        }
        session.addInput(&input);
        // After the input, so the session keeps the device's mode instead of a preset.
        set_camera_mode(&device, plan);
        if !session.canAddOutput(&output) {
            session.commitConfiguration();
            return Err("the camera cannot record to a file".into());
        }
        session.addOutput(&output);
        session.commitConfiguration();
    }
    if let Some(bitrate) = plan.get("bitrate").and_then(Value::as_i64) {
        set_bitrate(&output, bitrate);
    }
    Ok(Camera {
        session,
        output,
        delegate: Delegate::new(1),
        path: path.into(),
    })
}

/// The camera file's H.264 bitrate (capture.py's camera quality); macOS picks one when this fails.
fn set_bitrate(output: &AVCaptureMovieFileOutput, bitrate: i64) {
    let (Some(video), Some(codec_key), Some(compression_key), Some(bitrate_key), Some(h264)) = (unsafe {
        (
            AVMediaTypeVideo,
            AVVideoCodecKey,
            AVVideoCompressionPropertiesKey,
            AVVideoAverageBitRateKey,
            AVVideoCodecTypeH264,
        )
    }) else {
        return;
    };
    let Some(connection) = (unsafe { output.connectionWithMediaType(video) }) else {
        return;
    };
    let number: Retained<AnyObject> =
        unsafe { Retained::cast_unchecked(NSNumber::new_i64(bitrate)) };
    let properties: Retained<NSDictionary<NSString, AnyObject>> =
        NSDictionary::from_retained_objects(&[bitrate_key], &[number]);
    let codec: Retained<AnyObject> = unsafe { Retained::cast_unchecked(h264.copy()) };
    let properties: Retained<AnyObject> = unsafe { Retained::cast_unchecked(properties) };
    let settings: Retained<NSDictionary<NSString, AnyObject>> =
        NSDictionary::from_retained_objects(&[codec_key, compression_key], &[codec, properties]);
    unsafe { output.setOutputSettings_forConnection(Some(&settings), &connection) };
}

struct Mic {
    session: Retained<AVCaptureSession>,
    output: Retained<AVCaptureAudioFileOutput>,
    delegate: Retained<Delegate>,
    path: String,
    wav: bool,
}

fn setup_mic(plan: &Value, path: &str) -> Result<Mic, String> {
    let name = text(plan, "device").unwrap_or("default");
    let device = find_device("audio", name).ok_or_else(|| format!("no microphone named {name}"))?;
    let input = unsafe { AVCaptureDeviceInput::deviceInputWithDevice_error(&device) }
        .map_err(|error| describe(&error))?;
    let session = unsafe { AVCaptureSession::new() };
    let output = unsafe { AVCaptureAudioFileOutput::new() };
    unsafe {
        session.beginConfiguration();
        if !session.canAddInput(&input) || !session.canAddOutput(&output) {
            session.commitConfiguration();
            return Err("the microphone is busy or not allowed".into());
        }
        session.addInput(&input);
        session.addOutput(&output);
        session.commitConfiguration();
    }
    Ok(Mic {
        session,
        output,
        delegate: Delegate::new(2),
        path: path.into(),
        wav: text(plan, "format") != Some("m4a"),
    })
}

/// The microphone's peak level (dB) from its connection, the way AVFoundation meters it.
fn mic_peak(mic: &Mic) -> Option<f32> {
    let connection = unsafe { mic.output.connectionWithMediaType(AVMediaTypeAudio?) }?;
    let channels = unsafe { connection.audioChannels() };
    channels
        .iter()
        .map(|channel| unsafe { channel.peakHoldLevel() })
        .reduce(f32::max)
}

// ---------------------------------------------------------------- main

fn main() {
    let Some(plan_path) = std::env::args().nth(1) else {
        eprintln!("usage: ul-rec PLAN.json (written by `ul capture record`)");
        std::process::exit(2);
    };
    if plan_path == "--help" || plan_path == "-h" {
        print!("{HELP}");
        return;
    }
    let plan: Value = match std::fs::read_to_string(&plan_path)
        .ok()
        .and_then(|text| serde_json::from_str(&text).ok())
    {
        Some(plan) => plan,
        None => {
            eprintln!("ul-rec: cannot read the plan {plan_path}");
            std::process::exit(2);
        }
    };
    let Some(events) = text(&plan, "events") else {
        eprintln!("ul-rec: the plan has no events file");
        std::process::exit(2);
    };
    match OpenOptions::new().create(true).append(true).open(events) {
        Ok(file) => {
            let _ = EVENTS.set(Mutex::new(file));
        }
        Err(error) => {
            eprintln!("ul-rec: cannot write {events}: {error}");
            std::process::exit(2);
        }
    }
    unsafe {
        libc::signal(libc::SIGINT, on_signal as *const () as libc::sighandler_t);
        libc::signal(libc::SIGTERM, on_signal as *const () as libc::sighandler_t);
    }
    let path_of = |track: &str| {
        plan.get(track)
            .filter(|part| !part.is_null())
            .and_then(|part| text(part, "path"))
            .map(str::to_owned)
    };
    let _ = PATHS.set([path_of("screen"), path_of("camera"), path_of("mic")]);
    let paths = PATHS.get().unwrap();

    // Set everything up first (the slow part), then start all tracks together.
    let screen = paths[0]
        .as_ref()
        .map(|path| setup_screen(&plan["screen"], path));
    let camera = paths[1]
        .as_ref()
        .map(|path| setup_camera(&plan["camera"], path));
    let mic = paths[2].as_ref().map(|path| setup_mic(&plan["mic"], path));
    for (index, setup) in [
        screen.as_ref().map(|s| s.as_ref().err()),
        camera.as_ref().map(|c| c.as_ref().err()),
        mic.as_ref().map(|m| m.as_ref().err()),
    ]
    .into_iter()
    .enumerate()
    {
        if let Some(Some(error)) = setup {
            mark(index, FAILED, Some(error.clone()));
        }
    }
    let screen = screen.and_then(Result::ok);
    let camera = camera.and_then(Result::ok);
    let mic = mic.and_then(Result::ok);
    if screen.is_none() && camera.is_none() && mic.is_none() {
        fail("nothing could be recorded");
    }
    // Sessions take a moment to run; recording starts only once every device delivers.
    if let Some(camera) = &camera {
        unsafe { camera.session.startRunning() };
    }
    if let Some(mic) = &mic {
        unsafe { mic.session.startRunning() };
    }
    if let Some(screen) = &screen {
        start_screen(screen);
    }
    if let Some(camera) = &camera {
        unsafe {
            camera
                .output
                .startRecordingToOutputFileURL_recordingDelegate(
                    &url(&camera.path),
                    ProtocolObject::from_ref(&*camera.delegate),
                )
        };
    }
    if let Some(mic) = &mic {
        let kind = if mic.wav {
            unsafe { AVFileTypeWAVE }
        } else {
            unsafe { AVFileTypeAppleM4A }
        };
        unsafe {
            mic.output
                .startRecordingToOutputFileURL_outputFileType_recordingDelegate(
                    &url(&mic.path),
                    kind.unwrap(),
                    ProtocolObject::from_ref(&*mic.delegate),
                )
        };
    }
    let wanted: Vec<usize> = (0..3).filter(|&track| paths[track].is_some()).collect();
    let settled = |track: &usize| STATE[*track].load(Ordering::SeqCst) != PENDING;
    wait_until(15.0, || {
        wanted.iter().all(settled) || STOP.load(Ordering::SeqCst)
    });
    for &track in &wanted {
        if !settled(&track) {
            mark(track, FAILED, Some("it did not start within 15 s".into()));
        }
    }
    let started: Vec<&str> = wanted
        .iter()
        .filter(|&&track| STATE[track].load(Ordering::SeqCst) == STARTED)
        .map(|&track| TRACKS[track])
        .collect();
    event(json!({"event": "ready", "tracks": started}));

    let levels = text(&plan, "levels").and_then(|path| {
        OpenOptions::new()
            .create(true)
            .append(true)
            .open(Path::new(path))
            .ok()
    });
    let mut levels = levels.filter(|_| mic.is_some());
    let begun = Instant::now();
    let mut frame = 0u64;
    while !STOP.load(Ordering::SeqCst) {
        spin(0.1);
        if let (Some(file), Some(mic)) = (levels.as_mut(), mic.as_ref()) {
            if let Some(peak) = mic_peak(mic) {
                let t = begun.elapsed().as_secs_f64();
                let _ = write!(file, "frame:{frame} pts:{} pts_time:{t:.3}\nlavfi.astats.Overall.Peak_level={peak:.1}\n", (t * 48_000.0) as u64);
                let _ = file.flush();
                frame += 1;
            }
        }
        if wanted
            .iter()
            .all(|&track| STATE[track].load(Ordering::SeqCst) == FAILED)
        {
            event(json!({"event": "stopped"}));
            std::process::exit(1);
        }
    }

    // Stop every track, then wait until each file is finished (a long recording takes a moment).
    if let Some(camera) = &camera {
        unsafe { camera.output.stopRecording() };
    }
    if let Some(mic) = &mic {
        unsafe { mic.output.stopRecording() };
    }
    if let Some(screen) = &screen {
        stop_screen(screen);
    }
    let finished =
        |track: &usize| matches!(STATE[*track].load(Ordering::SeqCst), FINISHED | FAILED);
    wait_until(60.0, || wanted.iter().all(finished));
    for &track in &wanted {
        if STATE[track].load(Ordering::SeqCst) == STARTED
            && paths[track]
                .as_ref()
                .is_some_and(|path| Path::new(path).exists())
        {
            mark(track, FINISHED, None);
        }
    }
    if let Some(camera) = &camera {
        unsafe { camera.session.stopRunning() };
    }
    if let Some(mic) = &mic {
        unsafe { mic.session.stopRunning() };
    }
    event(json!({"event": "stopped"}));
}
