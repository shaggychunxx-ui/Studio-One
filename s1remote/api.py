"""Minimal HTTP API for Stream Deck / scripts / other apps."""

from __future__ import annotations

from flask import Flask, jsonify, request

from .controller import S1Remote


def create_app(remote: S1Remote) -> Flask:
    app = Flask("s1-remote")

    @app.get("/health")
    def health():
        return jsonify(remote.status())

    @app.get("/ports")
    def ports():
        from .midi.port import list_ports

        return jsonify(list_ports())

    @app.post("/connect")
    def connect():
        body = request.get_json(silent=True) or {}
        remote.connect(body.get("out"), body.get("in"))
        return jsonify({"ok": True, "status": remote.status()})

    @app.post("/transport/<cmd>")
    def transport(cmd: str):
        cmd = cmd.lower()
        fn = {
            "play": remote.play,
            "stop": remote.stop,
            "record": remote.record,
            "rewind": remote.mcu.rewind,
            "ffwd": remote.mcu.ffwd,
            "cycle": remote.mcu.cycle,
            "click": remote.mcu.click_metronome,
        }.get(cmd)
        if not fn:
            return jsonify({"error": f"unknown transport cmd {cmd}"}), 400
        if not remote.connected:
            return jsonify({"error": "MIDI not connected"}), 400
        fn()
        return jsonify({"ok": True, "cmd": cmd})

    @app.post("/mixer/fader")
    def mixer_fader():
        body = request.get_json(force=True)
        ch = int(body["channel"])
        if "db" in body:
            remote.mcu.fader(ch, db=float(body["db"]))
        else:
            remote.mcu.fader(ch, norm=float(body.get("norm", 0.75)))
        return jsonify({"ok": True})

    @app.post("/mixer/mute")
    def mixer_mute():
        body = request.get_json(force=True)
        remote.mute(int(body["channel"]))
        return jsonify({"ok": True})

    @app.post("/mixer/solo")
    def mixer_solo():
        body = request.get_json(force=True)
        remote.solo(int(body["channel"]))
        return jsonify({"ok": True})

    @app.post("/mixer/select")
    def mixer_select():
        body = request.get_json(force=True)
        remote.mcu.select(int(body["channel"]))
        return jsonify({"ok": True})

    @app.post("/mixer/bank")
    def mixer_bank():
        body = request.get_json(force=True)
        direction = body.get("direction", "right")
        if direction == "left":
            remote.mcu.bank_left()
        else:
            remote.mcu.bank_right()
        return jsonify({"ok": True})

    @app.post("/plugin/cc")
    def plugin_cc():
        body = request.get_json(force=True)
        remote.plugin_cc(int(body["control"]), int(body["value"]), int(body.get("channel", 0)))
        return jsonify({"ok": True})

    @app.post("/plugin/param")
    def plugin_param():
        body = request.get_json(force=True)
        remote.plugin_param(body["plugin"], body["param"], body["value"])
        return jsonify({"ok": True})

    @app.post("/plugin/mode")
    def plugin_mode():
        """Switch MCU V-Pots into Control Link plug-in mode."""
        remote.mcu.mode_plugin()
        return jsonify({"ok": True})

    @app.post("/midi/note")
    def midi_note():
        body = request.get_json(force=True)
        remote.note(
            int(body["note"]),
            float(body.get("duration", 0.25)),
            int(body.get("velocity", 100)),
            int(body.get("channel", 0)),
        )
        return jsonify({"ok": True})

    @app.post("/hotkey/<action>")
    def hotkey(action: str):
        remote.hotkey(action)
        return jsonify({"ok": True, "action": action})

    @app.post("/mcu/<name>")
    def mcu_click(name: str):
        remote.mcu.click(name)
        return jsonify({"ok": True, "button": name})

    return app


def run_server(remote: S1Remote, host: str = "127.0.0.1", port: int = 8765) -> None:
    app = create_app(remote)
    app.run(host=host, port=port, threaded=True)
