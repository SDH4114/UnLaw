//! Language server client: JSON-RPC over stdio, one server per (command, project root).
//!
//! Documents are synced in full on change (simple and robust); positions are
//! converted between ule's char columns and the server's UTF-16 (or UTF-8) units.

use std::collections::{HashMap, HashSet};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc::Sender;
use std::thread;
use std::time::{Duration, Instant};

use serde_json::{json, Value};

use crate::document::{absolute, Diagnostic, Document};
use crate::editor::{Editor, Event};
use crate::picker::{Data, Item};
use crate::syntax::Language;
use crate::text::{byte_at, Pos};
use crate::widgets::{CompletionItem, Popup, PopupKind};

#[derive(Debug)]
enum Pending {
    Initialize,
    Completion { doc: usize },
    Hover,
    Goto(String),
    References,
    Rename,
    Symbols(bool),
    CodeActions,
    ResolveAction,
    Other,
}

#[derive(Debug)]
pub struct Client {
    pub id: usize,
    pub name: String,
    pub command: Vec<String>,
    pub language: String,
    pub root: PathBuf,
    child: Child,
    stdin: ChildStdin,
    next_request: i64,
    pending: HashMap<i64, Pending>,
    pub capabilities: Value,
    pub initialized: bool,
    queue: Vec<Value>,
    utf8: bool,
    /// Open documents and the version last sent.
    pub opened: HashMap<usize, i32>,
    pub progress: HashMap<String, String>,
    pub dead: bool,
    pub started: Instant,
}

#[derive(Debug, Default)]
pub struct Lsp {
    pub clients: Vec<Client>,
    next_id: usize,
    pub failed: HashSet<String>,
    last_sync: Option<Instant>,
    pub deferred: Vec<Event>,
    /// The latest completion request: (client id, request id, doc, line, word start, answered).
    completion: Option<(usize, i64, usize, usize, usize, bool)>,
    /// The server said its last list was incomplete: ask again as the user types.
    pub completion_incomplete: bool,
}

impl std::fmt::Debug for Event {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("Event")
    }
}

pub fn which(program: &str) -> Option<PathBuf> {
    if program.contains('/') {
        return Some(PathBuf::from(program)).filter(|path| path.is_file());
    }
    let path = std::env::var_os("PATH")?;
    std::env::split_paths(&path).map(|dir| dir.join(program)).find(|candidate| candidate.is_file())
}

pub fn uri(path: &Path) -> String {
    let mut out = String::from("file://");
    for byte in path.to_string_lossy().bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'/' | b'-' | b'_' | b'.' | b'~' => out.push(byte as char),
            other => out.push_str(&format!("%{other:02X}")),
        }
    }
    out
}

pub fn path_of(uri: &str) -> Option<PathBuf> {
    let rest = uri.strip_prefix("file://")?;
    let bytes = rest.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] == b'%' && index + 2 < bytes.len() {
            if let Ok(value) = u8::from_str_radix(&rest[index + 1..index + 3], 16) {
                out.push(value);
                index += 3;
                continue;
            }
        }
        out.push(bytes[index]);
        index += 1;
    }
    Some(PathBuf::from(String::from_utf8_lossy(&out).into_owned()))
}

fn language_id(language: &str, path: Option<&Path>) -> String {
    let extension = path.and_then(|path| path.extension()).and_then(|ext| ext.to_str()).unwrap_or("");
    match (language, extension) {
        ("javascript", "jsx") => "javascriptreact".into(),
        ("typescript", "tsx") => "typescriptreact".into(),
        ("shell", _) => "shellscript".into(),
        ("make", _) => "makefile".into(),
        ("html", "vue") => "vue".into(),
        ("html", "svelte") => "svelte".into(),
        ("css", "scss") => "scss".into(),
        ("css", "less") => "less".into(),
        _ => language.to_string(),
    }
}

/// Char column → the server's unit (UTF-16 code units, or bytes with utf-8).
fn to_lsp(line: &str, col: usize, utf8: bool) -> usize {
    if utf8 {
        byte_at(line, col)
    } else {
        line.chars().take(col).map(char::len_utf16).sum()
    }
}

fn from_lsp(line: &str, units: usize, utf8: bool) -> usize {
    let mut used = 0;
    for (index, c) in line.chars().enumerate() {
        if used >= units {
            return index;
        }
        used += if utf8 { c.len_utf8() } else { c.len_utf16() };
    }
    line.chars().count()
}

fn position(doc: &Document, pos: Pos, utf8: bool) -> Value {
    json!({ "line": pos.line, "character": to_lsp(doc.text.line(pos.line), pos.col, utf8) })
}

fn pos_from(text: &crate::text::Text, value: &Value, utf8: bool) -> Pos {
    let line = value.get("line").and_then(Value::as_u64).unwrap_or(0) as usize;
    let character = value.get("character").and_then(Value::as_u64).unwrap_or(0) as usize;
    if line > text.last_line() {
        return text.end();
    }
    Pos::new(line, from_lsp(text.line(line), character, utf8))
}

fn read_message(reader: &mut impl BufRead) -> Option<Value> {
    let mut length = None;
    loop {
        let mut header = String::new();
        if reader.read_line(&mut header).ok()? == 0 {
            return None;
        }
        let header = header.trim_end();
        if header.is_empty() {
            break;
        }
        if let Some(value) = header.strip_prefix("Content-Length:") {
            length = value.trim().parse::<usize>().ok();
        }
    }
    let mut body = vec![0; length?];
    reader.read_exact(&mut body).ok()?;
    serde_json::from_slice(&body).ok()
}

