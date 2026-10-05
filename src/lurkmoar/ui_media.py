"""External-open helpers (the in-app image viewer is added in Task 9)."""
import shlex
import subprocess

VIDEO_EXT = {".webm", ".mp4"}


def is_video(ext: str) -> bool:
    return ext.lower() in VIDEO_EXT


def _spawn(argv):
    subprocess.Popen(argv, start_new_session=True, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def open_url(url: str):
    _spawn(["xdg-open", url])


def play_video(command: str, url: str):
    _spawn(shlex.split(command or "mpv") + [url])
