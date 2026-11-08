"""Small genuine installed-binary gate, not a full scientific/native qualification.

Called only on a native OS after installing OUTSIDE the checkout. A Python
interpreter is required for this *test harness*, never by the installed app.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

MODES = (
    "train-dataset-build", "train-cnn-training", "train-rf-training",
    "detect-cnn", "detect-rf-refinement",
)


@contextmanager
def owner_lease(path: Path):
    """Hold the same one-byte kernel lock that the actual GUI supervisor uses."""
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    try:
        os.write(descriptor, b"1")
        os.lseek(descriptor, 0, os.SEEK_SET)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(descriptor)
        path.unlink(missing_ok=True)


def call(executable: Path, arguments: list[str], cwd: Path, *, timeout: int = 30):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONNOUSERSITE"] = "1"
    return subprocess.run(
        [str(executable), *arguments],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout,
    )


def check(gui: Path, worker: Path, root: Path) -> dict[str, object]:
    gui = gui.resolve(strict=True)
    worker = worker.resolve(strict=True)
    root = root.resolve(strict=True)
    if root in gui.parents or root in worker.parents:
        raise ValueError("Native smoke must test binaries installed outside the source checkout.")
    with tempfile.TemporaryDirectory(prefix="biocall-native-smoke-") as temporary:
        isolated = Path(temporary)
        version = call(worker, ["--version"], isolated)
        if version.returncode != 0 or version.stdout.strip() != "0.1.0a1":
            raise AssertionError(f"Installed worker/version mismatch: {version!r}")
        help_result = call(worker, ["--help"], isolated)
        if help_result.returncode != 0 or "BioCall Studio" not in help_result.stdout:
            raise AssertionError("Installed CLI help/branding missing.")
        results: dict[str, int] = {}
        with owner_lease(isolated / "supervisor.lease"):
            for mode in MODES:
                # Intentionally malformed bounded request. This exercises the *actual*
                # private mode dispatch, imports and nonzero failure path without
                # publishing outputs or changing researcher-owned inputs.
                request = isolated / f"{mode}.json"
                request.write_text("{", encoding="utf-8")
                response = call(
                    worker,
                    ["--worker", mode, "--request", str(request),
                     "--owner-lease", str(isolated / "supervisor.lease")],
                    isolated,
                    timeout=60,
                )
                if response.returncode == 0:
                    raise AssertionError(f"{mode} accepted malformed request")
                combined = response.stdout + response.stderr
                if any(s in combined for s in ("ModuleNotFoundError", "ImportError", "DLL load failed", "No module named")):
                    raise AssertionError(f"Missing bundled module in {mode}: {combined[-1200:]}")
                results[mode] = response.returncode

        user_data = isolated / "suite-data"
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        env["PYTHONNOUSERSITE"] = "1"
        process = subprocess.Popen(
            [str(gui), "--settings-dir", str(user_data)],
            cwd=isolated, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        try:
            time.sleep(6)
            if process.poll() is not None:
                raise AssertionError(
                    f"Installed GUI exited on startup: {process.returncode}"
                )
            if user_data.resolve().is_relative_to(gui.parent):
                raise AssertionError("Mutable user-data root is inside the app bundle.")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            if process.stderr:
                process.stderr.close()
        return {
            "version": version.stdout.strip(),
            "worker_malformed_request_exit_codes": results,
            "gui_startup_survived_seconds": 6,
            "isolated_user_data_outside_bundle": True,
            "qualification": "minimal native binary smoke only; no scientific output, safe quit or uninstall proof",
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gui", type=Path, required=True)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--checkout", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    if sys.platform not in {"darwin", "win32"}:
        parser.error("A genuine macOS or Windows host is mandatory.")
    print(json.dumps(check(args.gui, args.worker or args.gui, args.checkout), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
