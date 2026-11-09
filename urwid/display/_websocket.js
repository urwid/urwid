// Urwid WebSocket display: the page script's connection to urwid.display.websocket.Screen

// Loaded after web_common.js, whose rendering and key names it uses.
// Every message the server sends is a screen update in the row format of render_update().
// The page sends JSON messages: {"type": "key", "key": <name>}, {"type": "resize", "cols": <n>, "rows": <n>}
// and {"type": "mouse", "event": <name>, "button": <n>, "col": <n>, "row": <n>}.

"use strict";

const check_font_delay = 1000;

let socket = null;
let screen_x = null;
let screen_y = null;

// urwid's button numbers for MouseEvent.button: left, middle, right, back, forward
const mouse_buttons = [1, 2, 3, 8, 9];
// the MouseEvent.buttons bit of each MouseEvent.button value
const button_bits = [1, 4, 2, 8, 16];
// the urwid number of the button held down, which drag and release events report, or null
let pressed_button = null;
// the MouseEvent.buttons bit of that button, and the pointer that pressed it
let pressed_bit = 0;
let pressed_pointer = null;
// the cell of the last press or drag, so a drag is sent only when the pointer reaches another cell
let last_cell = null;

// the wheel distance of one step, in lines of text; one notch of a mouse wheel is about this or more
const wheel_lines = 3;
// the wheel distance not sent yet, so the small steps of a touchpad add up to whole steps
let wheel_x = 0;
let wheel_y = 0;

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

// The modifier prefix of a mouse event name, in the order urwid writes it.
function mouse_modifiers(e) {
    let mod = "";
    if (e.shiftKey) { mod += "shift "; }
    if (e.altKey || e.metaKey) { mod += "meta "; }
    if (e.ctrlKey) { mod += "ctrl "; }
    return mod;
}

// The screen cell under the pointer, as [column, row]; it may be outside the screen.
function mouse_cell(e) {
    const [char_width, char_height] = char_size();
    const text = document.getElementById('text');
    const rect = text.getBoundingClientRect();
    // the rows start inside the border of the text area
    const x = e.clientX - rect.left - text.clientLeft;
    const y = e.clientY - rect.top - text.clientTop;
    return [Math.floor(x / char_width), Math.floor(y / char_height)];
}

function inside_screen(cell) {
    return screen_x !== null && cell[0] >= 0 && cell[1] >= 0 && cell[0] < screen_x && cell[1] < screen_y;
}

// The nearest cell of the screen, for a drag or a release outside it.
function clamp_cell(cell) {
    return [Math.min(Math.max(cell[0], 0), screen_x - 1), Math.min(Math.max(cell[1], 0), screen_y - 1)];
}

function send_mouse(event, e, button, cell) {
    send_message({type: "mouse", event: mouse_modifiers(e) + event, button: button, col: cell[0], row: cell[1]});
}

function on_pointerdown(e) {
    const button = mouse_buttons[e.button];
    const cell = mouse_cell(e);
    // a second button pressed while one is held is not reported
    if (socket === null || button === undefined || pressed_button !== null || !inside_screen(cell)) {
        return;
    }
    e.preventDefault();
    // the release arrives here even when the pointer leaves the screen first
    e.currentTarget.setPointerCapture(e.pointerId);
    pressed_button = button;
    pressed_bit = button_bits[e.button];
    pressed_pointer = e.pointerId;
    last_cell = cell;
    send_mouse("mouse press", e, button, cell);
}

function release(e, cell) {
    send_mouse("mouse release", e, pressed_button, cell);
    pressed_button = null;
    pressed_pointer = null;
}

// With several buttons held, the browser reports each one released before the last as a pointermove,
// and only the last one as a pointerup, so both check whether the pressed button is still held.
function on_pointermove(e) {
    if (pressed_button === null || e.pointerId !== pressed_pointer) {
        return;
    }
    const cell = clamp_cell(mouse_cell(e));
    if ((e.buttons & pressed_bit) === 0) {
        release(e, cell);
        return;
    }
    if (cell[0] === last_cell[0] && cell[1] === last_cell[1]) {
        return;
    }
    last_cell = cell;
    send_mouse("mouse drag", e, pressed_button, cell);
}

function on_pointerup(e) {
    if (pressed_button === null || e.pointerId !== pressed_pointer || (e.buttons & pressed_bit) !== 0) {
        return;
    }
    e.preventDefault();
    release(e, clamp_cell(mouse_cell(e)));
}

// The browser took the pointer away, for example for a touch gesture, without a pointerup;
// the application still gets the release.
function on_pointercancel(e) {
    if (pressed_button === null || e.pointerId !== pressed_pointer) {
        return;
    }
    release(e, last_cell);
}

// Add a wheel distance to the one not sent yet, and return the remainder and the direction of a step,
// -1, 0 or 1. A large distance, such as a mouse notch, is one step, as a terminal reports one notch.
function wheel_step(pending, delta, step) {
    // a turn the other way drops the distance left from the last one
    const total = Math.sign(pending) === -Math.sign(delta) ? delta : pending + delta;
    if (Math.abs(total) < step) {
        return [total, 0];
    }
    return [total % step, Math.sign(total)];
}

function on_wheel(e) {
    const cell = mouse_cell(e);
    // the wheel turned with ctrl held is left to the browser, which zooms the page with it
    if (socket === null || e.ctrlKey || !inside_screen(cell)) {
        return;
    }
    e.preventDefault();
    const line = char_size()[1];
    // WheelEvent.deltaMode: 0 is pixels, 1 is lines, 2 is pages
    const scale = [1, line, line * screen_y][e.deltaMode] || 1;
    let up_down;
    let left_right;
    [wheel_y, up_down] = wheel_step(wheel_y, e.deltaY * scale, wheel_lines * line);
    [wheel_x, left_right] = wheel_step(wheel_x, e.deltaX * scale, wheel_lines * line);
    if (up_down !== 0) {
        send_mouse("mouse press", e, up_down < 0 ? 4 : 5, cell);
    }
    if (left_right !== 0) {
        send_mouse("mouse press", e, left_right < 0 ? 6 : 7, cell);
    }
}

// force sends the size even when it did not change, for the server's first view of it
function on_resize(force) {
    // the screen uses at most this size, so the text area is not wider or taller and takes no mouse input beyond it;
    // a page without the attributes, such as one an adapter writes itself, has no limit
    const limits = document.body.dataset;
    const max_cols = Number(limits.maxCols) || Infinity;
    const max_rows = Number(limits.maxRows) || Infinity;
    // the measured size is a quotient of floats, and not a number before the fonts are laid out
    const [x_size, y_size] = measure_screen(max_cols, max_rows).map(Math.floor);
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

    const text = document.getElementById('text');
    text.addEventListener("pointerdown", on_pointerdown);
    text.addEventListener("pointermove", on_pointermove);
    text.addEventListener("pointerup", on_pointerup);
    text.addEventListener("pointercancel", on_pointercancel);
    text.addEventListener("lostpointercapture", on_pointercancel);
    // not passive, so the page does not scroll while the application takes the wheel
    text.addEventListener("wheel", on_wheel, {passive: false});
    // the right button goes to the application rather than opening the browser's menu
    text.addEventListener("contextmenu", (e) => e.preventDefault());
    setInterval(on_resize, check_font_delay);
}

start();
