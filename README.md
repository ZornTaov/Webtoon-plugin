# Webtoons plugin for ZornCoMix

A [scraper plugin](https://github.com/ZornTaov/ZornCoMix/wiki/Scraper-Plugins) that keeps a series from
webtoons.com up to date with [Webtoon-Downloader](https://github.com/Zehina/Webtoon-Downloader) (MIT), which the
updater installs from PyPI into the plugin's own `.venv`, pinned to the version `run.py` was checked against.

## Installing

On the updater's web page, open **Plugins** and install from this repository's address. Or clone it into the
updater's config folder under the name `webtoon-dl`:

```sh
git clone https://github.com/ZornTaov/<this repo>.git config/plugins/webtoon-dl
```

The first run installs Webtoon-Downloader and its packages. Nothing has to be installed in the container,
and the image does not need rebuilding.

## Adding a series

On the updater's web page, pick **Webtoons** as the scraper under Add comics. Give the series' list page,
`https://www.webtoons.com/en/genre/series-name/list?title_no=123`, and optionally the episode to start at:
its place in the series' list, the number the site's app shows beside it (`#12`). That is also the number
Webtoon-Downloader's own command line names its archives by, so a series fetched with it up to `153.cbz`
carries on from 154. From a shell, run from the library's root:

```sh
python run_plugin.py --add webtoon-dl Uncompressed/Series "url=https://www.webtoons.com/en/genre/series-name/list?title_no=123" start_episode=1
```

Each run fetches the episodes after the last one taken, oldest first, one at a time. Each episode is a
chapter named for its place and its title (`#45 [Season 2] Ep. 3`), so its archive is numbered by its place
(`c045`). The site's addresses use another number, `episode_no`, which skips every episode ever taken down,
so it is not used. The next run finds the last episode taken by its title. An episode taken down since moves
the later ones up a place, but the run still carries on after the right one. Pictures are kept exactly as the
site serves them.

## Why `run.py`

Webtoon-Downloader's own command line exits 0 when a download fails. It names each archive by the episode's
place in the list, padded to the current number of episodes, so `99.cbz` becomes `099.cbz` once
a series reaches a hundred. It also converts every picture that is not a JPEG, and leaves a good archive
missing pages when a chapter fails part way. `run.py` puts the tool's own pieces together without those
problems, so it depends on the tool's internals.

## Updating Webtoon-Downloader

Raise the pin in `plugin.json`'s `install`, then check `run.py` against that version's
`core/webtoon/downloaders/` before committing. The updater installs the new version on the next run.
