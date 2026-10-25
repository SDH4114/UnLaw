use std::io::{IsTerminal, Read};
use std::path::PathBuf;
use std::process::ExitCode;

use ule::app::{run, Launch};

const HELP: &str = "\
ule: Unlaw's modal code editor (vim keys, LSP, fuzzy pickers, ul built in)

Usage: ule [options] [file[:line[:col]] | +line file | directory]...
       command | ule -

Options:
  -R               open read-only
  -                read the text to edit from stdin
  +N file          open file at line N
  --clean          ignore ule.toml (defaults only)
  --health [lang]  which language servers, formatters and tools are installed
  --config         print the path of ule.toml
  -h, --help       this help
  -V, --version    version

Inside ule:
  i / Esc          type / stop typing        :w  :q  :wq   save, quit
  <space>          menu of everything else   <space>?      all key bindings
  <space><space>   find a file               <space>/      search the project
  gd K gr          definition, docs, refs    <space>r      run the file
  :help            help topics               <space>fc     settings (ule.toml)

Settings: ~/.config/unlaw/ule.toml (ULE_CONFIG overrides; XDG_CONFIG_HOME respected).
Also opened by `ul edit <file>` and `ul config edit`.
";

fn health(only: Option<&str>) {
    let config = ule::config::Config::load(&ule::commands::names());
    let (languages, errors) = ule::syntax::Languages::load(config.languages.as_ref());
    let path = ule::config::config_path();
    println!("ule {}", env!("CARGO_PKG_VERSION"));
    println!("config     {} {}", path.display(), if path.exists() { "" } else { "(not created; defaults)" });
    for error in config.errors.iter().chain(errors.iter()) {
        println!("  ✗ {error}");
    }
    let found = |program: &str| ule::lsp::which(program).map(|path| path.display().to_string());
    let tool = |name: &str, program: &str, purpose: &str| match found(program) {
        Some(path) => println!("{name:<10} ✓ {path}"),
        None => println!("{name:<10} ✗ not found ({purpose})"),
    };
    match ule::ul::ul_path() {
        Some(path) => println!("{:<10} ✓ {}", "ul", path.display()),
        None => println!("{:<10} ✗ not found (ul commands, ul lm, ul git)", "ul"),
    }
    tool("rg", "rg", "fast project search; ule falls back to its own");
    tool("git", "git", "changed files, diff, blame");
    tool("pbcopy", "pbcopy", "system clipboard");
    println!();
    println!("{:<12} {:<34} {:<26} run", "language", "language server", "formatter");
    for lang in &languages.list {
        if only.is_some_and(|name| name != lang.name) {
            continue;
        }
        let lsp = if lang.lsp.is_empty() {
            "-".to_string()
        } else {
            match lang.lsp.iter().find(|command| found(&command[0]).is_some()) {
                Some(command) => format!("✓ {}", command[0]),
                None => {
                    format!("✗ {}", lang.lsp.iter().map(|command| command[0].clone()).collect::<Vec<_>>().join(" / "))
                }
            }
        };
        let formatter = match lang.formatter.first() {
            None => "-".to_string(),
            Some(program) if found(program).is_some() => format!("✓ {program}"),
            Some(program) => format!("✗ {program}"),
        };
        println!("{:<12} {:<34} {:<26} {}", lang.name, lsp, formatter, lang.run.clone().unwrap_or_else(|| "-".into()));
    }
}

fn main() -> ExitCode {
    let mut args = std::env::args().skip(1).peekable();
    let mut launch = Launch { files: Vec::new(), stdin: None, readonly: false, clean: false };
    let mut next_line: Option<usize> = None;
    let mut only_files = false;
    while let Some(arg) = args.next() {
        if !only_files {
            match arg.as_str() {
                "-h" | "--help" => {
                    print!("{HELP}");
                    return ExitCode::SUCCESS;
                }
                "-V" | "--version" => {
                    println!("ule {}", env!("CARGO_PKG_VERSION"));
                    return ExitCode::SUCCESS;
                }
                "--health" => {
                    health(args.next().as_deref());
                    return ExitCode::SUCCESS;
                }
                "--config" => {
                    println!("{}", ule::config::config_path().display());
                    return ExitCode::SUCCESS;
                }
                "-R" => {
                    launch.readonly = true;
                    continue;
                }
                "--clean" => {
                    launch.clean = true;
                    continue;
                }
                "--" => {
                    only_files = true;
                    continue;
                }
                "-" => {
                    let mut text = String::new();
                    if std::io::stdin().read_to_string(&mut text).is_err() {
                        eprintln!("ule: could not read stdin");
                        return ExitCode::from(1);
                    }
                    launch.stdin = Some(text);
                    continue;
                }
                _ => {}
            }
            if let Some(number) = arg.strip_prefix('+') {
                match number.parse::<usize>() {
                    Ok(line) => next_line = Some(line),
                    Err(_) if number.is_empty() => next_line = Some(usize::MAX),
                    Err(_) => {
                        eprintln!("ule: +{number}: expected a line number");
                        return ExitCode::from(2);
                    }
                }
                continue;
            }
            if arg.starts_with('-') && arg.len() > 1 {
                eprintln!("ule: unknown option {arg} (ule --help)");
                return ExitCode::from(2);
            }
        }
        let path = PathBuf::from(&arg);
        // `file:12:3` opens at a position unless a file with that exact name exists.
        let (file, line, col) = if path.exists() {
            (path, None, None)
        } else {
            let (name, line, col) = ule::jobs::split_location(&arg);
            if line.is_some() {
                (PathBuf::from(name), line, col)
            } else {
                (path, None, None)
            }
        };
        let line = next_line.take().or(line);
        launch.files.push((file, line, col));
    }
    if !std::io::stdout().is_terminal() {
        eprintln!("ule: stdout is not a terminal");
        return ExitCode::from(1);
    }
    match run(launch) {
        Ok(code) => ExitCode::from(code as u8),
        Err(error) => {
            eprintln!("ule: {error}");
            ExitCode::from(1)
        }
    }
}