impl Client {
    fn spawn(id: usize, command: &[String], language: &str, root: &Path, tx: Sender<Event>) -> Result<Client, String> {
        let mut child = Command::new(&command[0])
            .args(&command[1..])
            .current_dir(root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|error| format!("{}: {error}", command[0]))?;
        let stdin = child.stdin.take().ok_or("no stdin")?;
        let stdout = child.stdout.take().ok_or("no stdout")?;
        thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            while let Some(message) = read_message(&mut reader) {
                log(id, "←", &message.to_string());
                if tx.send(Event::Lsp(id, message)).is_err() {
                    return;
                }
            }
            let _ = tx.send(Event::LspExit(id, "the server exited".into()));
        });
        let mut client = Client {
            id,
            name: Path::new(&command[0])
                .file_name()
                .map_or_else(|| command[0].clone(), |name| name.to_string_lossy().into_owned()),
            command: command.to_vec(),
            language: language.to_string(),
            root: root.to_path_buf(),
            child,
            stdin,
            next_request: 0,
            pending: HashMap::new(),
            capabilities: Value::Null,
            initialized: false,
            queue: Vec::new(),
            utf8: false,
            opened: HashMap::new(),
            progress: HashMap::new(),
            dead: false,
            started: Instant::now(),
        };
        let root_uri = uri(root);
        let params = json!({
            "processId": std::process::id(),
            "rootUri": root_uri,
            "rootPath": root.to_string_lossy(),
            "workspaceFolders": [{ "uri": root_uri, "name": root.file_name().map(|name| name.to_string_lossy().into_owned()).unwrap_or_default() }],
            "clientInfo": { "name": "ule", "version": env!("CARGO_PKG_VERSION") },
            "capabilities": {
                "general": { "positionEncodings": ["utf-8", "utf-16"] },
                "window": { "workDoneProgress": true, "showMessage": {} },
                "workspace": {
                    "applyEdit": true,
                    "workspaceEdit": { "documentChanges": true, "resourceOperations": ["create", "rename"] },
                    "configuration": true,
                    "workspaceFolders": true,
                    "symbol": { "dynamicRegistration": false },
                    "didChangeConfiguration": { "dynamicRegistration": false },
                },
                "textDocument": {
                    "synchronization": { "didSave": true, "willSave": false, "dynamicRegistration": false },
                    "completion": {
                        "completionItem": {
                            "snippetSupport": true,
                            "documentationFormat": ["markdown", "plaintext"],
                            "deprecatedSupport": true,
                            "labelDetailsSupport": true,
                        },
                        "contextSupport": true,
                    },
                    "hover": { "contentFormat": ["markdown", "plaintext"] },
                    "definition": { "linkSupport": true },
                    "declaration": { "linkSupport": true },
                    "typeDefinition": { "linkSupport": true },
                    "implementation": { "linkSupport": true },
                    "references": {},
                    "rename": { "prepareSupport": false },
                    "formatting": {},
                    "documentSymbol": { "hierarchicalDocumentSymbolSupport": true },
                    "publishDiagnostics": { "relatedInformation": false },
                    "codeAction": {
                        "codeActionLiteralSupport": {
                            "codeActionKind": { "valueSet": ["", "quickfix", "refactor", "refactor.extract", "refactor.inline", "refactor.rewrite", "source", "source.organizeImports"] }
                        },
                        "resolveSupport": { "properties": ["edit"] },
                        "dataSupport": true,
                    },
                    "signatureHelp": { "signatureInformation": { "documentationFormat": ["markdown", "plaintext"] } },
                },
            },
        });
        client.request_raw("initialize", params, Pending::Initialize)?;
        Ok(client)
    }

    fn write(&mut self, message: &Value) -> Result<(), String> {
        let body = message.to_string();
        log(self.id, "→", &body);
        let frame = format!("Content-Length: {}\r\n\r\n{body}", body.len());
        self.stdin.write_all(frame.as_bytes()).and_then(|_| self.stdin.flush()).map_err(|error| {
            self.dead = true;
            format!("{}: {error}", self.name)
        })
    }

    fn request_raw(&mut self, method: &str, params: Value, pending: Pending) -> Result<i64, String> {
        self.next_request += 1;
        let id = self.next_request;
        self.pending.insert(id, pending);
        self.write(&json!({ "jsonrpc": "2.0", "id": id, "method": method, "params": params }))?;
        Ok(id)
    }

    fn notify(&mut self, method: &str, params: Value) {
        let message = json!({ "jsonrpc": "2.0", "method": method, "params": params });
        if self.initialized {
            let _ = self.write(&message);
        } else {
            self.queue.push(message);
        }
    }

    fn reply(&mut self, id: Value, result: Value) {
        let _ = self.write(&json!({ "jsonrpc": "2.0", "id": id, "result": result }));
    }

    fn supports(&self, capability: &str) -> bool {
        match self.capabilities.get(capability) {
            None | Some(Value::Null) | Some(Value::Bool(false)) => false,
            Some(_) => true,
        }
    }

    pub fn status(&self) -> String {
        if !self.initialized {
            return "starting".into();
        }
        self.progress.values().next().cloned().unwrap_or_default()
    }

    fn open_doc(&mut self, doc: &Document) {
        if self.opened.contains_key(&doc.id) {
            return;
        }
        let Some(path) = &doc.path else {
            return;
        };
        self.opened.insert(doc.id, doc.version);
        self.notify(
            "textDocument/didOpen",
            json!({ "textDocument": {
                "uri": uri(path),
                "languageId": language_id(&self.language, Some(path)),
                "version": doc.version,
                "text": doc.content(false),
            }}),
        );
    }

    fn sync_doc(&mut self, doc: &Document) {
        let Some(sent) = self.opened.get(&doc.id).copied() else {
            return;
        };
        if sent == doc.version || !self.initialized {
            return;
        }
        let Some(path) = &doc.path else {
            return;
        };
        self.opened.insert(doc.id, doc.version);
        self.notify(
            "textDocument/didChange",
            json!({
                "textDocument": { "uri": uri(path), "version": doc.version },
                "contentChanges": [{ "text": doc.content(false) }],
            }),
        );
    }
}

/// `ULE_LSP_LOG=/path/file` records all traffic with language servers, for debugging them.
fn log(client: usize, direction: &str, body: &str) {
    let Some(path) = std::env::var_os("ULE_LSP_LOG") else {
        return;
    };
    if let Ok(mut file) = std::fs::OpenOptions::new().create(true).append(true).open(path) {
        let text: String = body.chars().take(4000).collect();
        let _ = writeln!(file, "[{client}] {direction} {text}");
    }
}

/// The project root for a file: the nearest folder with one of `roots` (or .git).
fn find_root(path: &Path, roots: &[String]) -> PathBuf {
    let start = path.parent().unwrap_or(Path::new("/"));
    let mut dir = Some(start);
    let mut git = None;
    while let Some(current) = dir {
        if roots.iter().any(|marker| current.join(marker).exists()) {
            return current.to_path_buf();
        }
        if git.is_none() && current.join(".git").exists() {
            git = Some(current.to_path_buf());
        }
        dir = current.parent();
    }
    git.unwrap_or_else(|| start.to_path_buf())
}

