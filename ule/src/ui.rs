//! Draws the editor into a Surface: views, gutters, status lines, bufferline,
//! explorer, command line, and overlays (picker, completion, popups, which-key).

use std::path::Path;

use crate::config::LineNumbers;
use crate::display::{col_to_display, fit, fit_start, str_width, width_at, wrap_rows};
use crate::document::{DocKind, Document};
use crate::editor::{Editor, Focus, Level, Mode, Rect, VisualKind};
use crate::keymap::KeyMode;
use crate::render::Surface;
use crate::syntax::Span;
use crate::text::Pos;
use crate::theme::{Color, Style, Theme};

const SPINNER: [char; 10] = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];

fn spinner(ed: &Editor) -> char {
    SPINNER[(ed.started.elapsed().as_millis() / 100) as usize % SPINNER.len()]
}

fn line_number_width(doc: &Document, numbers: LineNumbers) -> u16 {
    if numbers == LineNumbers::Off {
        return 2;
    }
    let digits = doc.text.len_lines().to_string().len().max(3) as u16;
    digits + 2
}

/// Sets every view's text area and keeps cursors visible; call before drawing.
pub fn layout(ed: &mut Editor) {
    let (areas, _) = ed.view_areas();
    for (id, rect) in areas {
        let Some(view) = ed.views.get(&id) else {
            continue;
        };
        let doc = &ed.docs[&view.doc];
        let gutter = line_number_width(doc, ed.options.line_numbers);
        let area =
            Rect { x: rect.x + gutter, y: rect.y, w: rect.w.saturating_sub(gutter), h: rect.h.saturating_sub(1) };
        ed.views.get_mut(&id).expect("view").area = area;
    }
    let focus = ed.focus;
    ed.scroll_to_cursor(focus);
}

pub fn draw(ed: &mut Editor) -> Surface {
    layout(ed);
    let theme = ed.theme.clone();
    let base = theme.text();
    let (width, height) = ed.size;
    let mut surface = Surface::new(width, height, base);
    if width < 10 || height < 4 {
        surface.text(0, 0, "ule: window too small", base, width);
        return surface;
    }
    if ed.bufferline_visible() {
        bufferline(ed, &mut surface, &theme);
    }
    let (areas, explorer) = ed.view_areas();
    for (id, rect) in &areas {
        draw_view(ed, &mut surface, &theme, *id, *rect);
        // A separator to the right of views that have a neighbour there.
        let right = rect.x + rect.w;
        if areas.iter().any(|(other, area)| {
            other != id && area.x == right + 1 && area.y < rect.y + rect.h && rect.y < area.y + area.h
        }) {
            for row in rect.y..rect.y + rect.h {
                surface.put_char(right, row, '│', base.patch(theme.get("ui.separator")), width);
            }
        }
    }
    if let Some(rect) = explorer {
        draw_explorer(ed, &mut surface, &theme, rect);
    }
    command_line(ed, &mut surface, &theme);
    if ed.completion.is_some() && matches!(ed.mode, Mode::Insert) {
        completion(ed, &mut surface, &theme);
    }
    if ed.popup.is_some() {
        popup(ed, &mut surface, &theme);
    }
    which_key(ed, &mut surface, &theme);
    if ed.picker.is_some() {
        picker(ed, &mut surface, &theme);
    }
    surface
}

fn bufferline(ed: &Editor, surface: &mut Surface, theme: &Theme) {
    let base = theme.text().patch(theme.get("ui.bufferline"));
    surface.fill(0, 0, surface.width, 1, base);
    let current = ed.view().doc;
    let mut tabs: Vec<(String, bool)> = Vec::new();
    for (index, id) in ed.buffers.iter().enumerate() {
        let doc = &ed.docs[id];
        let modified = if doc.modified() { " ●" } else { "" };
        tabs.push((format!(" {} {}{modified} ", index + 1, doc.file_name()), *id == current));
    }
    // Scroll so the current buffer is visible.
    let widths: Vec<u16> = tabs.iter().map(|(text, _)| str_width(text) as u16).collect();
    let active = tabs.iter().position(|(_, active)| *active).unwrap_or(0);
    let mut start = 0;
    while start < active && widths[start..=active].iter().sum::<u16>() > surface.width.saturating_sub(4) {
        start += 1;
    }
    let mut x = 0;
    if start > 0 {
        x = surface.text(0, 0, "‹", base, surface.width);
    }
    for (text, active) in &tabs[start..] {
        let style = if *active { theme.text().patch(theme.get("ui.bufferline.active")) } else { base };
        if x + str_width(text) as u16 > surface.width {
            surface.text(surface.width.saturating_sub(1), 0, "›", base, surface.width);
            break;
        }
        x = surface.text(x, 0, text, style, surface.width);
    }
}

fn dashboard(ed: &Editor, surface: &mut Surface, theme: &Theme, rect: Rect) {
    let logo = ["        __     ", " __ __ / /___  ", "/ // // // -_) ", "\\_,_//_/ \\__/  "];
    let leader = if crate::keys::notation(&ed.keymap.leader) == "<space>" {
        "␣".to_string()
    } else {
        crate::keys::notation(&ed.keymap.leader)
    };
    let items = [
        (format!("{leader}{leader}"), "find file"),
        (format!("{leader}/"), "search the project"),
        (format!("{leader}."), "recent files"),
        (format!("{leader}e"), "file explorer"),
        (format!("{leader}fc"), "settings (ule.toml)"),
        (format!("{leader}?"), "all key bindings"),
        (":help".to_string(), "help"),
        (":q".to_string(), "quit"),
    ];
    let total = logo.len() as u16 + 3 + items.len() as u16;
    let mut y = rect.y + rect.h.saturating_sub(total) / 2;
    let logo_style = theme.text().patch(theme.get("ui.dashboard.logo"));
    for line in logo {
        let x = rect.x + rect.w.saturating_sub(str_width(line) as u16) / 2;
        surface.text(x, y, line, logo_style, rect.x + rect.w);
        y += 1;
    }
    let title = format!("Unlaw editor {}", env!("CARGO_PKG_VERSION"));
    let x = rect.x + rect.w.saturating_sub(str_width(&title) as u16) / 2;
    surface.text(x, y, &title, theme.text().patch(theme.get("ui.hint")), rect.x + rect.w);
    y += 2;
    let key_style = theme.text().patch(theme.get("ui.dashboard.key"));
    let column = rect.x + rect.w.saturating_sub(30) / 2;
    for (key, label) in items {
        if y >= rect.y + rect.h {
            break;
        }
        surface.text(column, y, &key, key_style, rect.x + rect.w);
        surface.text(column + 8, y, label, theme.text(), rect.x + rect.w);
        y += 1;
    }
}

