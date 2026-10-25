//! Headless scenario tests: keys in, text and cursor out.

use crate::config::Config;
use crate::editor::{Editor, Mode};
use crate::text::Pos;

fn editor(text: &str) -> Editor {
    crate::clipboard::disable();
    let mut config = Config::default();
    config.options.clipboard = false;
    config.options.lsp = false;
    let mut ed = Editor::new(config);
    ed.size = (100, 30);
    ed.doc_mut().set_content(text);
    crate::ui::layout(&mut ed);
    ed
}

fn keys(ed: &mut Editor, text: &str) {
    let leader = ed.keymap.leader.clone();
    for key in crate::keys::parse(text, &leader).expect("keys") {
        crate::vim::handle_key(ed, key);
    }
}

fn run(text: &str, input: &str) -> Editor {
    let mut ed = editor(text);
    keys(&mut ed, input);
    ed
}

fn content(ed: &Editor) -> String {
    ed.doc().text.to_string_lf()
}

#[test]
fn delete_change_yank_with_motions() {
    assert_eq!(content(&run("one two three", "dw")), "two three");
    assert_eq!(content(&run("one two three", "d2w")), "three");
    assert_eq!(content(&run("one two three", "2dw")), "three");
    assert_eq!(content(&run("one two three", "wcwTWO<esc>")), "one TWO three");
    assert_eq!(content(&run("one two three", "$d0")), "e");
    assert_eq!(content(&run("one two three", "dfo")), " three");
    assert_eq!(content(&run("one two three", "dto")), "o three");
    assert_eq!(content(&run("a\nb\nc\nd", "jdd")), "a\nc\nd");
    assert_eq!(content(&run("a\nb\nc\nd", "2dd")), "c\nd");
    assert_eq!(content(&run("a\nb\nc\nd", "d2d")), "c\nd");
    assert_eq!(content(&run("a\nb\nc\nd", "dj")), "c\nd");
    assert_eq!(content(&run("a\nb\nc\nd", "Gdk")), "a\nb");
    assert_eq!(content(&run("a\nb\nc\nd", "jdG")), "a");
    assert_eq!(content(&run("a\nb\nc\nd", "jjdgg")), "d");
    assert_eq!(content(&run("last word\nnext", "wdw")), "last \nnext", "dw at the line end keeps the newline");
    assert_eq!(content(&run("x = 1", "D")), "");
    assert_eq!(content(&run("hello world", "wC!<esc>")), "hello !");
    let ed = run("hello world", "yiwwP");
    assert_eq!(content(&ed), "hello helloworld");
}

#[test]
fn text_objects() {
    assert_eq!(content(&run("call(x, y)", "fxdi(")), "call()");
    assert_eq!(content(&run("call(x, y)", "fxda(")), "call");
    assert_eq!(content(&run("call(x, y)", "di(")), "call(x, y)", "outside the brackets nothing happens");
    assert_eq!(content(&run("x = \"hello there\"", "fhci\"bye<esc>")), "x = \"bye\"");
    assert_eq!(content(&run("one two three", "wdaw")), "one three");
    assert_eq!(content(&run("one two three", "wdiw")), "one  three");
    assert_eq!(content(&run("f(a, bb, c)", "fbdia")), "f(a, , c)");
    assert_eq!(content(&run("f(a, bb, c)", "fbdaa")), "f(a, c)");
    assert_eq!(content(&run("fn a() {\n    x;\n    y;\n}", "jci{z<esc>")), "fn a() {\n    z\n}", "the inner block keeps its indent");
    assert_eq!(content(&run("p1\np1\n\np2", "dap")), "p2");
}

#[test]
fn insert_variants_and_counts() {
    assert_eq!(content(&run("abc", "ix<esc>")), "xabc");
    assert_eq!(content(&run("abc", "ax<esc>")), "axbc");
    assert_eq!(content(&run("  abc", "Ix<esc>")), "  xabc");
    assert_eq!(content(&run("abc", "Ax<esc>")), "abcx");
    assert_eq!(content(&run("abc", "3ihi <esc>")), "hi hi hi abc");
    assert_eq!(content(&run("a", "ob<esc>")), "a\nb");
    assert_eq!(content(&run("a", "Ob<esc>")), "b\na");
    assert_eq!(content(&run("a", "2ox<esc>")), "a\nx\nx");
    let ed = run("abc", "ix<esc>");
    assert_eq!(ed.mode, Mode::Normal);
    assert_eq!(ed.cursor(), Pos::new(0, 0));
}

