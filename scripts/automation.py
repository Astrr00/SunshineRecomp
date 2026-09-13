"""Send one runtime automation command atomically and check its acknowledgement."""
import argparse
from pathlib import Path
import time
import uuid


def read_status(root, timeout=2):
    """Retry transient Windows sharing errors and incomplete status rewrites."""
    path = Path(root).resolve() / "status.txt"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            fields = dict(line.split("=", 1) for line in
                          path.read_text(encoding="utf-8").splitlines() if "=" in line)
            if {"state", "frame_count", "last_error"} <= fields.keys():
                return fields
        except OSError:
            pass
        time.sleep(0.01)
    raise TimeoutError(f"No complete readable status: {path}")


def send(root, command, fields, timeout=30):
    root = Path(root).resolve()
    if not (root / "commands").is_dir():
        raise RuntimeError(f"Runtime command directory missing: {root}")
    values = dict(field.split("=", 1) for field in fields)
    if command in ("pad", "pad_frames", "clear_pad"):
        values.setdefault("port", "0")
    name = f"{time.time_ns()}-{uuid.uuid4().hex[:8]}.txt"
    staging = root / (name + ".tmp")
    staging.write_text("\n".join([f"command={command}"] +
                                [f"{k}={v}" for k, v in values.items()]) + "\n",
                       encoding="utf-8")
    staging.replace(root / "commands" / name)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if (root / "failed" / name).exists():
            raise RuntimeError(f"Command rejected: {name}\n" +
                               str(read_status(root)))
        if (root / "processed" / name).exists():
            return name
        time.sleep(0.05)
    raise TimeoutError(f"No acknowledgement for {name}; command may still be pending")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("command")
    parser.add_argument("fields", nargs="*")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    print(send(args.root, args.command, args.fields, args.timeout))
