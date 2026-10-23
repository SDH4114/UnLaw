//! Just enough HTTP/1.1 for a loopback API: one request per connection,
//! `Content-Length` or chunked bodies, and streamed responses that end when
//! the connection closes (SSE and NDJSON). No TLS: it never leaves 127.0.0.1.

use std::io::{self, BufRead, BufReader, Read, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

/// Large enough for several base64 images or an audio file.
pub const MAX_BODY: usize = 64 * 1024 * 1024;
const MAX_HEAD: usize = 64 * 1024;

#[derive(Debug)]
pub struct Request {
    pub method: String,
    /// Path without the query string.
    pub path: String,
    pub headers: Vec<(String, String)>,
    pub body: Vec<u8>,
}

impl Request {
    pub fn header(&self, name: &str) -> Option<&str> {
        self.headers.iter().find(|(key, _)| key.eq_ignore_ascii_case(name)).map(|(_, value)| value.as_str())
    }
}

#[derive(Debug)]
pub enum ReadError {
    Io(io::Error),
    /// Status code and message for a malformed or oversized request.
    Bad(u16, String),
}

impl From<io::Error> for ReadError {
    fn from(error: io::Error) -> Self {
        ReadError::Io(error)
    }
}

fn read_line(reader: &mut impl BufRead, budget: &mut usize) -> Result<String, ReadError> {
    let mut line = Vec::new();
    let read = reader.by_ref().take(*budget as u64 + 1).read_until(b'\n', &mut line)?;
    if read > *budget {
        return Err(ReadError::Bad(431, "request headers are too large".into()));
    }
    *budget -= read;
    if line.last() != Some(&b'\n') {
        return Err(ReadError::Io(io::Error::new(io::ErrorKind::UnexpectedEof, "connection closed")));
    }
    Ok(String::from_utf8_lossy(&line).trim_end_matches(['\r', '\n']).to_string())
}

fn read_chunked(reader: &mut impl BufRead) -> Result<Vec<u8>, ReadError> {
    let mut body = Vec::new();
    let mut budget = MAX_HEAD;
    loop {
        let line = read_line(reader, &mut budget)?;
        let size = usize::from_str_radix(line.split(';').next().unwrap_or("").trim(), 16)
            .map_err(|_| ReadError::Bad(400, "invalid chunk size".into()))?;
        if size == 0 {
            // Trailers end with an empty line.
            while !read_line(reader, &mut budget)?.is_empty() {}
            return Ok(body);
        }
        if body.len() + size > MAX_BODY {
            return Err(ReadError::Bad(413, "request body is larger than 64 MB".into()));
        }
        let start = body.len();
        body.resize(start + size, 0);
        reader.read_exact(&mut body[start..])?;
        read_line(reader, &mut budget)?;
    }
}

pub fn read_request(stream: &mut impl Read) -> Result<Request, ReadError> {
    let mut reader = BufReader::new(stream);
    let mut budget = MAX_HEAD;
    let first = read_line(&mut reader, &mut budget)?;
    let mut parts = first.split_whitespace();
    let (Some(method), Some(target)) = (parts.next(), parts.next()) else {
        return Err(ReadError::Bad(400, "malformed request line".into()));
    };
    let path = target.split(['?', '#']).next().unwrap_or("/").to_string();
    let mut headers = Vec::new();
    loop {
        let line = read_line(&mut reader, &mut budget)?;
        if line.is_empty() {
            break;
        }
        if let Some((key, value)) = line.split_once(':') {
            headers.push((key.trim().to_string(), value.trim().to_string()));
        }
    }
    let mut request = Request { method: method.to_ascii_uppercase(), path, headers, body: Vec::new() };
    if request.header("transfer-encoding").is_some_and(|value| value.to_ascii_lowercase().contains("chunked")) {
        request.body = read_chunked(&mut reader)?;
    } else if let Some(length) = request.header("content-length") {
        let length: usize = length.parse().map_err(|_| ReadError::Bad(400, "invalid Content-Length".into()))?;
        if length > MAX_BODY {
            return Err(ReadError::Bad(413, "request body is larger than 64 MB".into()));
        }
        request.body = vec![0; length];
        reader.read_exact(&mut request.body)?;
    }
    Ok(request)
}

pub fn reason(status: u16) -> &'static str {
    match status {
        200 => "OK",
        202 => "Accepted",
        204 => "No Content",
        400 => "Bad Request",
        403 => "Forbidden",
        404 => "Not Found",
        405 => "Method Not Allowed",
        409 => "Conflict",
        413 => "Payload Too Large",
        431 => "Request Header Fields Too Large",
        500 => "Internal Server Error",
        503 => "Service Unavailable",
        507 => "Insufficient Storage",
        _ => "Unknown",
    }
}