#[derive(Clone, Copy)]
struct Overlay {
    start: Pos,
    end: Pos,
    style: Style,
}

fn draw_view(ed: &mut Editor, surface: &mut Surface, theme: &Theme, id: usize, rect: Rect) {
    let focused = id == ed.focus && ed.focus_area == Focus::View;
    let Some(view) = ed.views.get(&id) else {
        return;
    };
    let doc_id = view.doc;
    let area = view.area;
    let scroll = view.scroll;
    let hscroll = view.hscroll;
    let cursor = view.cursor;
    let base = theme.text();
    surface.fill(rect.x, rect.y, rect.w, rect.h, base);
    let show_dashboard = ed.docs[&doc_id].is_empty_scratch()
        && ed.buffers.len() == 1
        && ed.layout.views().len() == 1
        && Some(id) != ed.panel
        && ed.explorer.is_none();
    if show_dashboard {
        dashboard(ed, surface, theme, Rect { x: rect.x, y: rect.y, w: rect.w, h: rect.h.saturating_sub(1) });
        status_line(ed, surface, theme, id, rect, focused);
        return;
    }
    let tab = ed.tab_width(&ed.docs[&doc_id]);
    let wrap = ed.wraps(&ed.docs[&doc_id]);
    let indent_width = {
        let unit = ed.indent_unit(&ed.docs[&doc_id]);
        if unit == "\t" {
            tab
        } else {
            unit.len().max(1)
        }
    };
    let gutter_width = area.x - rect.x;
    let text_width = area.w as usize;
    // Selection, search and bracket overlays for the visible lines.
    let selection = if focused {
        match ed.mode {
            // A Shift-selection's end is exclusive, like other editors.
            Mode::Visual(_) if ed.vim.select_mode => {
                let (start, end) = (ed.anchor.min(cursor), ed.anchor.max(cursor));
                let text = &ed.docs[&doc_id].text;
                (start != end).then(|| (start, text.prev(end).unwrap_or(start), VisualKind::Char))
            }
            Mode::Visual(kind) => Some((ed.anchor.min(cursor), ed.anchor.max(cursor), kind)),
            _ => None,
        }
    } else {
        None
    };
    let mut overlays: Vec<Overlay> = Vec::new();
    let last_visible = (scroll + area.h as usize).min(ed.docs[&doc_id].text.len_lines());
    if ed.options.hlsearch && ed.hlsearch_active {
        if let Some(regex) = ed.search_regex.clone() {
            let doc = &ed.docs[&doc_id];
            for line in scroll..last_visible {
                let text = doc.text.line(line);
                for found in regex.find_iter(text) {
                    if found.is_empty() {
                        continue;
                    }
                    let start = text[..found.start()].chars().count();
                    let end = text[..found.end()].chars().count();
                    let current = focused && line == cursor.line && start == cursor.col;
                    let style = theme.get(if current { "ui.search.current" } else { "ui.search" });
                    overlays.push(Overlay { start: Pos::new(line, start), end: Pos::new(line, end), style });
                }
            }
        }
    }
    if focused && !matches!(ed.mode, Mode::Insert) {
        let doc = &ed.docs[&doc_id];
        if let Some(c) = doc.text.char_at(cursor) {
            if "()[]{}".contains(c) {
                if let Some(other) = crate::motion::match_pair(&doc.text, cursor) {
                    let style = theme.get("ui.bracket");
                    for pos in [cursor, other] {
                        overlays.push(Overlay { start: pos, end: Pos::new(pos.line, pos.col + 1), style });
                    }
                }
            }
        }
    }
    let diagnostics: Vec<(Pos, Pos, u8, String)> = ed.docs[&doc_id]
        .diagnostics
        .iter()
        .filter(|diagnostic| diagnostic.end.line >= scroll && diagnostic.start.line < last_visible)
        .map(|diagnostic| (diagnostic.start, diagnostic.end, diagnostic.severity, diagnostic.message.clone()))
        .collect();
    let diag_key = |severity: u8| match severity {
        1 => "diag.error",
        2 => "diag.warning",
        3 => "diag.info",
        _ => "diag.hint",
    };
    let block_columns = selection.filter(|(_, _, kind)| *kind == VisualKind::Block).map(|_| {
        let doc = &ed.docs[&doc_id];
        let a = col_to_display(doc.text.line(ed.anchor.line), ed.anchor.col, tab);
        let b = col_to_display(doc.text.line(cursor.line), cursor.col, tab);
        (a.min(b), a.max(b) + 1)
    });
    let mut row = 0u16;
    let mut line = scroll;
    let line_count = ed.docs[&doc_id].text.len_lines();
    let cursorline = ed.options.cursorline && focused && selection.is_none();
    let languages = std::mem::take(&mut ed.languages);
    while row < area.h && line < line_count {
        let spans: Vec<Span> = ed.docs.get_mut(&doc_id).expect("document").spans(line, &languages);
        let doc = &ed.docs[&doc_id];
        let text = doc.text.line(line);
        let chars: Vec<char> = text.chars().collect();
        let starts = if wrap { wrap_rows(text, text_width, tab) } else { vec![0] };
        let trailing_from = text.trim_end_matches([' ', '\t']).chars().count();
        let leading = chars.iter().take_while(|c| **c == ' ' || **c == '\t').count();
        let line_diagnostics: Vec<&(Pos, Pos, u8, String)> =
            diagnostics.iter().filter(|(start, end, _, _)| start.line <= line && line <= end.line).collect();
        for (segment, &segment_start) in starts.iter().enumerate() {
            if row >= area.h {
                break;
            }
            let y = area.y + row;
            let segment_end = starts.get(segment + 1).copied().unwrap_or(chars.len());
            let is_cursor_line = line == cursor.line;
            let mut row_style = base;
            if cursorline && is_cursor_line {
                row_style = row_style.patch(theme.get("ui.cursorline"));
                surface.fill(rect.x, y, rect.w, 1, row_style);
            }
            // Gutter: sign, number.
            if segment == 0 {
                let worst = line_diagnostics.iter().map(|(_, _, severity, _)| *severity).min();
                if let Some(severity) = worst {
                    surface.put_char(rect.x, y, '●', row_style.patch(theme.get(diag_key(severity))), rect.x + 1);
                }
                if ed.options.line_numbers != LineNumbers::Off {
                    let number = match ed.options.line_numbers {
                        LineNumbers::Relative if !is_cursor_line && focused => line.abs_diff(cursor.line),
                        _ => line + 1,
                    };
                    let label = format!("{number:>width$} ", width = (gutter_width - 2) as usize);
                    let style = if is_cursor_line { theme.get("ui.linenr.current") } else { theme.get("ui.linenr") };
                    surface.text(rect.x + 1, y, &label, row_style.patch(style), area.x);
                }
            } else if ed.options.line_numbers != LineNumbers::Off {
                surface.text(
                    rect.x + 1,
                    y,
                    &format!("{:>width$} ", "↪", width = (gutter_width - 2) as usize),
                    row_style.patch(theme.get("ui.linenr")),
                    area.x,
                );
            }
            // Text.
            let mut column = 0usize;
            for (index, c) in chars.iter().enumerate().take(segment_start) {
                let _ = index;
                column += width_at(*c, column, tab);
            }
            let row_origin = if wrap { column } else { hscroll };
            let mut x_display = column;
            let mut index = segment_start;
            while index < segment_end {
                let c = chars[index];
                let w = width_at(c, x_display, tab);
                if x_display + w <= row_origin {
                    x_display += w;
                    index += 1;
                    continue;
                }
                let screen = x_display.saturating_sub(row_origin);
                if screen >= text_width {
                    break;
                }
                let pos = Pos::new(line, index);
                let mut style = row_style;
                for span in &spans {
                    if span.start <= index && index < span.end {
                        style = style.patch(theme.get(span.class));
                    }
                }
                for (start, end, severity, _) in &line_diagnostics {
                    if pos >= *start && (pos < *end || (start == end && pos == *start)) {
                        let color = theme.get(diag_key(*severity)).fg;
                        style.undercurl = true;
                        style.underline_color = color;
                    }
                }
                if let Some((start, end, kind)) = selection {
                    let selected = match kind {
                        VisualKind::Char => pos >= start && pos <= end,
                        VisualKind::Line => line >= start.line && line <= end.line,
                        VisualKind::Block => {
                            let (left, right) = block_columns.unwrap_or((0, 0));
                            line >= start.line && line <= end.line && x_display >= left && x_display < right
                        }
                    };
                    if selected {
                        style = style.patch(theme.get("ui.selection"));
                    }
                }
                for overlay in &overlays {
                    if pos >= overlay.start && pos < overlay.end {
                        style = style.patch(overlay.style);
                    }
                }
                let x = area.x + screen as u16;
                let limit = area.x + area.w;
                if c == '\t' {
                    let shown = if ed.options.show_whitespace { '→' } else { ' ' };
                    let ws = if ed.options.show_whitespace { style.patch(theme.get("ui.whitespace")) } else { style };
                    surface.put_char(x, y, shown, ws, limit);
                    for extra in 1..w {
                        surface.put_char(x + extra as u16, y, ' ', style, limit);
                    }
                } else if c == ' '
                    && index < leading
                    && ed.options.indent_guides
                    && x_display % indent_width == 0
                    && x_display > 0
                {
                    surface.put_char(x, y, '│', style.patch(theme.get("ui.indent_guide")), limit);
                } else if c == ' ' && ed.options.show_whitespace && index >= trailing_from {
                    surface.put_char(x, y, '·', style.patch(theme.get("ui.whitespace")), limit);
                } else {
                    surface.put_char(x, y, c, style, limit);
                }
                x_display += w;
                index += 1;
            }
            // Selected empty lines and line ends show one selected cell.
            if let Some((start, end, kind)) = selection {
                let past_end = Pos::new(line, chars.len());
                let selected_end = match kind {
                    VisualKind::Line => line >= start.line && line <= end.line,
                    VisualKind::Char => past_end >= start && past_end <= end && line < end.line,
                    VisualKind::Block => false,
                };
                if selected_end && segment_end == chars.len() {
                    let screen = x_display.saturating_sub(row_origin);
                    if screen < text_width {
                        surface.style(area.x + screen as u16, y, theme.get("ui.selection"));
                    }
                }
            }
            // Rulers.
            for ruler in &ed.options.rulers {
                if *ruler > row_origin && *ruler - 1 - row_origin < text_width {
                    surface.style(area.x + (*ruler - 1 - row_origin) as u16, y, theme.get("ui.ruler"));
                }
            }
            // Inline diagnostic after the last segment.
            if segment + 1 == starts.len() && ed.options.inline_diagnostics {
                if let Some((_, _, severity, message)) = line_diagnostics
                    .iter()
                    .filter(|(start, _, _, _)| start.line == line)
                    .min_by_key(|(_, _, severity, _)| *severity)
                {
                    let end_screen = x_display.saturating_sub(row_origin) + 3;
                    if end_screen + 4 < text_width {
                        let style = row_style
                            .patch(theme.get(diag_key(*severity)))
                            .patch(Style { italic: true, ..Style::default() });
                        let message = message.lines().next().unwrap_or("");
                        let text = fit(&format!("● {message}"), text_width - end_screen);
                        surface.text(area.x + end_screen as u16, y, &text, style, area.x + area.w);
                    }
                }
            }
            if focused && is_cursor_line && ed.prompt.is_none() && ed.picker.is_none() {
                let in_segment =
                    cursor.col >= segment_start && (cursor.col < segment_end || segment + 1 == starts.len());
                if in_segment {
                    let display = col_to_display(text, cursor.col, tab);
                    let screen = display.saturating_sub(row_origin);
                    if screen < text_width {
                        surface.cursor = Some((area.x + screen as u16, y));
                    }
                }
            }
            row += 1;
        }
        line += 1;
    }
    ed.languages = languages;
    // `~` marks rows past the end like vim.
    while row < area.h {
        surface.text(rect.x + 1, area.y + row, "~", base.patch(theme.get("ui.linenr")), area.x);
        row += 1;
    }
    status_line(ed, surface, theme, id, rect, focused);
}

