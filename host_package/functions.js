// S1 Full Control — in-host helpers (Studio One 6 Host API)

function alert(v) { Host.GUI.alert(String(v)); }
function print(v) { Host.Console.writeLine(String(v)); }

function getTracks(selectedOnly) {
    var list = Host.Objects.getObjectByUrl(
        "://hostapp/DocumentManager/ActiveDocument/TrackList"
    ).mainTrackList;
    var out = [];
    if (selectedOnly) {
        for (var i = 0; i < list.numSelectedTracks; i++)
            out.push(list.getSelectedTrack(i));
    } else {
        for (var i = 0; i < list.numTracks; i++)
            out.push(list.getTrack(i));
    }
    return out;
}

function getChannels(selectedOnly) {
    var console = Host.Objects.getObjectByUrl(
        "://hostapp/DocumentManager/ActiveDocument/Environment/MixerConsole"
    );
    var list = console.getChannelList(1);
    var out = [];
    if (selectedOnly) {
        for (var i = 0; i < list.numSelectedChannels; i++)
            out.push(list.getSelectedChannel(i));
    } else {
        for (var i = 0; i < list.numChannels; i++)
            out.push(list.getChannel(i));
    }
    return out;
}

function setFader(channel, db) {
    if (!channel || channel.findParameter("volume") == undefined) return false;
    var linear = Math.pow(10, parseFloat(db) / 20);
    channel.findParameter("volume").setValue(linear, true);
    return true;
}

function setMute(channel, state) {
    try {
        channel.mute = state ? 1 : 0;
        return true;
    } catch (e) {
        return false;
    }
}

function setSolo(channel, state) {
    try {
        channel.solo = state ? 1 : 0;
        return true;
    } catch (e) {
        return false;
    }
}

function setPan(channel, pan01) {
    try {
        if (channel.pan != undefined) {
            channel.pan = pan01;
            return true;
        }
    } catch (e) {}
    return false;
}

function interpret(category, name) {
    try {
        return Host.GUI.Commands.interpretCommand(category, name, false);
    } catch (e) {
        print("interpret fail " + category + "/" + name + ": " + e);
        return false;
    }
}

// Queue path: user Documents/Studio One/S1FullControl/queue.json
function queuePath() {
    // Host.IO may resolve user documents
    try {
        var folder = Host.IO.createFileObject(
            Host.IO.Paths.kUserDocuments + "/Studio One/S1FullControl"
        );
        return folder;
    } catch (e) {
        return null;
    }
}