#[test]
fn dot_repeat() {
    assert_eq!(content(&run("a b c d", "dw..")), "d");
    assert_eq!(content(&run("x\nx\nx", "A;<esc>j.j.")), "x;\nx;\nx;");
    assert_eq!(content(&run("one two three four", "cwX<esc>w.")), "X X three four");
    assert_eq!(content(&run("a\nb\nc\nd\ne", "dd2.")), "d\ne");
    assert_eq!(content(&run("abc", "x.")), "c");
}

#[test]
fn undo_redo() {
    let mut ed = run("hello", "xxx");
    assert_eq!(content(&ed), "lo");
    keys(&mut ed, "u");
    assert_eq!(content(&ed), "llo");
    keys(&mut ed, "2u");
    assert_eq!(content(&ed), "hello");
    keys(&mut ed, "<C-r>");
    assert_eq!(content(&ed), "ello");
    let mut ed = run("a", "ohello world<esc>");
    keys(&mut ed, "u");
    assert_eq!(content(&ed), "a", "one insert session is one undo step");
}

#[test]
fn visual_modes() {
    assert_eq!(content(&run("one two three", "wvwd")), "one hree");
    assert_eq!(content(&run("a\nb\nc", "Vjd")), "c");
    assert_eq!(content(&run("a\nb\nc", "Vj>")), "    a\n    b\nc");
    assert_eq!(content(&run("abc\nabc\nabc", "l<C-v>jjd")), "ac\nac\nac");
    assert_eq!(content(&run("abc\nabc\nabc", "<C-v>jjI- <esc>")), "- abc\n- abc\n- abc");
    assert_eq!(content(&run("abc\nabc", "<C-v>j$A;<esc>")), "abc;\nabc;");
    assert_eq!(content(&run("hello", "vU")), "Hello");
    assert_eq!(content(&run("hello world", "viwy$p")), "hello worldhello");
    assert_eq!(content(&run("x y", "yiwwviwp")), "x x");
    let ed = run("one two", "vw");
    assert_eq!(ed.mode, Mode::Visual(crate::editor::VisualKind::Char));
}

#[test]
fn registers_and_macros() {
    assert_eq!(content(&run("a\nb", "\"ayyj\"ap")), "a\nb\na");
    assert_eq!(content(&run("1\n2\n3", "qaA!<esc>jq2@a")), "1!\n2!\n3!");
    assert_eq!(content(&run("1\n2\n3", "qaA!<esc>jqQQ")), "1!\n2!\n3!");
    assert_eq!(content(&run("a b", "\"_dwP")), "b", "the blackhole register keeps the unnamed one");
}

#[test]
fn search_and_marks() {
    let ed = run("foo bar\nbaz foo\nfoo", "/foo<cr>");
    assert_eq!(ed.cursor(), Pos::new(1, 4));
    let ed = run("foo bar\nbaz foo\nfoo", "/foo<cr>n");
    assert_eq!(ed.cursor(), Pos::new(2, 0));
    let ed = run("foo bar\nbaz foo\nfoo", "*");
    assert_eq!(ed.cursor(), Pos::new(1, 4));
    let ed = run("foo bar\nbaz foo\nfoo", "G?bar<cr>");
    assert_eq!(ed.cursor(), Pos::new(0, 4));
    let ed = run("a\nb\nc", "jmaG'a");
    assert_eq!(ed.cursor().line, 1);
    let ed = run("abc def", "fd;");
    assert_eq!(ed.cursor(), Pos::new(0, 4));
}

#[test]
fn ex_commands() {
    assert_eq!(content(&run("a a\nb a", ":%s/a/x/g<cr>")), "x x\nb x");
    assert_eq!(content(&run("a a\nb a", ":s/a/x/<cr>")), "x a\nb a");
    assert_eq!(content(&run("one\ntwo", ":%s/\\(o\\)/[\\1]/g<cr>")), "one\ntwo");
    assert_eq!(content(&run("one\ntwo", ":%s/(o)/[$1]/g<cr>")), "[o]ne\ntw[o]", "regex crate groups");
    assert_eq!(content(&run("one\ntwo", ":%s/o/<lt>&>/g<cr>")), "<o>ne\ntw<o>");
    assert_eq!(content(&run("c\na\nb\na", ":sort u<cr>")), "a\nb\nc");
    assert_eq!(content(&run("10\n9\n100", ":sort n<cr>")), "9\n10\n100");
    assert_eq!(content(&run("keep\ndrop me\nkeep", ":g/drop/d<cr>")), "keep\nkeep");
    assert_eq!(content(&run("keep\ndrop me\nkeep", ":v/drop/d<cr>")), "drop me");
    assert_eq!(content(&run("a\nb\nc", ":2d<cr>")), "a\nc");
    assert_eq!(content(&run("a\nb\nc", ":%normal A;<cr>")), "a;\nb;\nc;");
    assert_eq!(content(&run("a\nb\nc\nd", "Vj:normal I-<cr>")), "-a\n-b\nc\nd");
    let ed = run("a\nb\nc", ":3<cr>");
    assert_eq!(ed.cursor().line, 2);
    let mut ed = run("x", ":set ts=2 nowrap<cr>");
    assert_eq!(ed.options.tab_width, 2);
    assert_eq!(ed.options.wrap, Some(false));
    keys(&mut ed, ":set wrap!<cr>");
    assert_eq!(ed.options.wrap, Some(true));
    let ed = run("x", ":nonsense<cr>");
    assert!(ed.message.as_ref().is_some_and(|message| message.text.contains("not a command")));
}