fn mode_name(ed: &Editor) -> (&'static str, &'static str) {
    if ed.vim.select_mode && matches!(ed.mode, Mode::Visual(_)) {
        return ("SELECT", "ui.mode.visual");
    }
    match ed.mode {
        Mode::Normal => ("NORMAL", "ui.mode.normal"),
        Mode::Insert => ("INSERT", "ui.mode.insert"),
        Mode::Replace => ("REPLACE", "ui.mode.replace"),
        Mode::Visual(VisualKind::Char) => ("VISUAL", "ui.mode.visual"),
        Mode::Visual(VisualKind::Line) => ("V-LINE", "ui.mode.visual"),
        Mode::Visual(VisualKind::Block) => ("V-BLOCK", "ui.mode.visual"),
    }
}

fn status_line(ed: &Editor, surface: &mut Surface, theme: &Theme, id: usize, rect: Rect, focused: bool) {
    let y = rect.y + rect.h - 1;
    let key = if focused || (id == ed.focus && ed.focus_area == Focus::Explorer) {
        "ui.statusline"
    } else {
        "ui.statusline.inactive"
    };
    let base = theme.text().patch(theme.get(key));
    surface.fill(rect.x, y, rect.w, 1, base);
    let view = &ed.views[&id];
    let doc = &ed.docs[&view.doc];
    let mut x = rect.x;
    let right_edge = rect.x + rect.w;
    if focused {
        let (name, style_key) =
            if ed.prompt.as_ref().is_some_and(|prompt| matches!(prompt.kind, crate::widgets::PromptKind::Command)) {
                ("COMMAND", "ui.mode.command")
            } else {
                mode_name(ed)
            };
        x = surface.text(x, y, &format!(" {name} "), theme.text().patch(theme.get(style_key)), right_edge);
    }
    let mut name = doc.title();
    if doc.kind == DocKind::Scratch && doc.path.is_none() {
        name = doc.name.clone();
    }
    let flags = format!("{}{}", if doc.modified() { " [+]" } else { "" }, if doc.readonly { " [RO]" } else { "" });
    // Right side first so the name is cut, not the position.
    let mut right_parts: Vec<(String, Style)> = Vec::new();
    if let Some((name, _)) = &ed.vim.macro_recording {
        right_parts.push((format!("@{name} "), base.patch(theme.get("diag.error"))));
    }
    if focused {
        if let Some(title) = ed.jobs.busy() {
            right_parts.push((format!("{} {title} ", spinner(ed)), base.patch(theme.get("ui.message.info"))));
        }
    }
    let errors = doc.diagnostics.iter().filter(|diagnostic| diagnostic.severity == 1).count();
    let warnings = doc.diagnostics.iter().filter(|diagnostic| diagnostic.severity == 2).count();
    if errors > 0 {
        right_parts.push((format!("● {errors} "), base.patch(theme.get("diag.error"))));
    }
    if warnings > 0 {
        right_parts.push((format!("● {warnings} "), base.patch(theme.get("diag.warning"))));
    }
    if let Some(status) = ed.lsp.status(doc.id) {
        right_parts.push((format!("{} ", fit(&status, 30)), base.patch(theme.get("ui.hint"))));
    }
    let lang = ed.language_name(doc);
    right_parts.push((format!("{lang} "), base));
    let lines = doc.text.len_lines();
    let percent = if lines <= 1 { 100 } else { view.cursor.line * 100 / (lines - 1) };
    let tab = ed.tab_width(doc);
    let column = col_to_display(doc.text.line(view.cursor.line), view.cursor.col, tab) + 1;
    let position = format!(" {}:{column} {percent:>3}% ", view.cursor.line + 1);
    right_parts.push((
        position,
        theme.text().patch(theme.get(if focused { mode_name(ed).1 } else { "ui.statusline.inactive" })),
    ));
    let right_width: u16 = right_parts.iter().map(|(text, _)| str_width(text) as u16).sum();
    let available = right_edge.saturating_sub(x + right_width + 2) as usize;
    let label = fit_start(&format!(" {name}{flags}"), available);
    surface.text(x, y, &label, base.patch(Style { bold: true, ..Style::default() }), right_edge);
    let mut rx = right_edge.saturating_sub(right_width);
    for (text, style) in right_parts {
        rx = surface.text(rx, y, &text, style, right_edge);
    }
}

