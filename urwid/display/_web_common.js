// Urwid browser display: row rendering and key names shared by the page scripts
//    Copyright (C) 2004-2005  Ian Ward
//
//    This library is free software; you can redistribute it and/or
//    modify it under the terms of the GNU Lesser General Public
//    License as published by the Free Software Foundation; either
//    version 2.1 of the License, or (at your option) any later version.
//
//    This library is distributed in the hope that it will be useful,
//    but WITHOUT ANY WARRANTY; without even the implied warranty of
//    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
//    Lesser General Public License for more details.
//
//    You should have received a copy of the GNU Lesser General Public
//    License along with this library; if not, write to the Free Software
//    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
//
// Urwid web site: https://urwid.org/

"use strict";

// Separates the fields of a span within a wire-format line (see urwid.display._web_common._STYLE_SEP).
const style_separator = "";

// KeyboardEvent.key values that urwid knows under a different name.
const key_names = {
    "Backspace": "backspace", "Tab": "tab", "Enter": "enter", "Escape": "esc",
    "PageUp": "page up", "PageDown": "page down", "End": "end", "Home": "home",
    "ArrowLeft": "left", "ArrowUp": "up", "ArrowRight": "right", "ArrowDown": "down",
    "Insert": "insert", "Delete": "delete"
};

const function_key = /^F([1-9]|1[0-2])$/;

// Draw the rows of an update (see urwid.display._web_common.BrowserScreen._render_rows)
// without the newline that ends the last row.
function render_update(text) {
    const container = document.getElementById('text');
    const last_screen = Array.from(container.childNodes);

    let line = document.createElement('span');
    let row = 0;

    for (const frag of text.split("\n")) {
        if (frag === "") {
            line.appendChild(document.createElement('br'));
            place_line(container, line, row);
            row += 1;
            line = document.createElement('span');
        } else if (frag.startsWith("<")) {
            // the row is unchanged from the last screen
            const source = Number.parseInt(frag.slice(1), 10);
            if (source !== row) {
                const previous = last_screen[source];
                place_line(container, previous ? previous.cloneNode(true) : document.createElement('span'), row);
            }
            row += 1;
        } else {
            const sep = frag.indexOf(style_separator);
            line.appendChild(make_span(frag.slice(sep + 1), frag.slice(0, sep)));
        }
    }

    while (container.childNodes.length > row) {
        container.removeChild(container.lastChild);
    }
}

function place_line(container, line, row) {
    if (container.childNodes.length > row) {
        container.replaceChild(line, container.childNodes[row]);
    } else {
        container.appendChild(line);
    }
}

// rest is "text", or "url<separator>text" for a hyperlink
function make_span(rest, style) {
    const sep = rest.indexOf(style_separator);
    const d = document.createElement('span');
    d.style.cssText = style;
    d.appendChild(document.createTextNode(sep < 0 ? rest : rest.slice(sep + 1)));
    if (sep < 0) {
        return d;
    }

    // a new tab, so following the link does not end the session drawn in this one
    const a = document.createElement('a');
    a.href = rest.slice(0, sep);
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.appendChild(d);
    return a;
}

function set_status(status) {
    document.getElementById('status').textContent = status;
}

// Map a KeyboardEvent to an urwid key name with its modifiers, or null if urwid ignores it.
function key_event_name(e) {
    const name = key_name(e);
    if (name === null) {
        return null;
    }

    let mod = "";
    if (e.ctrlKey) { mod = "ctrl " + mod; }
    if (e.altKey || e.metaKey) { mod = "meta " + mod; }
    // printable keys already carry the effect of the shift key
    if (e.shiftKey && name !== e.key) { mod = "shift " + mod; }
    return mod + name;
}

// Map a KeyboardEvent to an urwid key name, or null if urwid ignores it.
function key_name(e) {
    if (e.isComposing || !e.key || e.key === "Unidentified") {
        return null;
    }
    if (Object.prototype.hasOwnProperty.call(key_names, e.key)) {
        return key_names[e.key];
    }
    if (function_key.test(e.key)) {
        return e.key.toLowerCase();
    }
    if (Array.from(e.key).length === 1) {
        return e.key; // a printable character
    }
    return null; // modifier or a key urwid has no name for
}

// Fit the text area to the window in whole characters and return its size in [columns, rows].
function measure_screen() {
    const t = document.getElementById('testchar');
    const t2 = document.getElementById('testchar2');
    const text = document.getElementById('text');

    const char_width = t.offsetLeft / 44;
    const avail_width = window.innerWidth - 18;
    const x_size = (avail_width - (avail_width % char_width)) / char_width;

    const char_height = t2.offsetTop - t.offsetTop;
    const avail_height = window.innerHeight - text.offsetTop - 10;
    const y_size = (avail_height - (avail_height % char_height)) / char_height;

    text.style.width = x_size * char_width + "px";
    text.style.height = y_size * char_height + "px";
    return [x_size, y_size];
}
