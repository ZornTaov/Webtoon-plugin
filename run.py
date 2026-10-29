#the Webtoons plugin's program. Webtoon-Downloader's command line will not do as it is: it exits 0 when a
#download fails, names each archive by the episode's place padded to however many episodes there are now
#(so 99.cbz is 099.cbz once a series reaches a hundred), converts every picture that is not a JPEG, and
#leaves an archive holding only the pages it got when a chapter fails part way. so its pieces are put
#together here instead. this leans on its internals, so recheck it whenever the pinned version moves.
#exits 0 done (or nothing new), 1 bad arguments, 2 failed, 130 stopped
import argparse
import asyncio
import dataclasses
import os
import re
import signal
import sys
from pathlib import Path

from webtoon_downloader.core.downloaders.image import HttpImageDownloader
from webtoon_downloader.core.exceptions import DownloadError
from webtoon_downloader.core.webtoon.client import WebtoonHttpClient
from webtoon_downloader.core.webtoon.downloaders.chapter import ChapterDownloader
from webtoon_downloader.core.webtoon.downloaders.comic import WebtoonDownloader
from webtoon_downloader.core.webtoon.fetchers import WebtoonFetcher
from webtoon_downloader.core.webtoon.namer import SeparateFileNameGenerator
from webtoon_downloader.storage import AioZipWriter

#one episode at a time, so the archives finished are always every episode up to some point: stopped at
#its deadline, or killed outright, a run can never leave a later episode taken and an earlier one not,
#which the next run would step past for good. the pages of one go side by side, far fewer than the
#tool's own 120, which the site answers by refusing it for a while
EPISODES_AT_ONCE, PAGES_AT_ONCE = 1, 16
UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
LONGEST = 120


LABELLED = re.compile(r"^#(\d+)(?: (.*))?$")


def label(episode):
    #the chapter's name, and so its archive's: the episode's place in the series' list first - the number
    #the site's app and mobile pages show beside it, and what the tool's own command line names its archive
    #by - which the updater reads as the chapter's own number. then the title, made fit for a file name. not
    #the site's episode_no, which skips the number of every episode ever taken down, so a series with a gap
    #early on is #164 there where its readers know it as #153
    title = " ".join(UNSAFE.sub(" ", episode.title).split())
    return "#{0} {1}".format(episode.number, title)[:LONGEST].rstrip(" .") if title else \
        "#{0}".format(episode.number)


def after(listed, last):
    #the episodes after the last one taken, found by its title: an episode taken down since moves every
    #later one up a place, so the place its label says may now be another episode's. the title at or
    #nearest that place wins, for a series with two episodes of one name. a title found nowhere - renamed
    #on the site since, or taken down itself - leaves only the place to go by, and says so
    said = LABELLED.match(last)
    if not said:
        raise ValueError("{0!r} is not a chapter this plugin named, #<place> <title>".format(last))
    place = int(said.group(1))
    same = [at for at, episode in enumerate(listed) if label(episode) == last] or \
        [at for at, episode in enumerate(listed) if LABELLED.match(label(episode)).group(2) == said.group(2)]
    if same:
        at = min(same, key=lambda at: abs(listed[at].number - place))
        if listed[at].number != place:
            print("{0} is #{1} now: an earlier episode was taken down or added since.".format(
                last, listed[at].number), flush=True)
        return listed[at + 1:]
    print("WARNING: no episode is called what {0} was, so this carries on after #{1}, by place alone.".format(
        last, place), flush=True)
    return [episode for episode in listed if episode.number > place]


class Aside:
    #a chapter's archive, written under another name and given its own only once every page and its
    #ComicInfo are in. the tool's own closes the archive whatever happened, so a chapter that failed part
    #way would be a good archive missing pages - taken in, and never fetched again. the updater ignores a
    #.writing file, so one left by a run killed outright is not taken in either
    def __init__(self, path):
        self.path = path
        self.writing = path.with_name(path.name + ".writing")
        self.archive = AioZipWriter(self.writing)

    async def __aenter__(self):
        await self.archive.__aenter__()
        return self

    async def write(self, stream, name):
        return await self.archive.write(stream, name)

    async def __aexit__(self, kind, error, traceback):
        await self.archive.__aexit__(kind, error, traceback)
        if kind is None:
            os.replace(self.writing, self.path)
        else:
            os.remove(self.writing)


