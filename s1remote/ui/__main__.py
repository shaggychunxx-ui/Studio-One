"""python -m s1remote.ui inspect"""

from ..cli import main

if __name__ == "__main__":
    raise SystemExit(main(["ui", *(__import__("sys").argv[1:] or ["inspect"])]))