impl Lsp {
    /// Starts (or reuses) the server for `doc` and opens it there.
    pub fn open(&mut self, doc: &Document, lang: &Language, tx: Sender<Event>) -> Result<(), String> {
        let Some(path) = &doc.path else {
            return Ok(());
        };
        let Some(command) = lang.lsp.iter().find(|command| which(&command[0]).is_some()).cloned() else {
            return Ok(());
        };
        let root = find_root(path, &lang.roots);
        let key = format!("{}@{}", command.join(" "), root.display());
        if let Some(client) =
            self.clients.iter_mut().find(|client| !client.dead && client.command == command && client.root == root)
        {
            client.open_doc(doc);
            return Ok(());
        }
        if self.failed.contains(&key) {
            return Ok(());
        }
        self.next_id += 1;
        match Client::spawn(self.next_id, &command, &lang.name, &root, tx) {
            Ok(mut client) => {
                client.open_doc(doc);
                self.clients.push(client);
                Ok(())
            }
            Err(error) => {
                self.failed.insert(key);
                Err(format!("language server: {error}"))
            }
        }
    }

    pub fn close(&mut self, doc: &Document) {
        for client in &mut self.clients {
            if client.opened.remove(&doc.id).is_some() {
                if let Some(path) = &doc.path {
                    client.notify("textDocument/didClose", json!({ "textDocument": { "uri": uri(path) } }));
                }
            }
        }
    }

    pub fn saved(&mut self, doc: &Document) {
        self.sync(&[doc]);
        for client in &mut self.clients {
            if client.opened.contains_key(&doc.id) {
                if let Some(path) = &doc.path {
                    client.notify(
                        "textDocument/didSave",
                        json!({ "textDocument": { "uri": uri(path) }, "text": doc.content(false) }),
                    );
                }
            }
        }
    }

    pub fn sync(&mut self, docs: &[&Document]) {
        for client in &mut self.clients {
            for doc in docs {
                client.sync_doc(doc);
            }
        }
        self.last_sync = Some(Instant::now());
    }

    /// Sends pending changes at most every 100 ms while typing.
    pub fn sync_throttled(&mut self, docs: &[&Document]) {
        if self.last_sync.is_some_and(|last| last.elapsed() < Duration::from_millis(100)) {
            return;
        }
        self.sync(docs);
    }

    fn client_with(&self, doc: usize, capability: &str) -> Option<usize> {
        self.clients.iter().position(|client| {
            !client.dead && client.initialized && client.opened.contains_key(&doc) && client.supports(capability)
        })
    }

    pub fn shutdown(&mut self) {
        for client in &mut self.clients {
            if !client.dead {
                let _ = client.request_raw("shutdown", Value::Null, Pending::Other);
                let message = json!({ "jsonrpc": "2.0", "method": "exit" });
                let _ = client.write(&message);
            }
        }
        let deadline = Instant::now() + Duration::from_millis(300);
        for client in &mut self.clients {
            while Instant::now() < deadline {
                if let Ok(Some(_)) = client.child.try_wait() {
                    break;
                }
                thread::sleep(Duration::from_millis(10));
            }
            let _ = client.child.kill();
            let _ = client.child.wait();
        }
        self.clients.clear();
    }

    pub fn status(&self, doc: usize) -> Option<String> {
        let client = self.clients.iter().find(|client| client.opened.contains_key(&doc))?;
        let status = client.status();
        Some(if status.is_empty() { client.name.clone() } else { format!("{} {status}", client.name) })
    }
}

// --- requests from the editor -------------------------------------------------------------

fn sync_current(ed: &mut Editor) {
    let docs: Vec<&Document> = ed.docs.values().collect();
    ed.lsp.sync(&docs);
}

fn text_position(ed: &Editor, client: usize) -> Value {
    let doc = ed.doc();
    let utf8 = ed.lsp.clients[client].utf8;
    json!({
        "textDocument": { "uri": doc.path.as_ref().map(|path| uri(path)).unwrap_or_default() },
        "position": position(doc, ed.cursor(), utf8),
    })
}

fn no_server(ed: &Editor, what: &str) -> String {
    let name = ed.language_name(ed.doc());
    let lang = ed.doc().lang.and_then(|index| ed.languages.get(index));
    match lang.map(|lang| lang.lsp.clone()).unwrap_or_default().first() {
        Some(command) if which(&command[0]).is_none() => {
            format!("{what}: no language server for {name} (install {})", command[0])
        }
        Some(_) if ed.lsp.clients.iter().any(|client| !client.initialized) => {
            format!("{what}: the language server is still starting")
        }
        Some(_) => format!("{what}: the {name} language server does not support it"),
        None => format!("{what}: no language server configured for {name}"),
    }
}

pub fn request_completion(ed: &mut Editor) -> bool {
    let doc = ed.view().doc;
    let Some(client) = ed.lsp.client_with(doc, "completionProvider") else {
        return false;
    };
    sync_current(ed);
    let mut params = text_position(ed, client);
    let cursor = ed.cursor();
    let before = if cursor.col > 0 { ed.doc().text.line(cursor.line).chars().nth(cursor.col - 1) } else { None };
    if let Some(c) = before.filter(|c| is_trigger(ed, client, *c)) {
        params["context"] = json!({ "triggerKind": 2, "triggerCharacter": c.to_string() });
    } else {
        params["context"] = json!({ "triggerKind": 1 });
    }
    // While a request for this same word is on its way, the answer will be refiltered locally.
    let (word_start, _) = crate::motion::word_before(&ed.doc().text, cursor);
    let client_id = ed.lsp.clients[client].id;
    if let Some((existing, _, wanted_doc, line, start, answered)) = ed.lsp.completion {
        if existing == client_id && wanted_doc == doc && line == cursor.line && start == word_start && !answered && before.is_some_and(|c| c.is_alphanumeric() || c == '_') {
            return true;
        }
    }
    match ed.lsp.clients[client].request_raw("textDocument/completion", params, Pending::Completion { doc }) {
        Ok(id) => {
            ed.lsp.completion = Some((client_id, id, doc, cursor.line, word_start, false));
            true
        }
        Err(_) => false,
    }
}

fn is_trigger(ed: &Editor, client: usize, c: char) -> bool {
    ed.lsp.clients[client]
        .capabilities
        .pointer("/completionProvider/triggerCharacters")
        .and_then(Value::as_array)
        .is_some_and(|chars| chars.iter().any(|item| item.as_str() == Some(&c.to_string())))
}

pub fn is_trigger_char(ed: &Editor, c: char) -> bool {
    let doc = ed.view().doc;
    ed.lsp.client_with(doc, "completionProvider").is_some_and(|client| is_trigger(ed, client, c))
}

