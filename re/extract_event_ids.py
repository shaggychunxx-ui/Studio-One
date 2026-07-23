from pathlib import Path
import re

data = Path("ucremote_libs/lib_arm64-v8a_libucnet.so").read_bytes().decode("latin1")
seen = {}
for m in re.finditer(r"([A-Za-z][A-Za-z0-9_]{2,60}Event)ELi(\d+)", data):
    name, num = m.group(1), int(m.group(2))
    seen[num] = name
for num in sorted(seen):
    be = num.to_bytes(2, "big")
    print(f"{num:5d} 0x{num:04X} {seen[num]:30s} BE={be!r}")