fn command_line(ed: &Editor, surface: &mut Surface, theme: &Theme) {
    let y = surface.height - 1;
    let base = theme.text();
    surface.fill(0, y, surface.width, 1, base);
    if let Some(prompt) = &ed.prompt {
        let prefix = prompt.prefix();
        let x = surface.text(0, y, &prefix, base.patch(Style { bold: true, ..Style::default() }), surface.width);
        let available = surface.width.saturating_sub(x + 1) as usize;
        let cursor_display = str_width(&prompt.line.text.chars().take(prompt.line.cursor).collect::<String>());
        let skip = cursor_display.saturating_sub(available);
        let shown: String = {
            let mut used = 0;
            prompt
                .line
                .text
                .chars()
                .skip_while(|c| {
                    let take = used < skip;
                    used += width_at(*c, used, 8);
                    take
                })
                .collect()
        };
        surface.text(x, y, &shown, base, surface.width);
        surface.cursor = Some((x + (cursor_display - skip) as u16, y));
        surface.cursor_bar = true;
        // Completions of the command line, as a row above it.
        if !prompt.completions.is_empty() && prompt.completion.is_some() && y > 0 {
            let row_style = base.patch(theme.get("ui.popup"));
            surface.fill(0, y - 1, surface.width, 1, row_style);
            let mut cx = 1;
            let selected = prompt.completion.unwrap_or(0);
            let start = selected.saturating_sub(6);
            for (index, item) in prompt.completions.iter().enumerate().skip(start) {
                let style = if index == selected { row_style.patch(theme.get("ui.popup.selected")) } else { row_style };
                let shown = format!(" {} ", item.rsplit('/').find(|part| !part.is_empty()).unwrap_or(item));
                if cx + str_width(&shown) as u16 >= surface.width {
                    break;
                }
                cx = surface.text(cx, y - 1, &shown, style, surface.width);
            }
        }
        return;
    }
    if let Some(message) = &ed.message {
        let fresh = message.level == Level::Error || message.at.elapsed().as_secs() < 8;
        if fresh {
            let style = match message.level {
                Level::Error => theme.get("ui.message.error"),
                Level::Warning => theme.get("ui.message.warning"),
                Level::Info => Style::default(),
            };
            let text = message.text.replace('\n', " ⏎ ");
            surface.text(
                0,
                y,
                &fit(&text, surface.width.saturating_sub(12) as usize),
                base.patch(style),
                surface.width,
            );
        }
    }
    let pending: String = if !ed.vim.pending.is_empty() {
        crate::keys::notation(&ed.vim.pending)
    } else {
        crate::keys::notation(&ed.vim.insert_pending)
    };
    if !pending.is_empty() {
        let pending = pending.replace(&crate::keys::notation(&ed.keymap.leader), "␣");
        let x = surface.width.saturating_sub(str_width(&pending) as u16 + 1);
        surface.text(x, y, &pending, base.patch(theme.get("ui.hint")), surface.width);
    }
    if surface.cursor.is_some() {
        surface.cursor_bar = (matches!(ed.mode, Mode::Insert) || ed.vim.select_mode) && ed.options.cursor_shape;
    }
}

