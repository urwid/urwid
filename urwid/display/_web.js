// Urwid web (CGI/Asynchronous Javascript) display module
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

const colours = {
    '0': "black",
    '1': "#c00000",
    '2': "green",
    '3': "#804000",
    '4': "#0000c0",
    '5': "#c000c0",
    '6': "teal",
    '7': "silver",
    '8': "gray",
    '9': "#ff6060",
    'A': "lime",
    'B': "yellow",
    'C': "#8080ff",
    'D': "#ff40ff",
    'E': "aqua",
    'F': "white"
};

// KeyboardEvent.key values that urwid knows under a different name.
const key_names = {
    "Backspace": "backspace", "Tab": "tab", "Enter": "enter", "Escape": "esc",
    "PageUp": "page up", "PageDown": "page down", "End": "end", "Home": "home",
    "ArrowLeft": "left", "ArrowUp": "up", "ArrowRight": "right", "ArrowDown": "down",
    "Insert": "insert", "Delete": "delete"
};

const function_key = /^F([1-9]|1[0-2])$/;

// Boundary used by the multipart/x-mixed-replace stream sent by web.py.
const boundary = "ZZ";

const check_font_delay = 1000;
const poll_again_delay = 500;
const send_queue_max = 32;

const request_url = document.URL;

let update_method = null;
let urwid_id = null;
let screen_x = null;
let screen_y = null;

let send_queue = [];
let sending = false;

function load_web_display() {
    if (typeof fetch !== "function") {
        set_status("Connection Failed");
        alert("This browser is too old to run the urwid web display.");
        return;
    }

    document.addEventListener("keydown", body_keydown);
    window.addEventListener("resize", body_resize);

    update_method = supports_streaming() ? "multipart" : "polling";

    body_resize();
    send_queue = []; // don't queue the first resize, it is sent with the request

    set_status("Connecting");
    void start_connection();

    setInterval(body_resize, check_font_delay);
}

// The multipart update method needs the response body as a stream: browsers
// only demultiplex multipart/x-mixed-replace for images and navigations.
function supports_streaming() {
    return typeof ReadableStream === "function"
        && typeof TextDecoder === "function"
        && typeof Response === "function"
        && "body" in Response.prototype;
}

async function start_connection() {
    try {
        const response = await fetch(request_url, {
            method: "POST",
            headers: {
                "X-Urwid-Method": update_method,
                "Content-Type": "text/plain; charset=utf-8"
            },
            body: "window resize " + screen_x + " " + screen_y + "\n"
        });
        if (!check_response(response)) {
            return;
        }

        urwid_id = response.headers.get("X-Urwid-ID");
        set_status(update_method === "polling" ? "Polling" : "Connected");
        void flush_send_queue();

        if (update_method === "polling") {
            if (handle_update(await response.text())) {
                poll_again();
            }
        } else {
            await read_updates(response.body);
        }
    } catch (e) {
        connection_failed(e);
    }
}

async function do_poll() {
    if (update_method !== "polling" || urwid_id === null) {
        return;
    }
    try {
        const response = await fetch(request_url, {
            method: "POST",
            headers: {
                "X-Urwid-Method": "polling",
                "X-Urwid-ID": urwid_id,
                "Content-Type": "text/plain; charset=utf-8"
            },
            body: ""
        });
        if (!check_response(response)) {
            return;
        }
        if (handle_update(await response.text())) {
            poll_again();
        }
    } catch (e) {
        connection_failed(e);
    }
}

function poll_again() {
    if (update_method === "polling") {
        setTimeout(do_poll, poll_again_delay);
    }
}

// Read screen updates from the multipart/x-mixed-replace body stream.
async function read_updates(body) {
    const reader = body.getReader();
    const decoder = new TextDecoder("utf-8");
    const parser = new MultipartParser(boundary);

    try {
        for (;;) {
            const chunk = await reader.read();
            if (chunk.done) {
                break;
            }
            let open = true;
            for (const part of parser.push(decoder.decode(chunk.value, {stream: true}))) {
                open = handle_update(part);
                if (!open) {
                    break;
                }
            }
            if (!open || parser.finished) {
                return;
            }
        }
        set_status("Connection Closed");
        update_method = null;
    } finally {
        await reader.cancel();
    }
}