pub fn hover(ed: &mut Editor) -> Result<(), String> {
    let doc = ed.view().doc;
    let client = ed.lsp.client_with(doc, "hoverProvider").ok_or_else(|| no_server(ed, "hover"))?;
    sync_current(ed);
    let params = text_position(ed, client);
    ed.lsp.clients[client].request_raw("textDocument/hover", params, Pending::Hover)?;
    Ok(())
}

pub fn goto(ed: &mut Editor, method: &str) -> Result<(), String> {
    let capability = match method {
        "textDocument/declaration" => "declarationProvider",
        "textDocument/typeDefinition" => "typeDefinitionProvider",
        "textDocument/implementation" => "implementationProvider",
        _ => "definitionProvider",
    };
    let doc = ed.view().doc;
    let client = ed.lsp.client_with(doc, capability).ok_or_else(|| no_server(ed, "go to"))?;
    sync_current(ed);
    let params = text_position(ed, client);
    ed.lsp.clients[client].request_raw(method, params, Pending::Goto(method.to_string()))?;
    Ok(())
}

pub fn references(ed: &mut Editor) -> Result<(), String> {
    let doc = ed.view().doc;
    let client = ed.lsp.client_with(doc, "referencesProvider").ok_or_else(|| no_server(ed, "references"))?;
    sync_current(ed);
    let mut params = text_position(ed, client);
    params["context"] = json!({ "includeDeclaration": true });
    ed.lsp.clients[client].request_raw("textDocument/references", params, Pending::References)?;
    Ok(())
}

pub fn rename(ed: &mut Editor, new_name: &str) -> Result<(), String> {
    let doc = ed.view().doc;
    let client = ed.lsp.client_with(doc, "renameProvider").ok_or_else(|| no_server(ed, "rename"))?;
    sync_current(ed);
    let mut params = text_position(ed, client);
    params["newName"] = json!(new_name);
    ed.lsp.clients[client].request_raw("textDocument/rename", params, Pending::Rename)?;
    Ok(())
}

pub fn code_actions(ed: &mut Editor) -> Result<(), String> {
    let doc = ed.view().doc;
    let client = ed.lsp.client_with(doc, "codeActionProvider").ok_or_else(|| no_server(ed, "code actions"))?;
    sync_current(ed);
    let utf8 = ed.lsp.clients[client].utf8;
    let (start, end) = match ed.selection() {
        Some((start, end, _)) => (start, ed.doc().text.next(end).unwrap_or(end)),
        None => {
            let line = ed.cursor().line;
            (Pos::new(line, 0), Pos::new(line, ed.doc().text.line_len(line)))
        }
    };
    let document = ed.doc();
    let diagnostics: Vec<Value> = document
        .diagnostics
        .iter()
        .filter(|diagnostic| diagnostic.start.line <= end.line && diagnostic.end.line >= start.line)
        .map(|diagnostic| {
            json!({
                "range": { "start": position(document, diagnostic.start, utf8), "end": position(document, diagnostic.end, utf8) },
                "severity": diagnostic.severity,
                "message": diagnostic.message,
                "source": diagnostic.source,
            })
        })
        .collect();
    let params = json!({
        "textDocument": { "uri": document.path.as_ref().map(|path| uri(path)).unwrap_or_default() },
        "range": { "start": position(document, start, utf8), "end": position(document, end, utf8) },
        "context": { "diagnostics": diagnostics, "triggerKind": 1 },
    });
    ed.lsp.clients[client].request_raw("textDocument/codeAction", params, Pending::CodeActions)?;
    Ok(())
}

pub fn document_symbols(ed: &mut Editor) -> Result<(), String> {
    let doc = ed.view().doc;
    let client = ed.lsp.client_with(doc, "documentSymbolProvider").ok_or_else(|| no_server(ed, "symbols"))?;
    sync_current(ed);
    let params = json!({ "textDocument": { "uri": ed.doc().path.as_ref().map(|path| uri(path)).unwrap_or_default() } });
    ed.lsp.clients[client].request_raw("textDocument/documentSymbol", params, Pending::Symbols(false))?;
    Ok(())
}

pub fn workspace_symbols(ed: &mut Editor, query: &str) -> Result<(), String> {
    let doc = ed.view().doc;
    let client =
        ed.lsp.client_with(doc, "workspaceSymbolProvider").ok_or_else(|| no_server(ed, "workspace symbols"))?;
    let query = if query.is_empty() {
        crate::motion::word_at(&ed.doc().text, ed.cursor()).map(|(_, _, word)| word).unwrap_or_default()
    } else {
        query.to_string()
    };
    ed.lsp.clients[client].request_raw("workspace/symbol", json!({ "query": query }), Pending::Symbols(true))?;
    Ok(())
}

pub fn apply_code_action(ed: &mut Editor, client: usize, action: Value) -> Result<(), String> {
    let Some(index) = ed.lsp.clients.iter().position(|item| item.id == client) else {
        return Err("the language server is gone".into());
    };
    // A bare Command has a string `command`; a CodeAction has an edit and/or a Command object.
    if action.get("command").and_then(Value::as_str).is_some() {
        let params = json!({ "command": action["command"], "arguments": action.get("arguments").cloned().unwrap_or(json!([])) });
        ed.lsp.clients[index].request_raw("workspace/executeCommand", params, Pending::Other)?;
        return Ok(());
    }
    if action.get("edit").is_none()
        && action.get("data").is_some()
        && ed.lsp.clients[index].capabilities.pointer("/codeActionProvider/resolveProvider").and_then(Value::as_bool)
            == Some(true)
    {
        ed.lsp.clients[index].request_raw("codeAction/resolve", action, Pending::ResolveAction)?;
        return Ok(());
    }
    if let Some(edit) = action.get("edit") {
        apply_workspace_edit(ed, index, edit)?;
    }
    if let Some(command) = action.get("command").filter(|command| command.is_object()) {
        let params = json!({ "command": command["command"], "arguments": command.get("arguments").cloned().unwrap_or(json!([])) });
        ed.lsp.clients[index].request_raw("workspace/executeCommand", params, Pending::Other)?;
    }
    Ok(())
}