fn draw_box(surface: &mut Surface, theme: &Theme, rect: Rect, title: &str) -> Style {
    let style = theme.text().patch(theme.get("ui.popup"));
    surface.fill(rect.x, rect.y, rect.w, rect.h, style);
    let border = style.patch(theme.get("ui.popup.border"));
    let right = rect.x + rect.w - 1;
    let bottom = rect.y + rect.h - 1;
    for x in rect.x..=right {
        surface.put_char(x, rect.y, '─', border, surface.width);
        surface.put_char(x, bottom, '─', border, surface.width);
    }
    for y in rect.y..=bottom {
        surface.put_char(rect.x, y, '│', border, surface.width);
        surface.put_char(right, y, '│', border, surface.width);
    }
    surface.put_char(rect.x, rect.y, '╭', border, surface.width);
    surface.put_char(right, rect.y, '╮', border, surface.width);
    surface.put_char(rect.x, bottom, '╰', border, surface.width);
    surface.put_char(right, bottom, '╯', border, surface.width);
    if !title.is_empty() {
        let title = fit(&format!(" {title} "), rect.w.saturating_sub(4) as usize);
        surface.text(rect.x + 2, rect.y, &title, style.patch(theme.get("ui.popup.title")), right);
    }
    style
}

fn cursor_screen(ed: &Editor) -> Option<(u16, u16)> {
    let view = ed.view();
    let doc = ed.doc();
    let tab = ed.tab_width(doc);
    if view.cursor.line < view.scroll {
        return None;
    }
    let mut row = 0usize;
    let wrap = ed.wraps(doc);
    let width = view.area.w as usize;
    for line in view.scroll..view.cursor.line {
        row += if wrap { wrap_rows(doc.text.line(line), width, tab).len() } else { 1 };
    }
    let text = doc.text.line(view.cursor.line);
    let display = col_to_display(text, view.cursor.col, tab);
    let (extra_rows, column) = if wrap {
        let starts = wrap_rows(text, width, tab);
        let segment = starts.iter().rposition(|start| *start <= view.cursor.col).unwrap_or(0);
        (segment, display - col_to_display(text, starts[segment], tab))
    } else {
        (0, display.saturating_sub(view.hscroll))
    };
    let y = view.area.y as usize + row + extra_rows;
    Some(((view.area.x as usize + column) as u16, y as u16))
}

fn completion(ed: &Editor, surface: &mut Surface, theme: &Theme) {
    let Some(completion) = &ed.completion else {
        return;
    };
    if completion.shown.is_empty() {
        return;
    }
    let Some((cx, cy)) = cursor_screen(ed) else {
        return;
    };
    let prefix_width = completion.start.col.min(ed.cursor().col);
    let x = cx.saturating_sub((ed.cursor().col - prefix_width) as u16 + 1);
    let max_rows = 10.min(completion.shown.len()) as u16;
    let label_width = completion
        .shown
        .iter()
        .take(200)
        .map(|index| str_width(&completion.items[*index].label))
        .max()
        .unwrap_or(4)
        .min(40);
    let detail_width = completion
        .shown
        .iter()
        .take(200)
        .map(|index| str_width(&completion.items[*index].detail))
        .max()
        .unwrap_or(0)
        .min(30);
    let width = (label_width + detail_width + 12).min(surface.width as usize - 2) as u16;
    let below = cy + 1 + max_rows < surface.height - 1;
    let y = if below { cy + 1 } else { cy.saturating_sub(max_rows) };
    let x = x.min(surface.width.saturating_sub(width));
    let style = theme.text().patch(theme.get("ui.popup"));
    let selected = completion.selected;
    let offset = match selected {
        Some(index) if index >= max_rows as usize => index + 1 - max_rows as usize,
        _ => 0,
    };
    for row in 0..max_rows {
        let index = offset + row as usize;
        let Some(item) = completion.shown.get(index).map(|shown| &completion.items[*shown]) else {
            break;
        };
        let row_style = if selected == Some(index) { style.patch(theme.get("ui.popup.selected")) } else { style };
        surface.fill(x, y + row, width, 1, row_style);
        let kind: String = item.kind.chars().take(4).collect();
        surface.text(x + 1, y + row, &format!("{kind:<4}"), row_style.patch(theme.get("ui.hint")), x + width);
        surface.text(x + 6, y + row, &fit(&item.label, label_width), row_style, x + width);
        if !item.detail.is_empty() {
            let detail = fit(&item.detail, (width as usize).saturating_sub(label_width + 9));
            let dx = x + width - str_width(&detail) as u16 - 1;
            surface.text(dx, y + row, &detail, row_style.patch(theme.get("ui.hint")), x + width);
        }
    }
    // Documentation of the selected item beside the menu.
    if let Some(item) = completion.selected_item() {
        if !item.documentation.trim().is_empty() {
            let doc_x = x + width + 1;
            if doc_x + 20 < surface.width {
                let doc_width = (surface.width - doc_x - 1).min(60);
                let lines: Vec<String> = markdown_lines(&item.documentation, doc_width as usize - 2)
                    .into_iter()
                    .map(|(text, _)| text)
                    .take(12)
                    .collect();
                let rect = Rect { x: doc_x, y, w: doc_width, h: lines.len() as u16 + 2 };
                let inner = draw_box(surface, theme, rect, "");
                for (row, line) in lines.iter().enumerate() {
                    surface.text(doc_x + 1, y + 1 + row as u16, line, inner, doc_x + doc_width - 1);
                }
            }
        }
    }
}

