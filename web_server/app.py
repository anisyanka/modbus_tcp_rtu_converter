#!/usr/bin/env python
import os
import sys
from flask import Flask, render_template, request, json, jsonify
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from microscope_modbus import ModbusMicroscope
import helpers as helper
import stream_control as stream
import config_reader as conf_reader
import signal

# Ignore SIGCHLD to avoid zombi-proccesses
signal.signal(signal.SIGCHLD, signal.SIG_IGN)

# Obtain all initial config data. MUST be call first
conf_reader.read_all_configs()

# Modbus class
microscope_mb = ModbusMicroscope()

# Modbus library debug mode enabled?
if conf_reader.is_modbus_debug_enabled() == "On":
    print("Modbus lib debug mode ENABLED")
    microscope_mb.debug_mode(True)
else:
    microscope_mb.debug_mode(False)
    print("Modbus lib debug mode DISABLED")

# Temp file to save one frame
if not os.path.exists(stream.get_img_path()):
    with open(stream.get_img_path(), 'w'):
        pass

# Disable previously enabled settings
stream.stop_stream()
stream.set_resolution("1080p")

# Run server
app = Flask(__name__)

allow_to_chang_res = 0
video_control_req = 0
is_video_stream_started = 0

# Load main page #
##################
@app.route("/", methods=["GET"])
def index():
    global video_control_req
    global is_video_stream_started

    conf_reader.read_all_configs()

    print("Board ip=" + helper.get_my_ip())
    print("Client ip=" + request.remote_addr)

    helper.update_host_ip_config(request.remote_addr)

    if is_video_stream_started == 1:
        is_video_stream_started = 0
        video_control_req = 1 # Wait for sending frame will be finished
        while allow_to_chang_res == 0:
            pass
        stream.stop_stream()
        video_control_req = 0 # Start sending frames again

    return render_template('index.html')


# AJAX: Handle video buttons #
##############################
@app.route("/video_control", methods=["GET", "POST"])
def resolution_switch_request():
    print("Obtained request to change stream resolution to " + request.args.get("new_res"))

    # Wait for sending frame will be finished
    global video_control_req
    video_control_req = 1
    while allow_to_chang_res == 0:
        pass

    stream.stop_stream()
    stream.set_resolution(request.args.get("new_res"))

    # Start sending frames again
    video_control_req = 0

    return jsonify("OK")


# STREAM: send jpeg frame #
###########################
def get_camera_frame():
    global allow_to_chang_res
    while True:
        if video_control_req == 0:
            allow_to_chang_res = 0
            yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + b'\r\n')
        else:
            allow_to_chang_res = 1
            if is_video_stream_started == 0:
                print("STOP VIDEO STREAM")
                break

@app.route('/video_feed')
def video_feed():
    # global is_video_stream_started
    # is_video_stream_started = 1

    print("START VIDEO STREAM")
    # return Response(get_camera_frame(), mimetype='multipart/x-mixed-replace; boundary=frame')
    return "OK"


# AJAX: Focus change via Modbus #
#################################
@app.route("/focus_control", methods=["GET", "POST"])
def focus_control_request():
    print("Obtained request to focus " + request.args.get("sign"))

    # Call Modbus TCP/RTU converter to send focus cmd and wait for reply
    microscope_mb.focus_motor_control(request.args.get("sign"))

    return jsonify("OK")


# AJAX: Light control via Modbus #
##################################
@app.route("/light_control", methods=["GET", "POST"])
def light_control_request():
    print("Obtained request to make light " + request.args.get("level"))

    # Call Modbus TCP/RTU converter to send light cmd and wait for reply
    microscope_mb.light_control(request.args.get("level"))

    return jsonify("OK")


# AJAX: up/left/right/down + WORK/STOP/HOME control via Modbus #
###########################################################
@app.route("/motor_control", methods=["GET", "POST"])
def motor_control_request():
    print("Obtained request to move motors to " + request.args.get("position"))

    # Call Modbus TCP/RTU converter to send position cmd and wait for reply
    microscope_mb.main_motors_control(request.args.get("position"))
    return jsonify("OK")


# AJAX: Get battery level via Modbus #
######################################
@app.route("/get_battery_level", methods=["GET", "POST"])
def get_battery_level_request():
    print("Obtained request to retrieve battery level")

    # Call Modbus TCP/RTU converter and wait for reply
    level = microscope_mb.get_bat_level()
    return jsonify({ "level": level })


# AJAX: Get config #
####################
@app.route("/get_conf", methods=["GET", "POST"])
def send_config_data_to_client():
    soc_pol_time = conf_reader.get_soc_polling_period_ms()
    repeat_cmds = conf_reader.get_repeat_cmd_perid_ms()
    initial_bat_level = microscope_mb.get_bat_level()

    return jsonify({ "modbus_soc_polling_period_ms":  soc_pol_time,
                     "modbus_repeat_cmd_period_ms": repeat_cmds,
                      "initial_bat_level": initial_bat_level })


@app.errorhandler(HTTPException)
def handle_exception(e):
    """Return JSON instead of HTML for HTTP errors."""
    # start with the correct headers and status code from the error
    response = e.get_response()
    # replace the body with JSON
    response.data = json.dumps({
        "code": e.code,
        "name": e.name,
        "description": e.description,
    })
    response.content_type = "application/json"
    return response