/// Formats through the server synchronously (used before saving). Ok(false): no server can.
pub fn format_sync(ed: &mut Editor, doc: usize) -> Result<bool, String> {
    let Some(client) = ed.lsp.client_with(doc, "documentFormattingProvider") else {
        return Ok(false);
    };
    sync_current(ed);
    let tab = ed.tab_width(&ed.docs[&doc]);
    let spaces = ed.indent_unit(&ed.docs[&doc]) != "\t";
    let params = json!({
        "textDocument": { "uri": ed.docs[&doc].path.as_ref().map(|path| uri(path)).unwrap_or_default() },
        "options": { "tabSize": tab, "insertSpaces": spaces, "trimTrailingWhitespace": true, "insertFinalNewline": true },
    });
    let id = ed.lsp.clients[client].request_raw("textDocument/formatting", params, Pending::Other)?;
    let client_id = ed.lsp.clients[client].id;
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err("the language server did not format in time".into());
        }
        match ed.rx.recv_timeout(remaining) {
            Ok(Event::Lsp(from, message))
                if from == client_id
                    && message.get("id").and_then(Value::as_i64) == Some(id)
                    && message.get("method").is_none() =>
            {
                ed.lsp.clients[client].pending.remove(&id);
                if let Some(error) = message.get("error") {
                    return Err(error
                        .get("message")
                        .and_then(Value::as_str)
                        .unwrap_or("formatting failed")
                        .to_string());
                }
                let edits = message.get("result").and_then(Value::as_array).cloned().unwrap_or_default();
                let utf8 = ed.lsp.clients[client].utf8;
                let converted = convert_edits(&ed.docs[&doc].text, &edits, utf8);
                if converted.is_empty() {
                    return Ok(true);
                }
                crate::edit::apply_edits(ed, doc, converted);
                return Ok(true);
            }
            Ok(other) => ed.lsp.deferred.push(other),
            Err(_) => return Err("the language server did not format in time".into()),
        }
    }
}

fn convert_edits(text: &crate::text::Text, edits: &[Value], utf8: bool) -> Vec<(Pos, Pos, String)> {
    edits
        .iter()
        .filter_map(|edit| {
            let range = edit.get("range")?;
            let start = pos_from(text, range.get("start")?, utf8);
            let end = pos_from(text, range.get("end")?, utf8);
            let new_text = edit.get("newText")?.as_str()?.to_string();
            Some((start, end, new_text))
        })
        .collect()
}

/// Loads a document without showing it (for edits in other files).
fn load(ed: &mut Editor, path: &Path) -> Result<usize, String> {
    if let Some(id) = ed.find_doc(path) {
        return Ok(id);
    }
    let id = ed.new_doc_id();
    let doc = Document::open(id, path, &ed.languages).map_err(|error| format!("{}: {error}", path.display()))?;
    ed.docs.insert(id, doc);
    ed.buffers.push(id);
    ed.lsp_open(id);
    Ok(id)
}

fn apply_workspace_edit(ed: &mut Editor, client: usize, edit: &Value) -> Result<usize, String> {
    let utf8 = ed.lsp.clients[client].utf8;
    let mut per_file: Vec<(PathBuf, Vec<Value>)> = Vec::new();
    if let Some(changes) = edit.get("changes").and_then(Value::as_object) {
        for (key, edits) in changes {
            if let Some(path) = path_of(key) {
                per_file.push((path, edits.as_array().cloned().unwrap_or_default()));
            }
        }
    }
    if let Some(changes) = edit.get("documentChanges").and_then(Value::as_array) {
        for change in changes {
            match change.get("kind").and_then(Value::as_str) {
                Some("create") => {
                    if let Some(path) = change.get("uri").and_then(Value::as_str).and_then(path_of) {
                        if let Some(parent) = path.parent() {
                            let _ = std::fs::create_dir_all(parent);
                        }
                        if !path.exists() {
                            std::fs::write(&path, "").map_err(|error| error.to_string())?;
                        }
                    }
                }
                Some("rename") => {
                    let from = change.get("oldUri").and_then(Value::as_str).and_then(path_of);
                    let to = change.get("newUri").and_then(Value::as_str).and_then(path_of);
                    if let (Some(from), Some(to)) = (from, to) {
                        crate::ex::rename_file(ed, &from, &to.to_string_lossy())?;
                    }
                }
                Some(_) => {}
                None => {
                    if let Some(path) = change.pointer("/textDocument/uri").and_then(Value::as_str).and_then(path_of) {
                        per_file
                            .push((path, change.get("edits").and_then(Value::as_array).cloned().unwrap_or_default()));
                    }
                }
            }
        }
    }
    let count = per_file.len();
    for (path, edits) in per_file {
        let id = load(ed, &absolute(&path))?;
        let converted = convert_edits(&ed.docs[&id].text, &edits, utf8);
        crate::edit::apply_edits(ed, id, converted);
    }
    Ok(count)
}

fn locations(ed: &mut Editor, value: &Value, utf8: bool) -> Vec<(PathBuf, Pos, String)> {
    let items: Vec<Value> = match value {
        Value::Array(items) => items.clone(),
        Value::Object(_) => vec![value.clone()],
        _ => Vec::new(),
    };
    let mut out = Vec::new();
    for item in items {
        let uri_value = item.get("uri").or_else(|| item.get("targetUri")).and_then(Value::as_str);
        let range = item.get("range").or_else(|| item.get("targetSelectionRange")).or_else(|| item.get("targetRange"));
        let (Some(uri_value), Some(range)) = (uri_value, range) else {
            continue;
        };
        let Some(path) = path_of(uri_value) else {
            continue;
        };
        // Convert with the document's text when it is open (else read the line from disk).
        let line_number = range.pointer("/start/line").and_then(Value::as_u64).unwrap_or(0) as usize;
        let character = range.pointer("/start/character").and_then(Value::as_u64).unwrap_or(0) as usize;
        let line_text = match ed.find_doc(&path) {
            Some(id) => ed.docs[&id].text.line(line_number).to_string(),
            None => std::fs::read_to_string(&path)
                .ok()
                .and_then(|text| text.lines().nth(line_number).map(str::to_string))
                .unwrap_or_default(),
        };
        let col = from_lsp(&line_text, character, utf8);
        out.push((path, Pos::new(line_number, col), line_text));
    }
    out
}

fn markup_text(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        Value::Array(items) => {
            items.iter().map(markup_text).filter(|text| !text.is_empty()).collect::<Vec<_>>().join("\n\n")
        }
        Value::Object(map) => {
            if let Some(Value::String(text)) = map.get("value") {
                if let Some(Value::String(language)) = map.get("language") {
                    return format!("```{language}\n{text}\n```");
                }
                return text.clone();
            }
            String::new()
        }
        _ => String::new(),
    }
}

const KINDS: [&str; 26] = [
    "",
    "text",
    "method",
    "function",
    "constructor",
    "field",
    "variable",
    "class",
    "interface",
    "module",
    "property",
    "unit",
    "value",
    "enum",
    "keyword",
    "snippet",
    "color",
    "file",
    "reference",
    "folder",
    "enum member",
    "constant",
    "struct",
    "event",
    "operator",
    "type param",
];

