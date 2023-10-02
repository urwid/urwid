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

colours = new Object();
colours = {
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

keycodes = new Object();
keycodes = {
    8: "backspace", 9: "tab", 13: "enter", 27: "esc",
    33: "page up", 34: "page down", 35: "end", 36: "home",
    37: "left", 38: "up", 39: "right", 40: "down",
    45: "insert", 46: "delete",
    112: "f1", 113: "f2", 114: "f3", 115: "f4",
    116: "f5", 117: "f6", 118: "f7", 119: "f8",
    120: "f9", 121: "f10", 122: "f11", 123: "f12"
    };

var conn = null;
var char_width = null;
var char_height = null;
var screen_x = null;
var screen_y = null;

var urwid_id = null;
var send_conn = null;
var send_queue_max = 32;
var send_queue = new Array(send_queue_max);
var send_queue_in = 0;
var send_queue_out = 0;

var check_font_delay = 1000;
var send_more_delay = 100;
var poll_again_delay = 500;

var document_location = null;

var update_method = "multipart";

var sending = false;
var lastkeydown = null;

function setup_connection() {
    if (window.XMLHttpRequest) {
        conn = new XMLHttpRequest();
    } else if (window.ActiveXObject) {
        conn = new ActiveXObject("Microsoft.XMLHTTP");
    }

    if (conn == null) {
        set_status("Connection Failed");
        alert( "Can't figure out how to send request." );
        return;
    }
    try{
        conn.multipart = true;
    }catch(e){
        update_method = "polling";
    }
    conn.onreadystatechange = handle_recv;
    conn.open("POST", document_location, true);
    conn.setRequestHeader("X-Urwid-Method",update_method);
    conn.setRequestHeader("Content-type","text/plain");
    conn.send("window resize " +screen_x+" "+screen_y+"\n");
}

function do_poll() {
    if (urwid_id == null){
        alert("that's unpossible!");
        return;
    }
    if (window.XMLHttpRequest) {
        conn = new XMLHttpRequest();
    } else if (window.ActiveXObject) {
        conn = new ActiveXObject("Microsoft.XMLHTTP");
    }
    conn.onreadystatechange = handle_recv;
    conn.open("POST", document_location, true);
    conn.setRequestHeader("X-Urwid-Method","polling");
    conn.setRequestHeader("X-Urwid-ID",urwid_id);
    conn.setRequestHeader("Content-type","text/plain");
    conn.send("eh?");
}

function handle_recv() {
    if( ! conn ){ return;}
    if( conn.readyState != 4) {
        return;
    }
    if( conn.status == 404 && urwid_id != null) {
        set_status("Connection Closed");
        return;
    }
    if( conn.status == 403 && update_method == "polling" ) {
        set_status("Server Refused Connection");
        alert("This server does not allow polling clients.\n\n" +
            "Please use a web browser with multipart support " +
            "such as Mozilla Firefox");
        return;
    }
    if( conn.status == 503 ) {
        set_status("Connection Failed");
        alert("The server has reached its maximum number of "+
            "connections.\n\nPlease try again later.");
        return;
    }
    if( conn.status != 200) {
        set_status("Connection Failed");
        alert("Error from server: "+conn.statusText);
        return;
    }
    if( urwid_id == null ){
        urwid_id = conn.getResponseHeader("X-Urwid-ID");
        if( send_queue_in != send_queue_out ){
            // keys waiting
            do_send();
        }
        if(update_method=="polling"){
            set_status("Polling");
        }else if(update_method=="multipart"){
            set_status("Connected");
        }

    }

    if( conn.responseText == "" ){
        if(update_method=="polling"){
            poll_again();
        }
        return; // keepalive
    }
    if( conn.responseText == "Z" ){
        set_status("Connection Closed");
        update_method = null;
        return;
    }

    var text = document.getElementById('text');

    var last_screen = Array(text.childNodes.length);
    for( var i=0; i<text.childNodes.length; i++ ){
        last_screen[i] = text.childNodes[i];
    }

    var frags = conn.responseText.split("\n");
    var ln = document.createElement('span');
    var k = 0;
    for( var i=0; i<frags.length; i++ ){
        var f = frags[i];
        if( f == "" ){
            var br = document.getElementById('br').cloneNode(true);
            ln.appendChild( br );
            if( text.childNodes.length > k ){
                text.replaceChild(ln, text.childNodes[k]);
            }else{
                text.appendChild(ln);
            }
            k = k+1;
            ln = document.createElement('span');
        }else if( f.charAt(0) == "<" ){
            line_number = parseInt(f.substr(1));
            if( line_number == k ){
                k = k +1;
                continue;
            }
            var clone = last_screen[line_number].cloneNode(true);
            if( text.childNodes.length > k ){
                text.replaceChild(clone, text.childNodes[k]);
            }else{
                text.appendChild(clone);
            }
            k = k+1;
        }else{
            var span=make_span(f.substr(2),f.charAt(0),f.charAt(1));
            ln.appendChild( span );
        }
    }
    for( var i=k; i < text.childNodes.length; i++ ){
        text.removeChild(last_screen[i]);
    }

    if(update_method=="polling"){
        poll_again();
    }
}

function poll_again(){
    if(conn.status == 200){
        setTimeout("do_poll();",poll_again_delay);
    }
}


function load_web_display(){
    if( document.documentURI ){
        document_location = document.documentURI;
    }else{
        document_location = document.location;
    }

    document.onkeypress = body_keypress;
    document.onkeydown = body_keydown;
    document.onresize = body_resize;

    body_resize();
    send_queue_out = send_queue_in; // don't queue the first resize

    set_status("Connecting");
    setup_connection();

    setTimeout("check_fontsize();",check_font_delay);
}

function set_status( status ){
    var s = document.getElementById('status');
    var t = document.createTextNode(status);
    s.replaceChild(t, s.firstChild);
}

function make_span(s, fg, bg){
    d = document.createElement('span');
    d.style.backgroundColor = colours[bg];
    d.style.color = colours[fg];
    d.appendChild(document.createTextNode(s));

    return d;
}

function body_keydown(e){
    if (conn == null){
        return;
    }
    if (!e) var e = window.event;
    if (e.keyCode) code = e.keyCode;
    else if (e.which) code = e.which;

    var mod = "";
    var key;

    if( e.ctrlKey ){ mod = "ctrl " + mod; }
    if( e.altKey || e.metaKey ){ mod = "meta " + mod; }
    if( e.shiftKey && e.charCode == 0 ){ mod = "shift " + mod; }

    key = keycodes[code];

    if( key != undefined ){
        lastkeydown = key;
        send_key( mod + key );
        stop_key_event(e);
        return false;
    }
}

function body_keypress(e){
    if (conn == null){
        return;
    }

    if (!e) var e = window.event;
    if (e.keyCode) code = e.keyCode;
    else if (e.which) code = e.which;

    var mod = "";
    var key;

    if( e.ctrlKey ){ mod = "ctrl " + mod; }
    if( e.altKey || e.metaKey ){ mod = "meta " + mod; }
    if( e.shiftKey && e.charCode == 0 ){ mod = "shift " + mod; }

    if( e.charCode != null && e.charCode != 0 ){
        key = String.fromCharCode(e.charCode);
    }else if( e.charCode == null ){
        key = String.fromCharCode(code);
    }else{
        key = keycodes[code];
        if( key == undefined || lastkeydown == key ){
            lastkeydown = null;
            stop_key_event(e);
            return false;
        }
    }

    send_key( mod + key );
    stop_key_event(e);
    return false;
}

function stop_key_event(e){
    e.cancelBubble = true;
    if( e.stopPropagation ){
        e.stopPropagation();
    }
    if( e.preventDefault  ){
        e.preventDefault();
    }
}

function send_key( key ){
    if( (send_queue_in+1)%send_queue_max == send_queue_out ){
        // buffer overrun
        return;
    }
    send_queue[send_queue_in] = key;
    send_queue_in = (send_queue_in+1)%send_queue_max;

    if( urwid_id != null ){
        if (send_conn == undefined || send_conn.ready_state != 4 ){
            send_more();
            return;
        }
        do_send();
    }
}

function do_send() {
    if( ! urwid_id ){ return; }
    if( ! update_method ){ return; } // connection closed
    if( send_queue_in == send_queue_out ){ return; }
    if( sending ){
        //var queue_delta = send_queue_in - send_queue_out;
        //if( queue_delta < 0 ){ queue_delta += send_queue_max; }
        //set_status("Sending (queued "+queue_delta+")");
        return;
    }
    try{
        sending = true;
        //set_status("starting send");
        if( send_conn == null ){
            if (window.XMLHttpRequest) {
                send_conn = new XMLHttpRequest();
            } else if (window.ActiveXObject) {
                send_conn = new ActiveXObject("Microsoft.XMLHTTP");
            }
        }else if( send_conn.status != 200) {
            alert("Error from server: "+send_conn.statusText);
            return;
        }else if(send_conn.readyState != 4 ){
            alert("not ready on send connection");
            return;
        }
    } catch(e) {
        alert(e);
        sending = false;
        return;
    }
    send_conn.open("POST", document_location, true);
    send_conn.onreadystatechange = send_handle_recv;
    send_conn.setRequestHeader("Content-type","text/plain");
    send_conn.setRequestHeader("X-Urwid-ID",urwid_id);
    var tmp_send_queue_in = send_queue_in;
    var out = null;
    if( send_queue_out > tmp_send_queue_in ){
        out = send_queue.slice(send_queue_out).join("\n")
        if( tmp_send_queue_in > 0 ){
            out += "\n"  + send_queue.slice(0,tmp_send_queue_in).join("\n");
        }
    }else{
        out = send_queue.slice(send_queue_out,
             tmp_send_queue_in).join("\n");
    }
    send_queue_out = tmp_send_queue_in;
    //set_status("Sending");
    send_conn.send( out +"\n" );
}

function send_handle_recv() {
    if( send_conn.readyState != 4) {
        return;
    }
    if( send_conn.status == 404) {
        set_status("Connection Closed");
        update_method = null;
        return;
    }
    if( send_conn.status != 200) {
        alert("Error from server: "+send_conn.statusText);
        return;
    }

    sending = false;

    if( send_queue_out != send_queue_in ){
        send_more();
    }
}

function send_more(){
    setTimeout("do_send();",send_more_delay);
}

function check_fontsize(){
    body_resize()
    setTimeout("check_fontsize();",check_font_delay);
}

function body_resize(){
    var t = document.getElementById('testchar');
    var t2 = document.getElementById('testchar2');
    var text = document.getElementById('text');

    var window_width;
    var window_height;
    if (window.innerHeight) {
        window_width = window.innerWidth;
        window_height = window.innerHeight;
    }else{
        window_width = document.documentElement.clientWidth;
        window_height = document.documentElement.clientHeight;
        //var z = "CI:"; for(var i in bod){z = z + " " + i;} alert(z);
    }

    char_width = t.offsetLeft / 44;
    var avail_width = window_width-18;
    var avail_width_mod = avail_width % char_width;
    var x_size = (avail_width - avail_width_mod)/char_width;

    char_height = t2.offsetTop - t.offsetTop;
    var avail_height = window_height-text.offsetTop-10;
    var avail_height_mod = avail_height % char_height;
    var y_size = (avail_height - avail_height_mod)/char_height;

    text.style.width = x_size*char_width+"px";
    text.style.height = y_size*char_height+"px";

    if( screen_x != x_size || screen_y != y_size ){
        send_key("window resize "+x_size+" "+y_size);
    }
    screen_x = x_size;
    screen_y = y_size;
}