// Split a multipart/x-mixed-replace body into the payload of each part.
class MultipartParser {
    constructor(boundary_id) {
        this.delimiter = "\r\n--" + boundary_id;
        this.buffer = "";
        this.preamble = true;
        this.finished = false;
    }

    push(text) {
        this.buffer += text;

        const parts = [];
        while (!this.finished) {
            const index = this.buffer.indexOf(this.delimiter);
            if (index < 0) {
                break;
            }
            // "--" marks the closing delimiter, "\r\n" ends the boundary line.
            const tail = index + this.delimiter.length;
            if (this.buffer.length < tail + 2) {
                break;
            }

            const part = this.buffer.slice(0, index);
            this.finished = this.buffer.startsWith("--", tail);
            this.buffer = this.buffer.slice(tail + 2);

            if (this.preamble) {
                this.preamble = false;
            } else {
                // an empty header block separates the part headers from the payload
                parts.push(part.startsWith("\r\n") ? part.slice(2) : part);
            }
        }
        return parts;
    }
}

// Returns false once the server has closed the connection.
function handle_update(payload) {
    let text = payload;
    if (text.startsWith("\r\n")) {
        text = text.slice(2); // padding after the CGI headers
    }
    if (text.endsWith("\n")) {
        text = text.slice(0, -1); // terminator of the last row
    }

    if (text === "") {
        return true; // keepalive
    }
    if (text === "Z") {
        set_status("Connection Closed");
        update_method = null;
        return false;
    }

    render_update(text);
    return true;
}

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
            line.appendChild(make_span(frag.slice(3), frag.charAt(0), frag.charAt(1), frag.charAt(2)));
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

function make_span(s, fg, bg, attrs) {
    const d = document.createElement('span');
    d.style.backgroundColor = colours[bg];
    d.style.color = colours[fg];
    if (attrs === 'f') {
        d.style.opacity = '0.5';
    }
    d.appendChild(document.createTextNode(s));

    return d;
}

function set_status(status) {
    document.getElementById('status').textContent = status;
}

function connection_failed(reason) {
    if (!update_method) {
        return; // the connection was closed on purpose
    }
    set_status("Connection Failed");
    alert("Error talking to server: " + reason);
}

// Returns false if the response was an error that has been reported already.
function check_response(response) {
    if (response.ok) {
        return true;
    }
    if (response.status === 404 && urwid_id !== null) {
        set_status("Connection Closed");
        update_method = null;
        return false;
    }
    if (response.status === 403 && update_method === "polling") {
        set_status("Server Refused Connection");
        alert("This server does not allow polling clients.\n\n" +
            "Please use a web browser that can read streaming " +
            "responses, such as Mozilla Firefox");
        return false;
    }
    if (response.status === 503) {
        set_status("Connection Failed");
        alert("The server has reached its maximum number of " +
            "connections.\n\nPlease try again later.");
        return false;
    }
    set_status("Connection Failed");
    alert("Error from server: " + response.statusText);
    return false;
}

function body_keydown(e) {
    if (!update_method) {
        return;
    }

    const name = key_name(e);
    if (name === null) {
        return;
    }

    let mod = "";
    if (e.ctrlKey) { mod = "ctrl " + mod; }
    if (e.altKey || e.metaKey) { mod = "meta " + mod; }
    // printable keys already carry the effect of the shift key
    if (e.shiftKey && name !== e.key) { mod = "shift " + mod; }

    e.stopPropagation();
    e.preventDefault();

    send_key(mod + name);
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

function send_key(key) {
    if (send_queue.length >= send_queue_max) {
        return; // buffer overrun
    }
    send_queue.push(key);
    void flush_send_queue();
}

async function flush_send_queue() {
    if (sending || urwid_id === null || !update_method) {
        return;
    }

    sending = true;
    try {
        while (send_queue.length > 0 && update_method) {
            const keys = send_queue;
            send_queue = [];

            const response = await fetch(request_url, {
                method: "POST",
                headers: {
                    "X-Urwid-ID": urwid_id,
                    "Content-Type": "text/plain; charset=utf-8"
                },
                body: keys.join("\n") + "\n"
            });
            if (!check_response(response)) {
                return;
            }
        }
    } catch (e) {
        connection_failed(e);
    } finally {
        sending = false;
    }
}

function body_resize() {
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

    if (screen_x !== x_size || screen_y !== y_size) {
        send_key("window resize " + x_size + " " + y_size);
    }
    screen_x = x_size;
    screen_y = y_size;
}