/// Very small Markdown: fences dropped (their lines marked as code), headings bold, wrapped.
fn markdown_lines(text: &str, width: usize) -> Vec<(String, &'static str)> {
    let mut out = Vec::new();
    let mut in_code = false;
    for line in text.lines() {
        if line.trim_start().starts_with("```") {
            in_code = !in_code;
            continue;
        }
        let (content, class) = if in_code {
            (line.to_string(), "syntax.code")
        } else if line.starts_with('#') {
            (line.trim_start_matches('#').trim().to_string(), "syntax.heading")
        } else if line.trim() == "---" {
            ("─".repeat(width.min(40)), "ui.popup.border")
        } else {
            (line.replace("**", "").replace('`', ""), "")
        };
        if content.is_empty() {
            if out.last().is_some_and(|(last, _): &(String, &str)| !last.is_empty()) {
                out.push((String::new(), ""));
            }
            continue;
        }
        let starts = wrap_rows(&content, width.max(10), 4);
        let chars: Vec<char> = content.chars().collect();
        for (index, start) in starts.iter().enumerate() {
            let end = starts.get(index + 1).copied().unwrap_or(chars.len());
            out.push((chars[*start..end].iter().collect(), class));
        }
    }
    while out.last().is_some_and(|(text, _)| text.is_empty()) {
        out.pop();
    }
    out
}

fn popup(ed: &Editor, surface: &mut Surface, theme: &Theme) {
    let Some(popup) = &ed.popup else {
        return;
    };
    let max_width = (surface.width as usize).saturating_sub(4).min(if popup.kind == crate::widgets::PopupKind::Info {
        110
    } else {
        80
    });
    let lines: Vec<(String, &str)> = if popup.markdown {
        markdown_lines(&popup.lines.join("\n"), max_width.saturating_sub(2))
    } else {
        popup
            .lines
            .iter()
            .flat_map(|line| {
                let starts = wrap_rows(line, max_width.saturating_sub(2), 4);
                let chars: Vec<char> = line.chars().collect();
                starts
                    .iter()
                    .enumerate()
                    .map(|(index, start)| {
                        let end = starts.get(index + 1).copied().unwrap_or(chars.len());
                        (chars[*start..end].iter().collect::<String>(), "")
                    })
                    .collect::<Vec<_>>()
            })
            .collect()
    };
    if lines.is_empty() {
        return;
    }
    let content_width = lines
        .iter()
        .map(|(text, _)| str_width(text))
        .max()
        .unwrap_or(10)
        .max(str_width(&popup.title) + 4)
        .min(max_width);
    let max_height = (surface.height as usize).saturating_sub(4).min(24);
    let height = lines.len().min(max_height);
    let w = content_width as u16 + 2;
    let h = height as u16 + 2;
    let (x, y) = match (popup.kind == crate::widgets::PopupKind::Hover, cursor_screen(ed)) {
        (true, Some((cx, cy))) => {
            let y = if cy + 1 + h < surface.height - 1 { cy + 1 } else { cy.saturating_sub(h) };
            (cx.min(surface.width.saturating_sub(w)), y)
        }
        _ => ((surface.width.saturating_sub(w)) / 2, (surface.height.saturating_sub(h)) / 3),
    };
    let more = if lines.len() > height {
        format!("{} {}/{}", popup.title, popup.scroll + height, lines.len())
    } else {
        popup.title.clone()
    };
    let style = draw_box(surface, theme, Rect { x, y, w, h }, more.trim());
    for (row, (text, class)) in lines.iter().skip(popup.scroll).take(height).enumerate() {
        let line_style = if class.is_empty() { style } else { style.patch(theme.get(class)) };
        surface.text(x + 1, y + 1 + row as u16, text, line_style, x + w - 1);
    }
}