#[test]
fn indentation_and_pairs_while_typing() {
    let mut ed = editor("");
    let rust = ed.languages.by_name("rust");
    ed.doc_mut().set_language(rust);
    keys(&mut ed, "ifn main() {<cr>let x = (1<esc>");
    assert_eq!(content(&ed), "fn main() {\n    let x = (1)\n}");
    let mut ed = editor("");
    let python = ed.languages.by_name("python");
    ed.doc_mut().set_language(python);
    keys(&mut ed, "idef f():<cr>return 1<esc>");
    assert_eq!(content(&ed), "def f():\n    return 1");
    let mut ed = editor("    x");
    keys(&mut ed, "A<cr><bs>y<esc>");
    assert_eq!(content(&ed), "    x\ny");
}

#[test]
fn comments_join_case_increment() {
    let mut ed = editor("a\nb\nc");
    let python = ed.languages.by_name("python");
    ed.doc_mut().set_language(python);
    keys(&mut ed, "gcj");
    assert_eq!(content(&ed), "# a\n# b\nc");
    keys(&mut ed, "gcc");
    assert_eq!(content(&ed), "a\n# b\nc");
    assert_eq!(content(&run("a\n  b\nc", "3J")), "a b c");
    assert_eq!(content(&run("hello", "g~iw")), "HELLO");
    assert_eq!(content(&run("hello", "gUU")), "HELLO");
    assert_eq!(content(&run("v1.9", "<C-a>")), "v2.9");
    assert_eq!(content(&run("x 7", "5<C-x>")), "x 2");
    assert_eq!(content(&run("ab", "~~")), "AB");
}

#[test]
fn windows_buffers_and_jumps() {
    let mut ed = editor("a\nb\nc\nd\ne\nf");
    keys(&mut ed, "<C-w>v");
    assert_eq!(ed.layout.views().len(), 2);
    keys(&mut ed, "<C-w>q");
    assert_eq!(ed.layout.views().len(), 1);
    keys(&mut ed, "G<C-o>");
    assert_eq!(ed.cursor().line, 0);
    keys(&mut ed, "<C-i>");
    assert_eq!(ed.cursor().line, 5);
}

