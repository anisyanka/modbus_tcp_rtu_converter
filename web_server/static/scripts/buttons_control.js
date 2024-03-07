var interval_id = 0;
var timeout_id = 0;
var was_btn_released = 0;
var new_req_started = 0;
var polling_time_ms = 0;

function button_control_set_poll_time(poltime) {
    polling_time_ms = poltime;
}

function button_control_pressed(req, variable, value) {
    was_btn_released = 0;

    if (timeout_id == 0) {
        timeout_id = setTimeout(function() {button_control_check_was_release(req, variable, value);}, 400);
    }
}

function button_control_released(req, variable, value) {
    was_btn_released = 1;
    button_control_stop(req, variable, value);
    clearTimeout(timeout_id);
    timeout_id = 0;
}

function button_control_check_was_release(req, variable, value) {
    if (was_btn_released == 0) { /* the user is still pressing the button */
        button_control_change_repeatedly(req, variable, value);
    }
    timeout_id = 0;
}

function button_control(req, variable, value, is_retention) {
    var request = new XMLHttpRequest();

    request.onload = function() {
        if (request.response == "OK") {
            console.log("Request <" + req + "> OK! Parameter <" + variable + "> became " + value + "; retention=" + is_retention);
        } else {
            console.log("[ERR] HTTP request answer internal server error");
        }
        new_req_started = 0;
    }

    // Send a request
    if (new_req_started == 0) {
        request.responseType = 'json';
        request.open("GET", "/" + req + "?" + variable + "=" + value + "&retention=" + is_retention, true);
        request.send();
        new_req_started = 1;
    }
}

function button_control_change_repeatedly(req, variable, value) {
    if (interval_id == 0) {
        if (polling_time_ms <= 0) {
            interval_id = window.setInterval(function() {button_control(req, variable, value, "yes");}, 200);
        } else {
            interval_id = window.setInterval(function() {button_control(req, variable, value, "yes");}, polling_time_ms);
        }
        console.log("Repeat proccess started");
    }
}

function button_control_stop(req, variable, value) {
    was_btn_released = 1;

    if (interval_id) {
        clearInterval(interval_id);
        interval_id = 0;
        console.log("Repeat proccess stoped");
        setTimeout(function() { new_req_started = 0; button_control(req, variable, value, "released"); }, 150);
    }
}