fn which_key(ed: &Editor, surface: &mut Surface, theme: &Theme) {
    if !ed.options.whichkey || ed.vim.pending.is_empty() || ed.picker.is_some() || ed.prompt.is_some() {
        return;
    }
    // Only after a short pause, so fast typists are not distracted.
    if ed.vim.pending_since.is_some_and(|since| since.elapsed().as_millis() < 200) {
        return;
    }
    let mode = if matches!(ed.mode, Mode::Visual(_)) { KeyMode::Visual } else { KeyMode::Normal };
    let keys = &ed.vim.pending;
    let start = if keys.first().and_then(|key| key.as_char()) == Some('"') { 2 } else { 0 };
    let start = start
        + keys[start.min(keys.len())..]
            .iter()
            .take_while(|key| key.as_char().is_some_and(|c| c.is_ascii_digit()))
            .count();
    if start >= keys.len() {
        return;
    }
    let mut entries = ed.keymap.continuations(mode, &keys[start..]);
    // Vim's own keys after g and z complete the picture.
    if keys.len() == start + 1 {
        let extra: &[(&str, &str)] = match keys[start].as_char() {
            Some('g') => &[
                ("g", "first line"),
                ("e", "end of previous word"),
                ("_", "last non-blank"),
                ("u", "lowercase…"),
                ("U", "uppercase…"),
                ("~", "toggle case…"),
                ("c", "comment…"),
                ("v", "reselect"),
                ("i", "insert at last place"),
                ("J", "join without spaces"),
                ("p", "paste, cursor after"),
            ],
            Some('z') => &[("z", "center the line"), ("t", "line to top"), ("b", "line to bottom")],
            _ => &[],
        };
        for (key, description) in extra {
            if !entries.iter().any(|(existing, _, _)| existing == key) {
                entries.push((key.to_string(), description.to_string(), false));
            }
        }
    }
    if entries.is_empty() {
        return;
    }
    entries.sort_by(|a, b| b.2.cmp(&a.2).then(a.0.to_lowercase().cmp(&b.0.to_lowercase())));
    let cell = entries
        .iter()
        .map(|(key, description, _)| str_width(key) + str_width(description) + 4)
        .max()
        .unwrap_or(10)
        .min(40);
    let columns = ((surface.width as usize - 4) / cell).max(1);
    let rows = entries.len().div_ceil(columns);
    let rows = rows.min(surface.height as usize / 2);
    let w = surface.width;
    let h = rows as u16 + 2;
    let y = surface.height.saturating_sub(h + 1);
    let title = crate::keys::notation(&keys[start..]).replace(&crate::keys::notation(&ed.keymap.leader), "␣");
    let style = draw_box(surface, theme, Rect { x: 0, y, w, h }, &title);
    let key_style = style.patch(theme.get("ui.dashboard.key"));
    let group_style = style.patch(theme.get("ui.popup.title"));
    for (index, (key, description, group)) in entries.iter().enumerate() {
        let column = index / rows;
        let row = index % rows;
        if column >= columns {
            break;
        }
        let x = 2 + (column * cell) as u16;
        let key_shown = if key == "<space>" { "␣".to_string() } else { key.clone() };
        let after = surface.text(x, y + 1 + row as u16, &key_shown, key_style, w - 1);
        surface.text(after + 1, y + 1 + row as u16, "→", style.patch(theme.get("ui.hint")), w - 1);
        let text = fit(description, cell.saturating_sub(str_width(&key_shown) + 4));
        surface.text(after + 3, y + 1 + row as u16, &text, if *group { group_style } else { style }, w - 1);
    }
}

fn picker(ed: &mut Editor, surface: &mut Surface, theme: &Theme) {
    let width = surface.width;
    let height = surface.height;
    let w = (width as f32 * 0.9) as u16;
    let h = (height as f32 * 0.85) as u16;
    let x = (width - w) / 2;
    let y = (height - h) / 2;
    let Some(picker) = ed.picker.as_ref() else {
        return;
    };
    let show_preview = picker.preview
        && w > 90
        && picker.current().is_some_and(|item| crate::picker::preview_target(item, ed).is_some());
    let list_w = if show_preview { w * 2 / 5 } else { w };
    let title = picker.title.clone();
    let style = draw_box(surface, theme, Rect { x, y, w: list_w, h }, &title);
    // Prompt line.
    let count = format!(
        "{}/{}{}",
        picker.matches.len(),
        picker.items.len(),
        if picker.loading { format!(" {}", spinner(ed)) } else { String::new() }
    );
    let prompt_y = y + 1;
    let after = surface.text(x + 2, prompt_y, "› ", style.patch(theme.get("ui.popup.title")), x + list_w - 1);
    let input = picker.input.text.clone();
    let cursor_width = str_width(&input.chars().take(picker.input.cursor).collect::<String>()) as u16;
    surface.text(after, prompt_y, &input, style, x + list_w - str_width(&count) as u16 - 2);
    surface.text(
        x + list_w - str_width(&count) as u16 - 2,
        prompt_y,
        &count,
        style.patch(theme.get("ui.hint")),
        x + list_w - 1,
    );
    surface.cursor = Some((after + cursor_width, prompt_y));
    surface.cursor_bar = true;
    for column in x + 1..x + list_w - 1 {
        surface.put_char(column, prompt_y + 1, '─', style.patch(theme.get("ui.popup.border")), width);
    }
    let list_y = prompt_y + 2;
    let rows = (y + h - 1).saturating_sub(list_y) as usize;
    let picker = ed.picker.as_mut().expect("picker");
    if picker.selected < picker.offset {
        picker.offset = picker.selected;
    }
    if picker.selected >= picker.offset + rows {
        picker.offset = picker.selected + 1 - rows;
    }
    let offset = picker.offset;
    let match_style = style.patch(theme.get("ui.popup.match"));
    for row in 0..rows {
        let Some((index, positions)) = picker.matches.get(offset + row) else {
            break;
        };
        let item = &picker.items[*index];
        let selected = offset + row == picker.selected;
        let row_style = if selected { style.patch(theme.get("ui.popup.selected")) } else { style };
        let ry = list_y + row as u16;
        surface.fill(x + 1, ry, list_w - 2, 1, row_style);
        let detail_width = str_width(&item.detail) as u16;
        let label_limit = x + list_w - 2 - if detail_width > 0 { detail_width + 2 } else { 0 };
        let mut cx = x + 2;
        if selected {
            surface.text(x + 1, ry, "▌", row_style.patch(theme.get("ui.popup.title")), x + 2);
        }
        for (char_index, c) in item.label.chars().enumerate() {
            let char_style =
                if positions.binary_search(&char_index).is_ok() { row_style.patch(match_style) } else { row_style };
            let used = surface.put_char(cx, ry, c, char_style, label_limit);
            if used == 0 && width_at(c, 0, 8) > 0 {
                break;
            }
            cx += used;
        }
        if detail_width > 0 {
            surface.text(
                x + list_w - 2 - detail_width,
                ry,
                &item.detail,
                row_style.patch(theme.get("ui.hint")),
                x + list_w - 1,
            );
        }
    }
    if show_preview {
        let item = picker.current().cloned();
        if let Some(item) = item {
            preview(ed, surface, theme, Rect { x: x + list_w, y, w: w - list_w, h }, &item);
        }
    }
}