/// Off by default: with CORS any web page could drive the local models.
/// `ul lm serve --cors` turns it on for local web apps.
static CORS: AtomicBool = AtomicBool::new(false);

pub fn enable_cors() {
    CORS.store(true, Ordering::SeqCst);
}

fn common_headers() -> &'static str {
    if CORS.load(Ordering::SeqCst) {
        "Access-Control-Allow-Origin: *\r\nAccess-Control-Allow-Methods: GET, POST, DELETE, OPTIONS\r\nAccess-Control-Allow-Headers: *\r\nX-Unlaw: lm\r\nConnection: close\r\n"
    } else {
        "X-Unlaw: lm\r\nConnection: close\r\n"
    }
}

/// The Host header names this machine. A page on another domain that
/// resolves to 127.0.0.1 (DNS rebinding) sends its own name and is refused.
pub fn local_host(request: &Request) -> bool {
    let Some(host) = request.header("host") else { return true };
    let name = if let Some(rest) = host.strip_prefix('[') {
        rest.split(']').next().unwrap_or("")
    } else {
        host.rsplit_once(':').map(|(name, _)| name).unwrap_or(host)
    };
    matches!(name.to_ascii_lowercase().as_str(), "127.0.0.1" | "localhost" | "::1")
}

pub fn respond(stream: &mut impl Write, status: u16, content_type: &str, body: &[u8]) -> io::Result<()> {
    write!(
        stream,
        "HTTP/1.1 {status} {}\r\nContent-Type: {content_type}\r\nContent-Length: {}\r\n{}\r\n",
        reason(status),
        body.len(),
        common_headers()
    )?;
    stream.write_all(body)?;
    stream.flush()
}

pub fn respond_json(stream: &mut impl Write, status: u16, value: &serde_json::Value) -> io::Result<()> {
    respond(stream, status, "application/json", value.to_string().as_bytes())
}

/// Start a response whose body is streamed until the connection closes.
pub fn start_stream(stream: &mut impl Write, content_type: &str) -> io::Result<()> {
    write!(stream, "HTTP/1.1 200 OK\r\nContent-Type: {content_type}\r\nCache-Control: no-cache\r\n{}\r\n", common_headers())?;
    stream.flush()
}

/// A finished client-side response.
pub struct Response {
    pub status: u16,
    pub headers: Vec<(String, String)>,
    pub body: Vec<u8>,
}

impl Response {
    pub fn header(&self, name: &str) -> Option<&str> {
        self.headers.iter().find(|(key, _)| key.eq_ignore_ascii_case(name)).map(|(_, value)| value.as_str())
    }
}

/// Status, headers and the stream positioned at the body.
pub type Head = (u16, Vec<(String, String)>, BufReader<TcpStream>);

/// Send a request to a loopback server and return the open stream positioned
/// after the response head, with status and headers.
pub fn send(port: u16, method: &str, path: &str, body: Option<&[u8]>, timeout: Duration) -> io::Result<Head> {
    let address = ("127.0.0.1", port)
        .to_socket_addrs()?
        .next()
        .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "no loopback address"))?;
    let mut stream = TcpStream::connect_timeout(&address, timeout)?;
    stream.set_read_timeout(Some(timeout))?;
    let body = body.unwrap_or_default();
    write!(
        stream,
        "{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        body.len()
    )?;
    stream.write_all(body)?;
    stream.flush()?;
    let mut reader = BufReader::new(stream);
    let mut budget = MAX_HEAD;
    let invalid = |error: ReadError| match error {
        ReadError::Io(error) => error,
        ReadError::Bad(_, message) => io::Error::new(io::ErrorKind::InvalidData, message),
    };
    let status_line = read_line(&mut reader, &mut budget).map_err(invalid)?;
    let status = status_line
        .split_whitespace()
        .nth(1)
        .and_then(|code| code.parse().ok())
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "not an HTTP response"))?;
    let mut headers = Vec::new();
    loop {
        let line = read_line(&mut reader, &mut budget).map_err(invalid)?;
        if line.is_empty() {
            break;
        }
        if let Some((key, value)) = line.split_once(':') {
            headers.push((key.trim().to_string(), value.trim().to_string()));
        }
    }
    Ok((status, headers, reader))
}

