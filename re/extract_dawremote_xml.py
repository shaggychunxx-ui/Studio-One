from __future__ import annotations

import re
from pathlib import Path

DLL = Path(r"C:\Program Files\PreSonus\Studio One 6\Plugins\remoteservice.dll")
OUT = Path(__file__).parent / "extracted"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    text = DLL.read_bytes().decode("latin1")
    # Templates
    for m in re.finditer(r'<uc:Template id="([^"]+)"[\s\S]{0,80000}?</uc:Template>', text):
        tid = m.group(1)
        path = OUT / f"template_{tid}.xml"
        path.write_text(m.group(0), encoding="utf-8", errors="replace")
        print("template", tid, "len", len(m.group(0)), "->", path.name)

    for pid in ("Transport", "Session", "ShowTransport", "StreamingTransport", "RemoteFXSlot", "RemoteFXFolder"):
        m = re.search(rf'<uc:ParamList id="{pid}"[\s\S]{{0,50000}}?</uc:ParamList>', text)
        if m:
            path = OUT / f"paramlist_{pid}.xml"
            path.write_text(m.group(0), encoding="utf-8", errors="replace")
            print("paramlist", pid, "len", len(m.group(0)))

    # Network-related strings
    for pat in [
        r"networkServerEnabled",
        r"device/remotedev[^\x00]{0,80}",
        r"remotedevice[^\x00]{0,80}",
        r"UCXML[^\x00]{0,40}",
        r"UserService[^\x00]{0,40}",
        r"allow_remote[^\x00]{0,40}",
        r"DAW controls available[^\x00]{0,120}",
    ]:
        for m in re.finditer(pat, text, re.I):
            print("STR", repr(m.group(0)[:100]))


if __name__ == "__main__":
    main()
