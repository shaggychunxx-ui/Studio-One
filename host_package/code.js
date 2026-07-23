include_file("functions.js");

// ---- Process external queue written by s1-remote Python ----
function ProcessQueueTask() {
    this.interfaces = [Host.Interfaces.IEditTask];
    this.prepareEdit = function () { return Host.Results.kResultOk; };
    this.performEdit = function () {
        var results = [];
        var path = Host.IO.Paths.kUserDocuments + "/Studio One/S1FullControl/queue.json";
        var resultPath = Host.IO.Paths.kUserDocuments + "/Studio One/S1FullControl/result.json";
        try {
            var f = Host.IO.openTextFile(path);
            if (!f) {
                alert("No queue at:\n" + path + "\nRun s1remote full enqueue first.");
                return Host.Results.kResultOk;
            }
            var text = f.read();
            f.close();
            var queue = JSON.parse(text);
            if (!(queue instanceof Array)) queue = [];

            for (var i = 0; i < queue.length; i++) {
                var item = queue[i];
                var r = runTask(item.task, item.params || {});
                results.push({ id: item.id, task: item.task, ok: r.ok, detail: r.detail });
            }

            // clear queue
            var outQ = Host.IO.createTextFile(path);
            if (outQ) { outQ.write("[]"); outQ.close(); }

            var outR = Host.IO.createTextFile(resultPath);
            if (outR) { outR.write(JSON.stringify(results)); outR.close(); }

            print("S1 Full Control: processed " + results.length + " task(s)");
            alert("S1 Full Control processed " + results.length + " task(s). See Console.");
        } catch (e) {
            alert("Process Queue error: " + e);
        }
        return Host.Results.kResultOk;
    };
}
function createProcessQueue() { return new ProcessQueueTask(); }

function runTask(task, params) {
    try {
        if (task == "mute_selected") {
            var tracks = getTracks(1);
            for (var i = 0; i < tracks.length; i++) {
                if (tracks[i].channel) tracks[i].channel.mute = 1;
            }
            return { ok: true, detail: "muted " + tracks.length };
        }
        if (task == "solo_selected") {
            var tracks = getTracks(1);
            for (var i = 0; i < tracks.length; i++) {
                if (tracks[i].channel) tracks[i].channel.solo = 1;
            }
            return { ok: true, detail: "solo " + tracks.length };
        }
        if (task == "unmute_all") {
            var tracks = getTracks(0);
            for (var i = 0; i < tracks.length; i++) {
                if (tracks[i].channel) tracks[i].channel.mute = 0;
            }
            return { ok: true, detail: "unmuted " + tracks.length };
        }
        if (task == "faders_minus6") {
            var chs = getChannels(1);
            if (chs.length == 0) {
                var tr = getTracks(1);
                for (var i = 0; i < tr.length; i++)
                    if (tr[i].channel) setFader(tr[i].channel, -6);
                return { ok: true, detail: "faders via tracks" };
            }
            for (var j = 0; j < chs.length; j++) setFader(chs[j], -6);
            return { ok: true, detail: "faders " + chs.length };
        }
        if (task == "list_tracks") {
            var tracks = getTracks(0);
            print("=== Tracks (" + tracks.length + ") ===");
            for (var i = 0; i < tracks.length; i++) {
                var n = tracks[i].name != undefined ? tracks[i].name : "?";
                print(i + ": " + n);
            }
            return { ok: true, detail: String(tracks.length) };
        }
        if (task == "set_channel_volume") {
            var idx = parseInt(params.index || 0);
            var db = parseFloat(params.db != undefined ? params.db : -6);
            var chs = getChannels(0);
            if (idx < 0 || idx >= chs.length)
                return { ok: false, detail: "index out of range " + idx + "/" + chs.length };
            setFader(chs[idx], db);
            return { ok: true, detail: "ch" + idx + "=" + db + "dB" };
        }
        if (task == "set_channel_mute") {
            var idx = parseInt(params.index || 0);
            var state = params.state ? 1 : 0;
            var chs = getChannels(0);
            if (idx < 0 || idx >= chs.length)
                return { ok: false, detail: "bad index" };
            setMute(chs[idx], state);
            return { ok: true, detail: "mute ch" + idx + "=" + state };
        }
        if (task == "set_channel_pan") {
            var idx = parseInt(params.index || 0);
            var pan = parseFloat(params.pan != undefined ? params.pan : 0.5);
            var chs = getChannels(0);
            if (idx < 0 || idx >= chs.length)
                return { ok: false, detail: "bad index" };
            setPan(chs[idx], pan);
            return { ok: true, detail: "pan ch" + idx };
        }
        if (task == "interpret_command") {
            var cat = String(params.category || "");
            var name = String(params.name || "");
            var ok = interpret(cat, name);
            return { ok: !!ok, detail: cat + "/" + name };
        }
        if (task == "dump_channels") {
            var chs = getChannels(0);
            print("=== Channels (" + chs.length + ") ===");
            for (var i = 0; i < chs.length; i++) {
                var c = chs[i];
                var nm = c.name != undefined ? c.name : ("ch" + i);
                print(i + ": " + nm);
            }
            return { ok: true, detail: String(chs.length) };
        }
        return { ok: false, detail: "unknown task " + task };
    } catch (e) {
        return { ok: false, detail: String(e) };
    }
}

// ---- One-shot macros (also in Scripts menu) ----
function MuteSelectedTask() {
    this.interfaces = [Host.Interfaces.IEditTask];
    this.prepareEdit = function () { return Host.Results.kResultOk; };
    this.performEdit = function () {
        runTask("mute_selected", {});
        return Host.Results.kResultOk;
    };
}
function createMuteSelected() { return new MuteSelectedTask(); }

function UnmuteAllTask() {
    this.interfaces = [Host.Interfaces.IEditTask];
    this.prepareEdit = function () { return Host.Results.kResultOk; };
    this.performEdit = function () {
        runTask("unmute_all", {});
        return Host.Results.kResultOk;
    };
}
function createUnmuteAll() { return new UnmuteAllTask(); }

function ListTracksTask() {
    this.interfaces = [Host.Interfaces.IEditTask];
    this.prepareEdit = function () { return Host.Results.kResultOk; };
    this.performEdit = function () {
        runTask("list_tracks", {});
        alert("Listed tracks in Console (View messages).");
        return Host.Results.kResultOk;
    };
}
function createListTracks() { return new ListTracksTask(); }

function DumpChannelsTask() {
    this.interfaces = [Host.Interfaces.IEditTask];
    this.prepareEdit = function () { return Host.Results.kResultOk; };
    this.performEdit = function () {
        runTask("dump_channels", {});
        alert("Dumped channels to Console.");
        return Host.Results.kResultOk;
    };
}
function createDumpChannels() { return new DumpChannelsTask(); }