pub fn fetch(port: u16, method: &str, path: &str, body: Option<&[u8]>, timeout: Duration) -> io::Result<Response> {
    let (status, headers, mut reader) = send(port, method, path, body, timeout)?;
    let mut body = Vec::new();
    reader.read_to_end(&mut body)?;
    Ok(Response { status, headers, body })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    #[test]
    fn requests_parse_with_length_chunks_and_queries() {
        let raw = b"POST /v1/chat/completions?x=1 HTTP/1.1\r\nHost: a\r\nContent-Length: 4\r\n\r\nbodyEXTRA";
        let request = read_request(&mut Cursor::new(&raw[..])).unwrap();
        assert_eq!((request.method.as_str(), request.path.as_str()), ("POST", "/v1/chat/completions"));
        assert_eq!(request.header("content-length"), Some("4"));
        assert_eq!(request.body, b"body");

        let raw = b"post /api/chat HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n2;ext\r\nde\r\n0\r\n\r\n";
        let request = read_request(&mut Cursor::new(&raw[..])).unwrap();
        assert_eq!((request.method.as_str(), request.body.as_slice()), ("POST", &b"abcde"[..]));
    }

    #[test]
    fn bad_requests_are_rejected_with_a_status() {
        let status = |raw: &[u8]| match read_request(&mut Cursor::new(raw)) {
            Err(ReadError::Bad(status, _)) => status,
            Err(ReadError::Io(_)) => 0,
            Ok(_) => 200,
        };
        assert_eq!(status(b"GARBAGE\r\n\r\n"), 400);
        assert_eq!(status(b"POST / HTTP/1.1\r\nContent-Length: x\r\n\r\n"), 400);
        assert_eq!(status(format!("POST / HTTP/1.1\r\nContent-Length: {}\r\n\r\n", MAX_BODY + 1).as_bytes()), 413);
        assert_eq!(status(format!("GET / HTTP/1.1\r\nX: {}\r\n\r\n", "a".repeat(MAX_HEAD)).as_bytes()), 431);
        assert_eq!(status(b"POST / HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\nzz\r\n"), 400);
        // A client that hangs up mid-body is an I/O error, never a panic.
        assert_eq!(status(b"POST / HTTP/1.1\r\nContent-Length: 10\r\n\r\nabc"), 0);
        assert_eq!(status(b"GET / HTTP/1.1\r\n"), 0);
    }

    #[test]
    fn responses_carry_length_and_marker_but_no_cors() {
        let mut out = Vec::new();
        respond_json(&mut out, 404, &serde_json::json!({"error": "x"})).unwrap();
        let text = String::from_utf8(out).unwrap();
        assert!(text.starts_with("HTTP/1.1 404 Not Found\r\n"));
        assert!(text.contains("Content-Length: 13\r\n"));
        assert!(!text.contains("Access-Control-Allow-Origin"));
        assert!(text.contains("X-Unlaw: lm\r\n"));
        assert!(text.ends_with("\r\n\r\n{\"error\":\"x\"}"));
    }

    #[test]
    fn only_local_host_names_pass() {
        let with = |host: Option<&str>| {
            let headers = host.map(|h| vec![("Host".to_string(), h.to_string())]).unwrap_or_default();
            local_host(&Request { method: "GET".into(), path: "/".into(), headers, body: Vec::new() })
        };
        for host in ["127.0.0.1:1234", "localhost", "LOCALHOST:80", "[::1]:1234"] {
            assert!(with(Some(host)), "{host}");
        }
        for host in ["evil.example:1234", "127.0.0.1.evil.example", "[::2]:1"] {
            assert!(!with(Some(host)), "{host}");
        }
        assert!(with(None));
    }

    #[test]
    fn client_round_trip() {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let server = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let request = read_request(&mut stream).unwrap();
            respond(&mut stream, 200, "text/plain", &request.body).unwrap();
        });
        let response = fetch(port, "POST", "/echo", Some(b"hello"), Duration::from_secs(5)).unwrap();
        server.join().unwrap();
        assert_eq!((response.status, response.body.as_slice()), (200, &b"hello"[..]));
        assert_eq!(response.header("x-unlaw"), Some("lm"));
    }
}
