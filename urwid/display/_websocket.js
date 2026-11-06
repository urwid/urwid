// Urwid WebSocket display: the page script's connection to urwid.display.websocket.Screen

// Loaded after web_common.js, whose rendering and key names it uses.
// Every message the server sends is a screen update in the row format of render_update().
// The page sends JSON messages: {"type": "key", "key": <name>} and {"type": "resize", "cols": <n>, "rows": <n>}.

"use strict";

const check_font_delay = 1000;

let socket = null;
let screen_x = null;
let screen_y = null;

function websocket_url() {
    const url = new URL(document.body.dataset.websocketPath, window.location.href);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    return url;
}

function send_message(message) {
    if (socket !== null && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(message));
    }
}

function on_keydown(e) {
    if (socket === null) {
        return;
    }
    const name = key_event_name(e);
    if (name === null) {
        return;
    }
    e.stopPropagation();
    e.preventDefault();
    send_message({type: "key", key: name});
}

// force sends the size even when it did not change, for the server's first view of it
function on_resize(force) {
    // the measured size is a quotient of floats, and not a number before the fonts are laid out
    const [x_size, y_size] = measure_screen().map(Math.floor);
    if (!(x_size >= 1 && y_size >= 1)) {
        return;
    }
    if (force === true || screen_x !== x_size || screen_y !== y_size) {
        send_message({type: "resize", cols: x_size, rows: y_size});
    }
    screen_x = x_size;
    screen_y = y_size;
}

function on_message(event) {
    if (typeof event.data !== "string") {
        return;
    }
    // the newline that ends the last row
    render_update(event.data.endsWith("\n") ? event.data.slice(0, -1) : event.data);
}

function on_close() {
    socket = null;
    set_status("Connection Closed");
}

function start() {
    set_status("Connecting");
    socket = new WebSocket(websocket_url());
    socket.addEventListener("open", () => {
        set_status("Connected");
        on_resize(true);
    });
    socket.addEventListener("message", on_message);
    socket.addEventListener("close", on_close);

    document.addEventListener("keydown", on_keydown);
    window.addEventListener("resize", on_resize);
    setInterval(on_resize, check_font_delay);
}

start();