fn preview(ed: &mut Editor, surface: &mut Surface, theme: &Theme, rect: Rect, item: &crate::picker::Item) {
    let Some((path, first, highlight)) = crate::picker::preview_target(item, ed) else {
        return;
    };
    let title = crate::document::display_path(&path);
    let style = draw_box(surface, theme, rect, &title);
    let cached = ed.picker.as_ref().and_then(|picker| picker.cache.as_ref()).is_some_and(|(cached, _)| *cached == path);
    if !cached {
        let lines = match ed.find_doc(&path) {
            Some(id) => ed.docs[&id].text.lines().take(20_000).map(str::to_string).collect(),
            None => read_preview(&path),
        };
        if let Some(picker) = ed.picker.as_mut() {
            picker.cache = Some((path.clone(), lines));
        }
    }
    let Some((_, lines)) = ed.picker.as_ref().and_then(|picker| picker.cache.clone()) else {
        return;
    };
    let rows = rect.h.saturating_sub(2) as usize;
    let top = first.saturating_sub(rows / 3);
    let lang = ed.languages.detect(Some(&path), lines.first().map_or("", String::as_str));
    // Highlight from a little above the window so multi-line strings/comments are right.
    let from = top.saturating_sub(200);
    let spans: Vec<Vec<Span>> = match lang.and_then(|index| ed.languages.get(index)) {
        Some(lang) => crate::syntax::highlight_lines(
            &ed.languages,
            lang,
            lines[from.min(lines.len())..(top + rows).min(lines.len())].iter().map(String::as_str),
        ),
        None => Vec::new(),
    };
    for row in 0..rows {
        let index = top + row;
        let Some(text) = lines.get(index) else {
            break;
        };
        let y = rect.y + 1 + row as u16;
        let mut line_style = style;
        if Some(index) == highlight {
            line_style = line_style.patch(theme.get("ui.cursorline"));
            surface.fill(rect.x + 1, y, rect.w - 2, 1, line_style);
        }
        let number = format!("{:>4} ", index + 1);
        let mut x = surface.text(rect.x + 1, y, &number, line_style.patch(theme.get("ui.linenr")), rect.x + rect.w - 1);
        let line_spans = spans.get(index - from.min(index));
        let mut column = 0;
        for (char_index, c) in text.chars().enumerate() {
            let mut char_style = line_style;
            if let Some(line_spans) = line_spans {
                for span in line_spans {
                    if span.start <= char_index && char_index < span.end {
                        char_style = char_style.patch(theme.get(span.class));
                    }
                }
            }
            if c == '\t' {
                let w = 4 - column % 4;
                x += w as u16;
                column += w;
                continue;
            }
            let used = surface.put_char(x, y, c, char_style, rect.x + rect.w - 1);
            if used == 0 && width_at(c, 0, 8) > 0 {
                break;
            }
            x += used;
            column += used as usize;
        }
    }
}

fn read_preview(path: &Path) -> Vec<String> {
    let Ok(metadata) = std::fs::metadata(path) else {
        return vec!["(cannot read)".into()];
    };
    if metadata.is_dir() {
        return vec!["(folder)".into()];
    }
    let Ok(bytes) = std::fs::read(path) else {
        return vec!["(cannot read)".into()];
    };
    let bytes = &bytes[..bytes.len().min(2_000_000)];
    if bytes.iter().take(8000).any(|byte| *byte == 0) {
        return vec![format!("(binary, {} bytes)", metadata.len())];
    }
    String::from_utf8_lossy(bytes).lines().take(20_000).map(str::to_string).collect()
}

fn draw_explorer(ed: &Editor, surface: &mut Surface, theme: &Theme, rect: Rect) {
    let Some(explorer) = &ed.explorer else {
        return;
    };
    let focused = ed.focus_area == Focus::Explorer;
    let base = theme.text();
    surface.fill(rect.x, rect.y, rect.w + 1, rect.h, base);
    for row in rect.y..rect.y + rect.h {
        surface.put_char(rect.x + rect.w, row, '│', base.patch(theme.get("ui.separator")), surface.width);
    }
    let root = explorer
        .root
        .file_name()
        .map_or_else(|| explorer.root.display().to_string(), |name| name.to_string_lossy().into_owned());
    let title_style = base.patch(theme.get(if focused { "ui.popup.title" } else { "ui.hint" }));
    surface.text(rect.x + 1, rect.y, &fit(&format!("{root}/"), rect.w as usize - 2), title_style, rect.x + rect.w);
    let rows = rect.h.saturating_sub(1) as usize;
    let mut offset = explorer.offset;
    if explorer.selected < offset {
        offset = explorer.selected;
    }
    if explorer.selected >= offset + rows {
        offset = explorer.selected + 1 - rows;
    }
    let current = ed.doc().path.clone();
    for row in 0..rows {
        let Some(entry) = explorer.entries.get(offset + row) else {
            break;
        };
        let y = rect.y + 1 + row as u16;
        let selected = offset + row == explorer.selected;
        let mut style = base;
        if selected {
            style = style.patch(theme.get(if focused { "ui.popup.selected" } else { "ui.cursorline" }));
            surface.fill(rect.x, y, rect.w, 1, style);
        }
        let icon = if entry.dir {
            if explorer.is_expanded(&entry.path) {
                "▾ "
            } else {
                "▸ "
            }
        } else {
            "  "
        };
        let mut name_style = style;
        if entry.dir {
            name_style = name_style.patch(theme.get("ui.explorer.dir"));
        }
        if current.as_ref() == Some(&entry.path) {
            name_style = name_style.patch(theme.get("ui.popup.match"));
        }
        let indent = "  ".repeat(entry.depth);
        let x = surface.text(rect.x + 1, y, &indent, style, rect.x + rect.w);
        let x = surface.text(x, y, icon, style.patch(theme.get("ui.hint")), rect.x + rect.w);
        surface.text(
            x,
            y,
            &fit(&entry.name, (rect.x + rect.w).saturating_sub(x + 1) as usize),
            name_style,
            rect.x + rect.w,
        );
    }
    if focused {
        let row = explorer.selected.saturating_sub(offset) as u16;
        surface.cursor = Some((rect.x + 1, rect.y + 1 + row));
    }
}

/// The color the terminal background should be (themes with their own background).
pub fn background(theme: &Theme) -> Option<Color> {
    theme.text().bg
}