#[test]
fn quitting_protects_unsaved_work() {
    let dir = std::env::temp_dir().join(format!("ule-quit-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join("f.txt");
    std::fs::write(&path, "one\n").unwrap();
    let mut ed = editor("");
    ed.open(&path).unwrap();
    keys(&mut ed, "x:q<cr>");
    assert!(!ed.quit, "unsaved changes block :q");
    keys(&mut ed, ":wq<cr>");
    assert!(ed.quit);
    assert_eq!(std::fs::read_to_string(&path).unwrap(), "ne\n");
}

#[test]
fn leader_menu_waits_then_runs() {
    let mut ed = editor("text");
    keys(&mut ed, "<space>");
    assert_eq!(ed.vim.pending.len(), 1, "the leader waits for more keys");
    keys(&mut ed, "tw");
    assert!(ed.vim.pending.is_empty());
    assert_eq!(ed.options.wrap, Some(true));
}

#[test]
fn user_bindings_apply() {
    crate::clipboard::disable();
    let mut config = Config::parse(
        "[keys.insert]\n\"jk\" = \"normal_mode\"\n[keys.normal]\n\"H\" = \"^\"\n\"<leader>x\" = \":%s/a/b/g\"\n",
        &crate::commands::names(),
    );
    config.options.clipboard = false;
    config.options.lsp = false;
    let mut ed = Editor::new(config);
    ed.doc_mut().set_content("  a a");
    keys(&mut ed, "$H");
    assert_eq!(ed.cursor(), Pos::new(0, 2));
    keys(&mut ed, "ixjk");
    assert_eq!(ed.mode, Mode::Normal);
    assert_eq!(content(&ed), "  xa a");
    keys(&mut ed, "<space>x");
    assert_eq!(content(&ed), "  xb b");
}

#[test]
fn rendering_smoke() {
    let mut ed = editor("fn main() {\n\tprintln!(\"日本\");\n}\n");
    let rust = ed.languages.by_name("rust");
    ed.doc_mut().set_language(rust);
    keys(&mut ed, "jVj");
    let surface = crate::ui::draw(&mut ed);
    let row: String = (0..surface.width)
        .filter_map(|x| surface.get(x, 1))
        .filter(|cell| !cell.continuation)
        .map(|cell| cell.symbol)
        .collect();
    assert!(row.contains("println!(\"日本\");"), "{row:?}");
    assert!(surface.cursor.is_some());
    // Pickers, popups and the start screen draw without panicking at odd sizes.
    for (width, height) in [(10, 4), (40, 10), (200, 60)] {
        let mut ed = editor("");
        ed.size = (width, height);
        crate::ui::draw(&mut ed);
        keys(&mut ed, ":help<cr>");
        crate::ui::draw(&mut ed);
        crate::picker::open_commands(&mut ed);
        crate::ui::draw(&mut ed);
    }
}

#[test]
fn version_matches_unlaw() {
    let root: toml_edit::DocumentMut = include_str!("../../Cargo.toml").parse().expect("root Cargo.toml");
    let unlaw = root["package"]["version"].as_str().expect("version");
    assert_eq!(env!("CARGO_PKG_VERSION"), unlaw, "ule/Cargo.toml and Cargo.toml must carry the same version");
}

/// Random key sequences must never panic (a panic would lose unsaved work).
#[test]
fn random_keys_never_panic() {
    let texts = [
        "",
        "a",
        "fn main() {\n    let x = (1, [2, 3]);\n}\n",
        "日本語 テキスト\n\temoji 😀 here\n  \n\"quoted 'mixed'\" ` back",
        "x\n\n\ny = 1 # comment\n\tz",
        "<div class=\"a\"><b>bold</b></div>",
    ];
    let pieces = [
        "h", "j", "k", "l", "w", "b", "e", "W", "B", "E", "0", "^", "$", "gg", "G", "%", "{", "}", "(", ")", "f", "t", "F", "T",
        ";", ",", "x", "X", "dd", "dw", "cw", "ciw", "di(", "da\"", "dap", "yy", "p", "P", "u", "<C-r>", ".", "~", "J", "gJ",
        "v", "V", "<C-v>", "o", "O", "i", "a", "A", "I", "<esc>", "<cr>", "<bs>", "<tab>", "<s-tab>", "<del>", ">>", "<<",
        "gcc", "guu", "gUiw", "<C-a>", "<C-x>", "qa", "q", "@a", "@@", "ma", "'a", "`a", "*", "#", "n", "N", "/a<cr>",
        "?x<cr>", ":s/a/b/g<cr>", ":%sort<cr>", ":g/x/d<cr>", "r", "R", "s", "S", "C", "D", "Y", "3", "2", "\"a", "\"_",
        "<C-d>", "<C-u>", "<C-e>", "<C-y>", "zz", "H", "M", "L", "gv", "gi", "<C-o>", "<C-i>", "<A-j>", "<A-k>", "Q",
        "日", "😀", " ", "(", "\"", "'", "}", "<C-w>", "<C-u>", "<C-n>", "<left>", "<right>", "<up>", "<down>", "<home>",
        "<end>", ":normal A!<cr>", "<C-w>v", "<C-w>q", "]d", "[b", "<C-^>",
    ];
    let mut seed: u64 = 0x5eed_1234_abcd_ef01;
    let mut next = || {
        seed ^= seed << 13;
        seed ^= seed >> 7;
        seed ^= seed << 17;
        seed
    };
    for round in 0..1500 {
        let text = texts[round % texts.len()];
        let mut ed = editor(text);
        let mut sequence = String::new();
        for _ in 0..40 {
            sequence.push_str(pieces[(next() % pieces.len() as u64) as usize]);
        }
        let leader = ed.keymap.leader.clone();
        let keys = crate::keys::parse(&sequence, &leader).unwrap();
        for key in keys {
            crate::vim::handle_key(&mut ed, key);
            // The cursor must always be inside the text.
            let cursor = ed.cursor();
            let doc = ed.doc();
            assert!(cursor.line < doc.text.len_lines(), "round {round}: {sequence}");
            assert!(cursor.col <= doc.text.line_len(cursor.line), "round {round}: {sequence}");
        }
        ed.prompt = None;
        crate::ui::draw(&mut ed);
    }
}