const SYMBOL_KINDS: [&str; 27] = [
    "",
    "file",
    "module",
    "namespace",
    "package",
    "class",
    "method",
    "property",
    "field",
    "constructor",
    "enum",
    "interface",
    "function",
    "variable",
    "constant",
    "string",
    "number",
    "boolean",
    "array",
    "object",
    "key",
    "null",
    "enum member",
    "struct",
    "event",
    "operator",
    "type param",
];

fn completion_items(doc: &Document, result: &Value, utf8: bool) -> Vec<CompletionItem> {
    let items = match result {
        Value::Array(items) => items.clone(),
        Value::Object(list) => list.get("items").and_then(Value::as_array).cloned().unwrap_or_default(),
        _ => Vec::new(),
    };
    items
        .iter()
        .take(2000)
        .filter_map(|item| {
            // clangd prefixes labels with a space or • (an include will be added).
            let label = item.get("label")?.as_str()?.trim().trim_start_matches('•').to_string();
            let snippet = item.get("insertTextFormat").and_then(Value::as_u64) == Some(2);
            let escape =
                |text: &str| if snippet { text.to_string() } else { text.replace('\\', "\\\\").replace('$', "\\$") };
            let kind = item
                .get("kind")
                .and_then(Value::as_u64)
                .and_then(|kind| KINDS.get(kind as usize))
                .copied()
                .unwrap_or("");
            let detail = item
                .get("labelDetails")
                .and_then(|details| details.get("description").or_else(|| details.get("detail")))
                .and_then(Value::as_str)
                .or_else(|| item.get("detail").and_then(Value::as_str))
                .unwrap_or("")
                .to_string();
            let edit = item.get("textEdit").and_then(|edit| {
                let range = edit.get("range").or_else(|| edit.get("insert"))?;
                let new_text = edit.get("newText")?.as_str()?;
                Some((
                    pos_from(&doc.text, range.get("start")?, utf8),
                    pos_from(&doc.text, range.get("end")?, utf8),
                    escape(new_text),
                ))
            });
            let insert = item.get("insertText").and_then(Value::as_str).map(escape).unwrap_or_else(|| escape(&label));
            let additional = item
                .get("additionalTextEdits")
                .and_then(Value::as_array)
                .map(|edits| convert_edits(&doc.text, edits, utf8))
                .unwrap_or_default();
            Some(CompletionItem {
                label: label.clone(),
                kind: kind.to_string(),
                detail,
                insert,
                filter: item.get("filterText").and_then(Value::as_str).unwrap_or(&label).to_string(),
                sort: item.get("sortText").and_then(Value::as_str).unwrap_or(&label).to_string(),
                edit,
                additional,
                documentation: item.get("documentation").map(markup_text).unwrap_or_default(),
                preselect: item.get("preselect").and_then(Value::as_bool).unwrap_or(false),
            })
        })
        .collect()
}

fn flatten_symbols(value: &Value, depth: usize, path: &Path, doc: Option<&Document>, utf8: bool, out: &mut Vec<Item>) {
    let Some(items) = value.as_array() else {
        return;
    };
    for symbol in items {
        let name = symbol.get("name").and_then(Value::as_str).unwrap_or("?");
        let kind = symbol
            .get("kind")
            .and_then(Value::as_u64)
            .and_then(|kind| SYMBOL_KINDS.get(kind as usize))
            .copied()
            .unwrap_or("");
        let (target_path, range) = match symbol.get("location") {
            Some(location) => (
                location.get("uri").and_then(Value::as_str).and_then(path_of).unwrap_or_else(|| path.to_path_buf()),
                location.get("range"),
            ),
            None => (path.to_path_buf(), symbol.get("selectionRange").or_else(|| symbol.get("range"))),
        };
        let start = range.and_then(|range| range.get("start"));
        let pos = match (start, doc) {
            (Some(start), Some(doc)) if target_path == path => pos_from(&doc.text, start, utf8),
            (Some(start), _) => Pos::new(
                start.get("line").and_then(Value::as_u64).unwrap_or(0) as usize,
                start.get("character").and_then(Value::as_u64).unwrap_or(0) as usize,
            ),
            _ => Pos::default(),
        };
        let container = symbol.get("containerName").and_then(Value::as_str).filter(|name| !name.is_empty());
        let label = format!("{}{name}", "  ".repeat(depth));
        let detail = match container {
            Some(container) => format!("{kind} · {container}"),
            None => kind.to_string(),
        };
        out.push(Item { label, detail, data: Data::Location(target_path.clone(), pos) });
        if let Some(children) = symbol.get("children") {
            flatten_symbols(children, depth + 1, path, doc, utf8, out);
        }
    }
}

// --- messages from servers ----------------------------------------------------------------

pub fn handle(ed: &mut Editor, client_id: usize, message: Value) {
    let Some(index) = ed.lsp.clients.iter().position(|client| client.id == client_id) else {
        return;
    };
    let method = message.get("method").and_then(Value::as_str).map(str::to_string);
    match (method, message.get("id").cloned()) {
        (Some(method), Some(id)) => {
            server_request(ed, index, &method, id, message.get("params").cloned().unwrap_or(Value::Null))
        }
        (Some(method), None) => notification(ed, index, &method, message.get("params").cloned().unwrap_or(Value::Null)),
        (None, Some(id)) => {
            let Some(id) = id.as_i64() else {
                return;
            };
            let Some(pending) = ed.lsp.clients[index].pending.remove(&id) else {
                return;
            };
            if let Some(error) = message.get("error") {
                let text = error.get("message").and_then(Value::as_str).unwrap_or("error");
                // Cancelled or "content modified" requests are routine.
                let code = error.get("code").and_then(Value::as_i64).unwrap_or(0);
                if !matches!(pending, Pending::Completion { .. } | Pending::Hover) && code != -32800 && code != -32801 {
                    ed.error(format!("{}: {text}", ed.lsp.clients[index].name));
                }
                return;
            }
            response(ed, index, pending, message.get("result").cloned().unwrap_or(Value::Null), id);
        }
        (None, None) => {}
    }
}

