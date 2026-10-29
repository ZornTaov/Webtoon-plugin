#the Webtoons plugin's own command: run.py, which puts Webtoon-Downloader's pieces together, on a series
#address - oldest episode first, into the folder the updater hands it, starting after the last episode
#taken. that is known by the number the site gives it, which each chapter's label opens with
import os
import re
import sys

PLUGIN = os.path.dirname(os.path.abspath(__file__))
#"#45 (S2) Episode 3": the site's own number for the episode, not its place in the list, which an episode
#taken down would shift
EPISODE = re.compile(r"^#(\d+)\b")


def build_command(settings, state, staging):
    command = [sys.executable, os.path.join(PLUGIN, "run.py"), settings["url"], "--output", staging]
    last = EPISODE.match(state.get("last_chapter") or "")
    if last:
        return command + ["--after", last.group(1)]
    #before anything has been taken: the episode the comic was added with, or none for the first
    start = (settings.get("plugin") or {}).get("start_episode")
    if start:
        command += ["--from", str(start)]
    return command