class Flat(SeparateFileNameGenerator):
    #an episode's pages as 001.jpg on at the top of its archive, which the tool's own namers put in a
    #folder named for the episode or prefix with its place in the list
    def get_chapter_directory(self, chapter_info):
        return Path(".")


@dataclasses.dataclass
class Episodes(WebtoonDownloader):
    #the tool's series downloader, handed the episodes already picked and naming each archive by its label
    episodes: list = dataclasses.field(default_factory=list)

    async def _get_chapters(self):
        return self.episodes

    async def _get_storage(self, chapter_info):
        return Aside(Path(self._directory) / (label(chapter_info) + ".cbz"))


def wanted(listed, last=None, first=None):
    if last:
        return after(listed, last)
    if first:
        return [episode for episode in listed if episode.number >= first]
    return list(listed)


async def report(chapter_info, kind, extractor=None):
    if kind == "Completed":
        print("  {0}".format(label(chapter_info)), flush=True)


async def fetch(args):
    async with WebtoonHttpClient(retry_strategy="exponential") as client:
        listed = await WebtoonFetcher(client, args.url).get_chapters_details(args.url)
        picked = wanted(listed, args.after, args.first)
        if not picked:
            print("No episode after {0} yet: caught up.".format(args.after) if args.after else
                  "The series lists no episode{0}.".format(" from #{0}".format(args.first) if args.first else ""))
            return
        #the tool's ComicInfo gives each its place as its Number, as its label does
        print("{0} episode(s) to fetch, #{1} to #{2}:".format(
            len(picked), picked[0].number, picked[-1].number), flush=True)
        pages = HttpImageDownloader(client=client, concurrent_downloads_limit=PAGES_AT_ONCE,
                                    #no conversion: every picture kept as the site served it
                                    transformers=[])
        chapters = ChapterDownloader(client=client, image_downloader=pages,
                                     file_name_generator=Flat(),
                                     concurrent_downloads_limit=EPISODES_AT_ONCE, progress_callback=report)
        await Episodes(url=args.url, client=client, chapter_downloader=chapters, storage_type="cbz", quality=100,
                       directory=args.output, episodes=picked).run()


def chain(error):
    #an error and what caused it, all the way down: the tool's say only "chapter failed", their cause why
    while error is not None:
        yield error
        error = getattr(error, "cause", None) or error.__cause__


def stopped(*_):
    raise KeyboardInterrupt


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fetch a webtoons.com series, an archive per episode.")
    parser.add_argument("url", help="the series' list page, https://www.webtoons.com/.../list?title_no=...")
    parser.add_argument("--output", required=True, help="the folder to write the archives into")
    start = parser.add_mutually_exclusive_group()
    start.add_argument("--after", metavar="LABEL",
                       help="the last chapter taken, '#<place> <title>': fetch the episodes after it")
    start.add_argument("--from", dest="first", type=int,
                       help="fetch from this place in the series' list on, the number the site's app shows")
    try:
        args = parser.parse_args(argv)
    except SystemExit as stop:
        #argparse's own 2 would read as a failed fetch
        return 1 if stop.code else 0
    os.makedirs(args.output, exist_ok=True)
    #the updater stops a run at its deadline with SIGTERM: the episode being written is dropped, and the
    #ones finished are kept for it to take in
    signal.signal(signal.SIGTERM, stopped)
    try:
        asyncio.run(fetch(args))
    except KeyboardInterrupt:
        print("Stopped; the episodes finished are kept.", flush=True)
        return 130
    #called below download_webtoon, which would have wrapped them, so whatever the tool or httpx raises
    #lands here - a failure, never the 1 that says the command was wrong
    except Exception as error:
        print("ERROR: {0}: {1}".format(type(error).__name__, error), flush=True)
        if isinstance(error, DownloadError) and "Rate limited" in " ".join(str(cause) for cause in chain(error)):
            print("The site is refusing requests for now; the next run tries again.", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
