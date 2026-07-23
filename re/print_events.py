from s1remote.ucnet.events import EventType

for e in EventType:
    tag = int(e).to_bytes(2, "big")
    print(f"{e.name:20s} 0x{int(e):04X} {tag!r}")