fn server_request(ed: &mut Editor, index: usize, method: &str, id: Value, params: Value) {
    let result = match method {
        "workspace/configuration" => {
            let count = params.get("items").and_then(Value::as_array).map_or(1, Vec::len);
            Value::Array(vec![Value::Null; count])
        }
        "workspace/applyEdit" => {
            let applied = params.get("edit").map(|edit| apply_workspace_edit(ed, index, edit).is_ok()).unwrap_or(false);
            json!({ "applied": applied })
        }
        "workspace/workspaceFolders" => {
            let root = &ed.lsp.clients[index].root;
            json!([{ "uri": uri(root), "name": root.file_name().map(|name| name.to_string_lossy().into_owned()).unwrap_or_default() }])
        }
        "window/showMessageRequest" => {
            if let Some(text) = params.get("message").and_then(Value::as_str) {
                ed.info(text.to_string());
            }
            Value::Null
        }
        "window/showDocument" => {
            if let Some(path) = params.get("uri").and_then(Value::as_str).and_then(path_of) {
                let _ = ed.open(&path);
            }
            json!({ "success": true })
        }
        _ => Value::Null,
    };
    ed.lsp.clients[index].reply(id, result);
}

fn notification(ed: &mut Editor, index: usize, method: &str, params: Value) {
    match method {
        "textDocument/publishDiagnostics" => {
            let Some(path) = params.get("uri").and_then(Value::as_str).and_then(path_of) else {
                return;
            };
            let Some(doc_id) = ed.find_doc(&path) else {
                return;
            };
            let utf8 = ed.lsp.clients[index].utf8;
            let source_name = ed.lsp.clients[index].name.clone();
            let doc = ed.docs.get_mut(&doc_id).expect("document");
            let items = params.get("diagnostics").and_then(Value::as_array).cloned().unwrap_or_default();
            doc.diagnostics = items
                .iter()
                .filter_map(|item| {
                    let range = item.get("range")?;
                    Some(Diagnostic {
                        start: pos_from(&doc.text, range.get("start")?, utf8),
                        end: pos_from(&doc.text, range.get("end")?, utf8),
                        severity: item.get("severity").and_then(Value::as_u64).unwrap_or(1).clamp(1, 4) as u8,
                        message: item.get("message").and_then(Value::as_str).unwrap_or("").to_string(),
                        source: item
                            .get("source")
                            .and_then(Value::as_str)
                            .map_or_else(|| source_name.clone(), str::to_string),
                    })
                })
                .collect();
            ed.needs_redraw = true;
        }
        "window/showMessage" => {
            let kind = params.get("type").and_then(Value::as_u64).unwrap_or(4);
            let text = params.get("message").and_then(Value::as_str).unwrap_or("").to_string();
            let name = ed.lsp.clients[index].name.clone();
            match kind {
                1 => ed.error(format!("{name}: {text}")),
                2 => ed.warn(format!("{name}: {text}")),
                _ => {}
            }
        }
        "$/progress" => {
            let token = params.get("token").map(|token| token.to_string()).unwrap_or_default();
            let value = params.get("value").cloned().unwrap_or(Value::Null);
            let client = &mut ed.lsp.clients[index];
            match value.get("kind").and_then(Value::as_str) {
                Some("end") => {
                    client.progress.remove(&token);
                }
                Some(_) => {
                    let title = value.get("title").and_then(Value::as_str).map(str::to_string);
                    let message = value.get("message").and_then(Value::as_str).unwrap_or("");
                    let percent = value
                        .get("percentage")
                        .and_then(Value::as_u64)
                        .map(|percent| format!(" {percent}%"))
                        .unwrap_or_default();
                    let previous = client.progress.get(&token).cloned().unwrap_or_default();
                    let title = title.unwrap_or_else(|| previous.split(" · ").next().unwrap_or("").to_string());
                    let text = if message.is_empty() {
                        format!("{title}{percent}")
                    } else {
                        format!("{title} · {message}{percent}")
                    };
                    client.progress.insert(token, text.chars().take(40).collect());
                }
                None => {}
            }
            ed.needs_redraw = true;
        }
        _ => {}
    }
}

fn response(ed: &mut Editor, index: usize, pending: Pending, result: Value, request: i64) {
    let utf8 = ed.lsp.clients[index].utf8;
    match pending {
        Pending::Initialize => {
            let client = &mut ed.lsp.clients[index];
            client.capabilities = result.get("capabilities").cloned().unwrap_or(Value::Null);
            client.utf8 = client.capabilities.get("positionEncoding").and_then(Value::as_str) == Some("utf-8");
            client.initialized = true;
            let _ = client.write(&json!({ "jsonrpc": "2.0", "method": "initialized", "params": {} }));
            let queued = std::mem::take(&mut client.queue);
            for message in queued {
                let _ = client.write(&message);
            }
            // Documents edited while the server started.
            let docs: Vec<&Document> = ed.docs.values().collect();
            ed.lsp.sync(&docs);
            ed.needs_redraw = true;
        }
        Pending::Completion { doc } => {
            // Servers may answer out of order; only the latest request counts.
            let client_id = ed.lsp.clients[index].id;
            match ed.lsp.completion.as_mut() {
                Some((client, id, ..)) if *client == client_id && *id == request => {}
                _ => return,
            }
            if let Some(latest) = ed.lsp.completion.as_mut() {
                latest.5 = true;
            }
            ed.lsp.completion_incomplete = result.get("isIncomplete").and_then(Value::as_bool).unwrap_or(false);
            let Some(document) = ed.docs.get(&doc) else {
                return;
            };
            let items = completion_items(document, &result, utf8);
            crate::complete::on_lsp_items(ed, doc, items);
        }
        Pending::Hover => {
            let text = result.get("contents").map(markup_text).unwrap_or_default();
            if text.trim().is_empty() {
                ed.info("no documentation here");
            } else {
                ed.popup = Some(Popup::new(PopupKind::Hover, "", &text, true));
            }
        }
        Pending::Goto(method) => {
            let found = locations(ed, &result, utf8);
            match found.len() {
                0 => ed.info("nothing found"),
                1 => {
                    let (path, pos, _) = found.into_iter().next().expect("one location");
                    ed.push_jump();
                    match ed.open(&path) {
                        Ok(_) => {
                            ed.set_cursor(pos);
                            ed.align_cursor('z');
                        }
                        Err(error) => ed.error(error),
                    }
                }
                _ => {
                    let title = method.rsplit('/').next().unwrap_or("locations").to_string();
                    crate::picker::open_locations(ed, &title, found);
                }
            }
        }
        Pending::References => {
            let found = locations(ed, &result, utf8);
            if found.is_empty() {
                ed.info("no references");
            } else {
                let title = format!("{} references", found.len());
                crate::picker::open_locations(ed, &title, found);
            }
        }
        Pending::Rename => {
            if result.is_null() {
                ed.error("nothing to rename here");
                return;
            }
            match apply_workspace_edit(ed, index, &result) {
                Ok(files) => ed.info(format!("renamed in {files} file(s) — :wa saves them")),
                Err(error) => ed.error(error),
            }
        }
        Pending::Symbols(workspace) => {
            let doc = ed.doc();
            let path = doc.path.clone().unwrap_or_default();
            let mut items = Vec::new();
            flatten_symbols(&result, 0, &path, if workspace { None } else { Some(doc) }, utf8, &mut items);
            if items.is_empty() {
                ed.info("no symbols");
            } else {
                crate::picker::open_items(ed, if workspace { "Workspace symbols" } else { "Symbols" }, items);
            }
        }
        Pending::CodeActions => {
            let actions = result.as_array().cloned().unwrap_or_default();
            if actions.is_empty() {
                ed.info("no code actions here");
                return;
            }
            let client = ed.lsp.clients[index].id;
            let items: Vec<Item> = actions
                .into_iter()
                .map(|action| Item {
                    label: action.get("title").and_then(Value::as_str).unwrap_or("?").to_string(),
                    detail: action.get("kind").and_then(Value::as_str).unwrap_or("").to_string(),
                    data: Data::CodeAction(action, client),
                })
                .collect();
            crate::picker::open_items(ed, "Code actions", items);
        }
        Pending::ResolveAction => {
            let client = ed.lsp.clients[index].id;
            if result.get("edit").is_some() || result.get("command").is_some() {
                let mut action = result;
                if let Some(map) = action.as_object_mut() {
                    map.remove("data");
                }
                if let Err(error) = apply_code_action(ed, client, action) {
                    ed.error(error);
                }
            }
        }
        Pending::Other => {}
    }
}

