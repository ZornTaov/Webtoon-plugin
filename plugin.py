#the Webtoons plugin's own command: run.py, which puts Webtoon-Downloader's pieces together, on a series
#address - oldest episode first, into the folder the updater hands it, starting after the last episode
#taken. run.py finds that by its label, "#153 Some title", the episode's place in the list and its title
import os
import sys

PLUGIN = os.path.dirname(os.path.abspath(__file__))


def build_command(settings, state, staging):
    command = [sys.executable, os.path.join(PLUGIN, "run.py"), settings["url"], "--output", staging]
    last = state.get("last_chapter")
    if last:
        return command + ["--after", last]
    #before anything has been taken: the place the comic was added with, or none for the first
    start = (settings.get("plugin") or {}).get("start_episode")
    if start:
        command += ["--from", str(start)]
    return command