pub fn exited(ed: &mut Editor, client_id: usize, reason: &str) {
    if let Some(client) = ed.lsp.clients.iter_mut().find(|client| client.id == client_id) {
        if !client.dead {
            client.dead = true;
            let name = client.name.clone();
            let _ = client.child.try_wait();
            ed.warn(format!("{name}: {reason} (:lsp restart)"));
        }
    }
}

pub fn restart(ed: &mut Editor) {
    ed.lsp.shutdown();
    ed.lsp.failed.clear();
    for doc in ed.docs.values_mut() {
        doc.diagnostics.clear();
    }
    let ids: Vec<usize> = ed.docs.keys().copied().collect();
    for id in ids {
        ed.lsp_open(id);
    }
    ed.info(format!("{} language server(s) restarted", ed.lsp.clients.len()));
}

pub fn info(ed: &Editor) -> String {
    let mut lines = Vec::new();
    for client in &ed.lsp.clients {
        let state = if client.dead {
            "stopped"
        } else if client.initialized {
            "running"
        } else {
            "starting"
        };
        lines.push(format!("{} ({})  {state}  {} file(s)", client.name, client.language, client.opened.len()));
        lines.push(format!("  root: {}", crate::document::display_path(&client.root)));
        lines.push(format!("  command: {}", client.command.join(" ")));
        let status = client.status();
        if !status.is_empty() {
            lines.push(format!("  {status}"));
        }
    }
    let doc = ed.doc();
    if let Some(lang) = doc.lang.and_then(|index| ed.languages.get(index)) {
        if !ed.lsp.clients.iter().any(|client| client.opened.contains_key(&doc.id)) {
            lines.push(format!("{}: no server attached.", lang.name));
            for command in &lang.lsp {
                let found = which(&command[0]).map_or("not installed".to_string(), |path| path.display().to_string());
                lines.push(format!("  {} → {found}", command.join(" ")));
            }
        }
    }
    if lines.is_empty() {
        lines.push("No language servers. ule starts one when you open a file whose server is installed (ule --health lists them).".into());
    }
    lines.join("\n")
}

pub fn show_line_diagnostics(ed: &mut Editor) {
    let line = ed.cursor().line;
    let text: Vec<String> = ed
        .doc()
        .diagnostics_on(line)
        .map(|diagnostic| {
            let level = match diagnostic.severity {
                1 => "error",
                2 => "warning",
                3 => "info",
                _ => "hint",
            };
            format!("{level} ({}): {}", diagnostic.source, diagnostic.message)
        })
        .collect();
    if text.is_empty() {
        ed.info("no diagnostics on this line");
    } else {
        ed.popup = Some(Popup::new(PopupKind::Info, "Diagnostics", &text.join("\n"), false));
    }
}

pub fn goto_diagnostic(ed: &mut Editor, forward: bool, errors_only: bool, count: usize) {
    let cursor = ed.cursor();
    let mut starts: Vec<Pos> = ed
        .doc()
        .diagnostics
        .iter()
        .filter(|diagnostic| !errors_only || diagnostic.severity == 1)
        .map(|diagnostic| diagnostic.start)
        .collect();
    starts.sort();
    starts.dedup();
    if starts.is_empty() {
        ed.info(if errors_only { "no errors" } else { "no diagnostics" });
        return;
    }
    let mut target = cursor;
    for _ in 0..count {
        target = if forward {
            starts.iter().copied().find(|pos| *pos > target).unwrap_or(starts[0])
        } else {
            starts.iter().copied().rev().find(|pos| *pos < target).unwrap_or(*starts.last().expect("non-empty"))
        };
    }
    ed.push_jump();
    ed.set_cursor(target);
    let message = ed
        .doc()
        .diagnostics
        .iter()
        .find(|diagnostic| diagnostic.start == target)
        .map(|diagnostic| diagnostic.message.lines().next().unwrap_or("").to_string());
    if let Some(message) = message {
        ed.info(message);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn uris_round_trip() {
        let path = Path::new("/Users/me/my project/файл#1.rs");
        let encoded = uri(path);
        assert!(encoded.starts_with("file:///Users/me/my%20project/"));
        assert_eq!(path_of(&encoded), Some(path.to_path_buf()));
    }

    #[test]
    fn utf16_columns() {
        let line = "a😀b";
        assert_eq!(to_lsp(line, 2, false), 3);
        assert_eq!(from_lsp(line, 3, false), 2);
        assert_eq!(to_lsp(line, 2, true), 5);
        assert_eq!(from_lsp(line, 5, true), 2);
    }

    #[test]
    fn frames() {
        let body = r#"{"jsonrpc":"2.0","id":1,"result":null}"#;
        let input = format!("Content-Length: {}\r\n\r\n{body}", body.len());
        let mut reader = BufReader::new(input.as_bytes());
        assert_eq!(read_message(&mut reader).unwrap()["id"], 1);
        assert!(read_message(&mut reader).is_none());
    }
}
