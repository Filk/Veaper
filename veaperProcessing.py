#!/usr/bin/env python3
"""Convert a DaVinci Resolve AAF timeline into a Reaper project (.rpp).

Usage: python3 veaperProcessing.py path/to/timeline.aaf
"""
import argparse
import json
import logging
import os
import re
import shutil
import struct
import subprocess
import sys
import urllib.parse
import urllib.request
import uuid
import wave

import aaf2
from aaf2.components import Filler, OperationGroup, Selector, Sequence, SourceClip, Transition
from aaf2.misc import ConstantValue, VaryingValue
from aaf2.mobs import MasterMob

log = logging.getLogger("veaper")

# The project folder goes next to the AAF's folder, named "<timeline> - Reaper".
OUTPUT_SUFFIX = " - Reaper"
JSON_FILE = "Audio_data_from_aaf.json"
# Remembers which sources produced each WAV so reruns skip media that is up to date.
MANIFEST_FILE = ".veaper_media.json"
DEFAULT_SAMPLE_RATE = 48000
# Reaper gives new items 10 ms fades so hard cuts don't click; do the same
# wherever the AAF has no fade of its own.
DEFAULT_FADE = 0.01
# Reaper fade shapes. Shape 1 ("fast start") is Reaper's closest match to an
# equal-power fade: 0.75 at the midpoint, where equal power is 0.707.
LINEAR_FADE = 0
POWER_FADE = 1


def unwrap(segment):
    """Return the segment that actually plays: a Selector's selected segment,
    or the first non-filler component of a Sequence."""
    while True:
        if isinstance(segment, Selector):
            segment = segment["Selected"].value
        elif isinstance(segment, Sequence):
            segment = next((c for c in segment.components if not isinstance(c, Filler)), None)
        else:
            return segment


def parameters(group):
    return group["Parameters"].value if "Parameters" in group else []


def point_list(varying, duration):
    """Points of an AAF VaryingValue, with times in seconds from the clip start."""
    return [{"time": float(point.time) * duration, "value": float(point.value)}
            for point in varying["PointList"].value]


def pan_envelope_value(aaf_pan):
    """AAF pan runs from 0 (left) to 1 (right). Reaper pan envelopes are stored
    inverted, from 1 (left) to -1 (right)."""
    return 1 - 2 * aaf_pan


def transition_shape(transition):
    try:
        group = transition["OperationGroup"].value
        if parameters(group)[0].interpolation.name == "PowerInterp":
            return POWER_FADE
    except Exception:
        pass
    return LINEAR_FADE


def url_to_path(url):
    # file:///C%3a/Users/user/My%20video.mp4 -> C:\Users\user\My video.mp4
    parsed = urllib.parse.urlparse(url)
    return urllib.request.url2pathname(urllib.parse.unquote(parsed.netloc + parsed.path))


def path_basename(path):
    # The AAF may come from another OS, so split on both kinds of separator.
    return re.split(r"[\\/]", path)[-1]


def unique_name(name, taken):
    """Return `name`, or `name (2)`, `name (3)`... so it is not in `taken`
    (compared case-insensitively, as on Windows and macOS)."""
    stem, ext = os.path.splitext(name)
    candidate, n = name, 1
    while candidate.lower() in taken:
        n += 1
        candidate = "%s (%d)%s" % (stem, n, ext)
    taken.add(candidate.lower())
    return candidate


def safe_filename(name):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip() or "clip"


class AAFInterface:
    """Reads the top-level timeline of an open AAF file into plain dicts."""

    def __init__(self, aaf, aaf_directory, essence_folder=None):
        self.aaf = aaf
        self.aaf_directory = aaf_directory
        # Where embedded audio gets extracted; must be set before reading the timeline.
        self.essence_folder = essence_folder
        self.essence_cache = {}
        self.extracted_names = set()
        try:
            self.encoder = aaf.header["IdentificationList"][0]["ProductName"].value
        except Exception:
            log.warning("Unable to find the program that created the AAF")
            self.encoder = ""

    def get_aaf_metadata(self):
        try:
            identity = self.aaf.header["IdentificationList"][0]
            return {
                "company": identity["CompanyName"].value,
                "product": identity["ProductName"].value,
                "version": identity["ProductVersionString"].value,
                "date": str(identity["Date"].value),
                "platform": identity["Platform"].value,
            }
        except Exception:
            log.warning("Could not read the AAF identity metadata")
            return {}

    # --- Media ---------------------------------------------------------------

    def get_essence_file(self, mob, slot_id):
        """Path of the media behind slot `slot_id` of `mob`, or "" if unknown.

        Embedded audio is extracted the first time it is asked for, so only
        media the timeline uses gets written to disk."""
        if mob is None:
            log.warning("A clip references media that is not in the AAF")
            return ""
        key = (str(mob.mob_id), slot_id)
        if key not in self.essence_cache:
            self.essence_cache[key] = self._find_essence(mob, slot_id)
        return self.essence_cache[key]

    def _find_essence(self, mob, slot_id):
        source_mob = mob
        media_kind = None
        if isinstance(mob, MasterMob):
            source_mob = None
            try:
                slot = mob.slot_at(slot_id)
            except IndexError:
                slot = None
            if slot is not None:
                media_kind = slot.segment.media_kind
                segment = slot.segment
                if isinstance(segment, Sequence):
                    segment = next((c for c in segment.components if isinstance(c, SourceClip)), None)
                if isinstance(segment, SourceClip):
                    source_mob = segment.mob

        if source_mob is None or getattr(source_mob, "descriptor", None) is None:
            log.warning("Cannot find the media for %s (track %s)", mob.name, slot_id)
            return ""
        # Video can't be embedded in an AAF, and we only extract audio.
        if media_kind != "Picture" and getattr(source_mob, "essence", None):
            return self.extract_embedded_essence(source_mob, "%s_%s" % (mob.name or "clip", slot_id))
        return self.get_linked_essence(source_mob)

    def get_linked_essence(self, mob):
        try:
            locators = list(mob.descriptor["Locator"].value)
        except Exception:
            locators = []
        paths = []
        for locator in locators:
            try:
                paths.append(url_to_path(locator["URLString"].value))
            except Exception:
                pass
        for path in paths:
            if os.path.isfile(path):
                return path
            # If the AAF was built on another computer the paths will differ.
            # Typically the media sits in the same folder as the AAF.
            local = os.path.join(self.aaf_directory, path_basename(path))
            if os.path.isfile(local):
                return local
        if not paths:
            log.warning("No file location for %s", mob.name)
            return ""
        return paths[-1]

    def extract_embedded_essence(self, mob, name):
        filename = unique_name(safe_filename(name) + ".wav", self.extracted_names)
        path = os.path.join(self.essence_folder, filename)
        log.info("Extracting embedded audio %s...", filename)
        stream = mob.essence.open()
        try:
            data = stream.read()
        finally:
            stream.close()

        meta = mob.descriptor
        temp_path = path + ".part"
        if "QuantizationBits" in meta:
            # Raw PCM samples (as in MXF or AAF-KLV containers): add a WAV header.
            rate = meta["AudioSamplingRate"].value if "AudioSamplingRate" in meta else meta["SampleRate"].value
            with wave.open(temp_path, "wb") as wav_file:
                wav_file.setnchannels(meta["Channels"].value if "Channels" in meta else 1)
                wav_file.setsampwidth(meta["QuantizationBits"].value // 8)
                wav_file.setframerate(float(rate))
                wav_file.writeframes(data)
        else:
            with open(temp_path, "wb") as f:
                f.write(data)
        os.replace(temp_path, path)
        return path

    # --- Timeline ------------------------------------------------------------

    def parse_operation_group(self, group, edit_rate):
        """Read a clip wrapped in effects (gain, pan, speed, channel combiner).

        Calls itself for nested groups; the caller sets position and duration."""
        item = {}
        name = group.operation.name
        length = group.length / edit_rate

        # Extraction keys on both the operation name and the parameter name,
        # so automation from software that picks other names may be ignored.
        if name in ("Mono Audio Gain", "Audio Gain"):
            for p in parameters(group):
                if p.name not in ("Amplitude", "Amplitude multiplier", "Level"):
                    continue
                if isinstance(p, VaryingValue):
                    item["volume_envelope"] = point_list(p, length)
                elif isinstance(p, ConstantValue):
                    item["volume"] = float(p.value)

        elif name == "Mono Audio Pan":
            for p in parameters(group):
                if p.name != "Pan value":
                    continue
                if isinstance(p, VaryingValue):
                    item["panning_envelope"] = [
                        {"time": point["time"], "value": pan_envelope_value(point["value"])}
                        for point in point_list(p, length)
                    ]
                elif isinstance(p, ConstantValue):
                    item["pan"] = float(p.value) * 2 - 1

        elif name == "Audio Effect":
            # Vegas/MC also saves volume and pan automation here, but with a
            # blank parameter name there's no telling which is which.
            for p in parameters(group):
                if p.name == "SpeedRatio" and isinstance(p, ConstantValue):
                    item["playbackrate"] = float(p.value)

        elif name == "Audio Channel Combiner":
            # One input per channel, usually one mono file each. Reaper plays one
            # file per item, so the files get merged into one when converting.
            clips = [c for c in (unwrap(s) for s in group.segments) if isinstance(c, SourceClip)]
            if clips:
                if len({c.start for c in clips}) > 1:
                    log.warning("Channels of a combined clip start at different points; using the first channel only")
                    clips = clips[:1]
                sources = []
                for clip in clips:
                    source = self.get_essence_file(clip.mob, clip.slot_id)
                    if source and source not in sources:
                        sources.append(source)
                item["source"] = sources[0] if sources else ""
                item["offset"] = clips[0].start / edit_rate
                if len(sources) > 1:
                    item["channel_sources"] = sources
            return item

        inner = unwrap(group.segments[0]) if len(group.segments) else None
        if isinstance(inner, OperationGroup):
            nested = self.parse_operation_group(inner, edit_rate)
            if "volume" in item and "volume" in nested:
                nested["volume"] *= item["volume"]
            item.update(nested)
        elif isinstance(inner, SourceClip):
            item["source"] = self.get_essence_file(inner.mob, inner.slot_id)
            item["offset"] = inner.start / edit_rate
        return item

    def parse_clip(self, segment, edit_rate):
        if isinstance(segment, SourceClip):
            return {
                "source": self.get_essence_file(segment.mob, segment.slot_id),
                "offset": segment.start / edit_rate,
            }
        item = self.parse_operation_group(segment, edit_rate)
        if "source" not in item:
            log.warning("Could not find the media of a clip")
            item["source"] = ""
        item.setdefault("offset", 0)
        return item

    def parse_sequence(self, sequence, edit_rate):
        items = []
        time = 0.0
        previous = None  # "clip", "gap" or "transition"
        pending_fade = None  # (length, shape) for the next clip's fade-in

        for component in sequence.components:
            duration = component.length / edit_rate

            if isinstance(component, Transition):
                # A transition overlaps the clips on both sides of it.
                pending_fade = (duration, transition_shape(component))
                if previous == "clip":
                    items[-1]["fadeout"], items[-1]["fadeouttype"] = pending_fade
                previous = "transition"
                time -= duration
                continue

            segment = unwrap(component)
            item = None
            if isinstance(segment, (SourceClip, OperationGroup)):
                try:
                    item = self.parse_clip(segment, edit_rate)
                except Exception as exc:
                    log.warning("Skipping a clip at %.3f s that could not be read (%s)", time, exc)

            if item is not None:
                item["position"] = time
                item["duration"] = duration
                if previous == "transition":
                    item["fadein"], item["fadeintype"] = pending_fade
                items.append(item)
                previous = "clip"
            else:
                previous = "gap"
            # Always advance, even past an unreadable clip, so later clips keep their sync.
            time += duration

        return items

    def get_picture_tracks(self, slot, first_number):
        edit_rate = float(slot.edit_rate)
        segment = slot.segment
        if isinstance(segment, aaf2.components.NestedScope):
            sequences = [("", s) for s in segment.slots.value]
        elif isinstance(segment, Sequence):
            sequences = [(slot.name or "", segment)]
        else:
            sequences = []
        tracks = []
        for name, sequence in sequences:
            items = self.parse_sequence(sequence, edit_rate)
            if items:
                number = first_number + len(tracks)
                tracks.append({"name": name or "Video %d" % number, "kind": "picture", "items": items})
        return tracks

    def get_sound_track(self, slot, number):
        edit_rate = float(slot.edit_rate)
        track = {"name": slot.name or "Audio %d" % number, "kind": "sound", "items": []}
        segment = slot.segment

        if isinstance(segment, OperationGroup):
            # Track-level pan, wrapped around the track's sequence.
            length = segment.length / edit_rate
            if self.encoder == "DaVinci Resolve" and len(segment.segments):
                # Resolve writes the wrong length here; the sequence has the real one.
                length = segment.segments[0].length / edit_rate
            for p in parameters(segment):
                if p.name not in ("Pan value", "Pan", "Pan Level"):
                    continue
                if isinstance(p, ConstantValue):
                    track["panning"] = float(p.value) * 2 - 1
                elif isinstance(p, VaryingValue):
                    track["panning_envelope"] = [
                        {"time": point["time"], "value": pan_envelope_value(point["value"])}
                        for point in point_list(p, length)
                    ]
            segment = segment.segments[0] if len(segment.segments) else None

        if isinstance(segment, Sequence):
            track["items"] = self.parse_sequence(segment, edit_rate)
        return track

    def get_markers(self, slot):
        markers = []
        edit_rate = float(slot.edit_rate)
        segment = slot.segment
        components = segment.components if isinstance(segment, Sequence) else [segment]
        for component in components:
            if "Position" not in component:
                continue
            comment = component["Comment"].value if "Comment" in component else ""
            user = component["CommentMarkerUser"].value if "CommentMarkerUser" in component else ""
            if self.encoder == "DaVinci Resolve":
                # Resolve stores the marker's name as its "user" and its notes as the comment.
                name = ": ".join(text for text in (user, comment) if text)
            else:
                name = comment or user
            marker = {"name": name, "position": component["Position"].value / edit_rate}
            for key in ("CommentMarkerColor", "CommentMarkerColour"):
                if key in component:
                    colour = component[key].value
                    marker["colour"] = {c[0]: colour[c] // 256 for c in ("red", "green", "blue")}
                    break
            markers.append(marker)
        return markers

    def timeline_mob(self):
        """The top-level composition, i.e. the edited timeline."""
        compositions = list(self.aaf.content.toplevel()) or list(self.aaf.content.compositionmobs())
        if not compositions:
            raise ValueError("The AAF file has no timeline.")
        if len(compositions) > 1:
            log.warning("The AAF has %d timelines; using the first: %s", len(compositions), compositions[0].name)
        return compositions[0]

    def read_timeline(self, mob):
        data = {"name": mob.name, "tracks": [], "markers": []}
        sound_tracks = 0
        for slot in mob.slots:
            try:
                if slot.media_kind == "Picture":
                    picture_tracks = len(get_tracks(data, "picture"))
                    data["tracks"] += self.get_picture_tracks(slot, picture_tracks + 1)
                elif slot.media_kind in ("Sound", "LegacySound"):
                    sound_tracks += 1
                    data["tracks"].append(self.get_sound_track(slot, sound_tracks))
                elif slot.media_kind == "DescriptiveMetadata":
                    data["markers"] += self.get_markers(slot)
            except Exception as exc:
                log.warning("Could not read track %s (%s)", slot.name or slot.slot_id, exc)
        return data


# --- Media conversion --------------------------------------------------------

def get_tracks(data, kind):
    return [track for track in data["tracks"] if track["kind"] == kind]


def item_media(item):
    """The files an item plays, as a tuple: one file, or one per channel."""
    if item.get("channel_sources"):
        return tuple(item["channel_sources"])
    return (item["source"],) if item.get("source") else ()


def is_wav(path):
    return os.path.splitext(path)[1].lower() == ".wav"


def plan_media(media_list, output_folder, ext):
    """Pick a unique file name with extension `ext` in the output folder for each media tuple."""
    names = {}
    taken = set()
    # Embedded audio was already extracted into the output folder; keep its name.
    for media in media_list:
        if len(media) == 1 and os.path.splitext(media[0])[1].lower() == ext and \
                os.path.dirname(os.path.abspath(media[0])) == os.path.abspath(output_folder):
            names[media] = os.path.basename(media[0])
            taken.add(names[media].lower())
    for media in media_list:
        if media not in names:
            stem = os.path.splitext(path_basename(media[0]))[0]
            if len(media) > 1:
                stem += " (%dch)" % len(media)
            names[media] = unique_name(stem + ext, taken)
    return names


def find_ffmpeg():
    """Locate FFmpeg inside a packaged app, next to the source, or on PATH."""
    names = ["ffmpeg.exe", "ffmpeg"] if os.name == "nt" else ["ffmpeg"]
    search_dirs = []

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        exe_dir = os.path.dirname(sys.executable)
        search_dirs.extend([meipass, exe_dir, os.path.join(exe_dir, "..", "Frameworks"), os.path.join(exe_dir, "..", "Resources")])
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        search_dirs.extend([here, os.path.join(here, "vendor")])

    for folder in search_dirs:
        if not folder:
            continue
        for name in names:
            path = os.path.abspath(os.path.join(folder, name))
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path

    found = shutil.which("ffmpeg")
    if found:
        return found

    raise RuntimeError(
        "Veaper could not find FFmpeg, which converts the audio and video for Reaper.\n\n"
        "The standalone Veaper app should already include FFmpeg. "
        "Download the app again if this copy is incomplete.\n\n"
        "If you are running Veaper from source, install FFmpeg, then open a new terminal "
        "and check that the ffmpeg command works."
    )


def _subprocess_window_kwargs():
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {
        "startupinfo": startupinfo,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }


def call_ffmpeg(arguments):
    return subprocess.run(
        [find_ffmpeg()] + arguments,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
        **_subprocess_window_kwargs(),
    )


def run_ffmpeg(arguments):
    result = call_ffmpeg(arguments)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise RuntimeError("\n".join(detail[-8:]) or "FFmpeg failed.")


# ffmpeg describes an audio stream as e.g.
# "Audio: pcm_s24le ([1][0][0][0] / 0x0001), 48000 Hz, 1 channels, s32 (24 bit), 1152 kb/s"
AUDIO_STREAM = re.compile(r"Audio: (\w+).*?, (\d+) Hz, [^,]+, (\w+)(?: \((\d+) bit\))?")
SAMPLE_FORMAT_BITS = {"u8": 8, "s16": 16, "s32": 32, "s64": 64, "flt": 32, "dbl": 64}


def probe_audio(path):
    """Codec, sample rate and bit depth of a file's first audio stream.

    Read from ffmpeg's own description of the file, since the standalone app
    ships ffmpeg but not ffprobe."""
    match = AUDIO_STREAM.search(call_ffmpeg(["-hide_banner", "-nostdin", "-i", path]).stderr or "")
    if not match:
        return {}
    codec, rate, sample_format, bits = match.groups()
    return {
        "codec_name": codec,
        "sample_rate": int(rate),
        "bits": int(bits) if bits else SAMPLE_FORMAT_BITS.get(sample_format.rstrip("p"), 0),
    }


def pcm_codec(stream):
    """A WAV codec that keeps the source's bit depth."""
    codec = stream.get("codec_name", "")
    bits = stream.get("bits", 0)
    if codec.startswith("pcm_f"):
        return "pcm_f32le"
    if codec.startswith("pcm_") and 0 < bits <= 16:
        return "pcm_s16le"
    if codec.startswith("pcm_s32") and bits in (0, 32):
        return "pcm_s32le"
    return "pcm_s24le"


def convert_to_wav(sources, out_path):
    """Write `sources` to a WAV at their own sample rate and bit depth.
    Several sources are merged into one file, one channel per source."""
    arguments = ["-nostdin", "-v", "error", "-y"]
    for source in sources:
        arguments += ["-i", source]
    if len(sources) > 1:
        inputs = "".join("[%d:a:0]" % i for i in range(len(sources)))
        arguments += ["-filter_complex", "%samerge=inputs=%d[out]" % (inputs, len(sources)), "-map", "[out]"]
    else:
        arguments += ["-map", "0:a:0"]
    arguments += ["-c:a", pcm_codec(probe_audio(sources[0])), "-rf64", "auto", "-f", "wav", out_path]
    run_ffmpeg(arguments)


def prepare_audio(media, out_path):
    if len(media) == 1 and is_wav(media[0]):
        shutil.copyfile(media[0], out_path)
    else:
        convert_to_wav(media, out_path)


def video_format():
    """Extension and ffmpeg options for the video copy Reaper plays.

    H.264 with a keyframe every 12 frames and no B-frames decodes everywhere and
    scrubs smoothly; MJPEG is the fallback when ffmpeg has no H.264 encoder."""
    if "libx264" in (call_ffmpeg(["-hide_banner", "-encoders"]).stdout or ""):
        return ".mp4", ["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-g", "12", "-bf", "0",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-write_tmcd", "0", "-f", "mp4"]
    return ".avi", ["-c:v", "mjpeg", "-q:v", "3", "-pix_fmt", "yuvj420p", "-f", "avi"]


def prepare_video(options):
    def convert(media, out_path):
        # Even dimensions, at most 1920 wide, video only: the timeline audio is already in the project.
        run_ffmpeg(["-nostdin", "-v", "error", "-y", "-i", media[0], "-map", "0:v:0", "-an",
                    "-vf", "scale='trunc(min(1920,iw)/2)*2':-2"] + options + [out_path])
    return convert


def prepare_media(names, output_folder, convert, recipe, status, label):
    """Copy or convert each media tuple into the output folder with `convert(media, path)`.

    Files are written under a temporary name and renamed when complete, and a
    manifest records the sources and `recipe` (the conversion settings) behind
    each one, so a rerun skips only files that are complete and still match."""
    manifest_path = os.path.join(output_folder, MANIFEST_FILE)
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, ValueError):
        manifest = {}

    for index, (media, name) in enumerate(names.items(), start=1):
        status("%s %d of %d: %s" % (label, index, len(names), name))
        dest = os.path.join(output_folder, name)
        if len(media) == 1 and os.path.abspath(media[0]) == os.path.abspath(dest):
            continue
        missing = [path for path in media if not os.path.isfile(path)]
        if missing:
            log.warning('Could not find "%s". Keep it in the same folder as the AAF file.', path_basename(missing[0]))
            continue
        fingerprint = {
            "sources": [[os.path.abspath(p), os.path.getsize(p), os.path.getmtime(p)] for p in media],
            "recipe": recipe,
        }
        if os.path.isfile(dest) and manifest.get(name) == fingerprint:
            continue

        temp_path = dest + ".part"
        try:
            convert(media, temp_path)
            os.replace(temp_path, dest)
        except Exception as exc:
            log.warning("Could not prepare %s (%s)", name, exc)
            if os.path.exists(temp_path):
                os.remove(temp_path)
            continue
        manifest[name] = fingerprint
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=1)


def wav_sample_rate(path):
    """Sample rate from a WAV or RF64 file's fmt chunk, or None."""
    try:
        with open(path, "rb") as f:
            header = f.read(12)
            if header[:4] not in (b"RIFF", b"RF64") or header[8:12] != b"WAVE":
                return None
            while True:
                chunk = f.read(8)
                if len(chunk) < 8:
                    return None
                size = struct.unpack("<I", chunk[4:])[0]
                if chunk[:4] == b"fmt ":
                    return struct.unpack("<HHI", f.read(8))[2]
                f.seek(size + (size & 1), 1)
    except (OSError, struct.error):
        return None


def project_sample_rate(paths):
    rates = [rate for rate in map(wav_sample_rate, paths) if rate]
    return max(rates) if rates else DEFAULT_SAMPLE_RATE


# --- Reaper project ----------------------------------------------------------

def new_guid():
    return "{" + str(uuid.uuid4()).upper() + "}"


def rpp_quote(text):
    """Quote a string the way Reaper does: with whichever quote it doesn't contain."""
    text = str(text).replace("\r", " ").replace("\n", " ")
    for quote in ('"', "'", "`"):
        if quote not in text:
            return quote + text + quote
    return '"' + text.replace('"', "'") + '"'


def native_colour(colour):
    """Reaper stores colours in the OS's native byte order, plus a "custom colour" flag."""
    r, g, b = colour["r"], colour["g"], colour["b"]
    if sys.platform == "win32":
        value = r | g << 8 | b << 16
    else:
        value = r << 16 | g << 8 | b
    return value | 0x1000000


def build_envelope(tag, points, indent):
    lines = [
        "<" + tag,
        "  EGUID " + new_guid(),
        "  ACT 1 -1",
        "  VIS 1 1 1",
        "  LANEHEIGHT 0 0",
        "  ARM 0",
        "  DEFSHAPE 0 -1 -1",
    ]
    lines += ["  PT %r %r 0" % (p["time"], p["value"]) for p in sorted(points, key=lambda p: p["time"])]
    lines.append(">")
    return [" " * indent + line for line in lines]


def build_fade(tag, item, length_key, shape_key, default_length):
    length = item.get(length_key)
    shape = item.get(shape_key, LINEAR_FADE)
    if not length:
        length, shape = min(default_length, item["duration"] / 2), POWER_FADE
    return "      %s %d %r 0 %d 0 0 0" % (tag, shape, length, shape)


def build_item(item, source_type="WAVE", default_fade=DEFAULT_FADE):
    source = item["source"]
    lines = [
        "    <ITEM",
        "      POSITION %r" % item["position"],
        "      SNAPOFFS 0",
        "      LENGTH %r" % item["duration"],
        "      LOOP 0",
        "      ALLTAKES 0",
        build_fade("FADEIN", item, "fadein", "fadeintype", default_fade),
        build_fade("FADEOUT", item, "fadeout", "fadeouttype", default_fade),
        "      MUTE 0 0",
        "      SEL 0",
        "      NAME " + rpp_quote(os.path.basename(source)),
        "      VOLPAN %r %r 1 -1" % (item.get("volume", 1), item.get("pan", 0)),
        "      SOFFS %r" % item.get("offset", 0),
        "      PLAYRATE %r 1 0 -1 0 0.0025" % item.get("playbackrate", 1),
        "      CHANMODE 0",
        "      <SOURCE " + source_type,
        "        FILE " + rpp_quote(source),
        "      >",
    ]
    # Clip automation goes on the take, so it moves with the clip and leaves
    # the track's own Volume and Pan lanes free.
    if item.get("volume_envelope"):
        lines += build_envelope("VOLENV", item["volume_envelope"], 6)
    if item.get("panning_envelope"):
        lines += build_envelope("PANENV", item["panning_envelope"], 6)
    lines.append("    >")
    return lines


def build_track(track):
    lines = [
        "  <TRACK",
        "    NAME " + rpp_quote(track["name"]),
        "    PEAKCOL 0",
        "    BEAT -1",
        "    AUTOMODE 0",
        "    VOLPAN 1 %r -1 -1 1" % track.get("panning", 0),
        "    MUTESOLO 0 0 0",
        "    IPHASE 0",
        "    PLAYOFFS 0 1",
        "    ISBUS 0 0",
        "    BUSCOMP 0 0 0 0 0",
        "    SHOWINMIX 1 0.6667 0.5 1 0.5 0 0 0",
        "    SEL 0",
        "    REC 0 0 1 0 0 0 0 0",
        "    VU 2",
        "    TRACKHEIGHT 0 0 0 0 0 0",
        "    INQ 0 0 0 0.5 100 0 0 100",
        "    NCHAN 2",
        "    FX 1",
        "    PERF 0",
        "    MIDIOUT -1",
        "    MAINSEND 1 0",
    ]
    if track.get("panning_envelope"):
        lines += build_envelope("PANENV2", track["panning_envelope"], 4)
    for item in track["items"]:
        if item.get("source"):
            if track["kind"] == "picture":
                # No default fades on video: they would fade the picture.
                lines += build_item(item, "VIDEO", default_fade=0)
            else:
                lines += build_item(item)
    lines.append("  >")
    return lines


def build_markers(markers):
    lines = []
    for number, marker in enumerate(sorted(markers, key=lambda m: m["position"]), start=1):
        colour = native_colour(marker["colour"]) if "colour" in marker else 0
        lines.append("  MARKER %d %r %s 0 %d" % (number, marker["position"], rpp_quote(marker["name"]), colour))
    return lines


PROJECT_HEADER = """<REAPER_PROJECT 0.1 "7.0" 0
  <NOTES 0 2
  >
  RIPPLE 0
  GROUPOVERRIDE 0 0 0
  AUTOXFADE 129
  ENVATTACH 1
  POOLEDENVATTACH 0
  MIXERUIFLAGS 11 48
  PEAKGAIN 1
  FEEDBACK 0
  PANLAW 1
  PROJOFFS 0 0 0
  MAXPROJLEN 0 600
  GRID 3454 8 1 8 1 0 0 0
  TIMEMODE 1 5 -1 30 0 0 -1
  VIDEO_CONFIG 0 0 256
  PANMODE 3
  CURSOR 0
  ZOOM 7.87791667974761 0 0
  VZOOMEX 6 0
  USE_REC_CFG 0
  RECMODE 1
  SMPTESYNC 0 30 100 40 1000 300 0 0 1 0 0
  LOOP 0
  LOOPGRAN 0 4
  RECORD_PATH "" ""
  <RECORD_CFG
    ZXZhdxgAAA==
  >
  <APPLYFX_CFG
  >
  RENDER_FILE ""
  RENDER_PATTERN ""
  RENDER_FMT 0 2 0
  RENDER_1X 0
  RENDER_RANGE 1 0 0 18 1000
  RENDER_RESAMPLE 3 0 1
  RENDER_ADDTOPROJ 0
  RENDER_STEMS 0
  RENDER_DITHER 0
  TIMELOCKMODE 0
  TEMPOENVLOCKMODE 0
  ITEMMIX 0
  DEFPITCHMODE 589824 0
  TAKELANE 1
  SAMPLERATE {sample_rate} 1 0
  <RENDER_CFG
    ZXZhdxgAAA==
  >
  LOCK 1
  <METRONOME 6 2
    VOL 0.25 0.125
    FREQ 800 1600 1
    BEATLEN 4
    SAMPLES "" ""
    PATTERN 2863311530 2863311529
    MULT 1
  >
  GLOBAL_AUTO -1
  TEMPO 120 4 4
  PLAYRATE 1 0 0.25 4
  SELECTION 0 0
  SELECTION2 0 0
  MASTERAUTOMODE 0
  MASTERTRACKHEIGHT 0 0
  MASTERPEAKCOL 16576
  MASTERMUTESOLO 0
  MASTERTRACKVIEW 0 0.6667 0.5 0.5 0 0 0 0 0 0 0 0 0
  MASTERHWOUT 0 0 1 0 0 0 0 -1
  MASTER_NCH 2 2
  MASTER_VOLUME 1 0 -1 -1 1
  MASTER_PANMODE 3
  MASTER_FX 1
  MASTER_SEL 0
  <PROJBAY
  >"""


def build_reaper_project(data, sample_rate):
    lines = [PROJECT_HEADER.format(sample_rate=sample_rate)]
    lines += build_markers(data["markers"])
    # Video tracks go on top, highest layer first: Reaper shows the topmost video,
    # and in Resolve the highest video track wins.
    for track in reversed(get_tracks(data, "picture")):
        lines += build_track(track)
    for track in get_tracks(data, "sound"):
        lines += build_track(track)
    lines.append(">")
    return "\n".join(lines) + "\n"


# --- Entry point -------------------------------------------------------------

class _WarningCollector(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def import_aaf(aaf_path, output_folder=None, on_status=None):
    """Convert `aaf_path` into a self-contained Reaper project folder.

    By default the folder sits next to the AAF's folder (not inside it) and is
    named "<timeline> - Reaper". All the media the project uses, video included,
    is copied or converted into it, so it doesn't depend on the original folder.
    `on_status` is called with progress messages.

    Returns {"project": .rpp path, "folder": project folder, "warnings": [...]}.
    Raises if the AAF can't be read."""
    def status(message):
        log.info(message)
        if on_status:
            on_status(message)

    aaf_path = os.path.abspath(aaf_path)
    aaf_directory = os.path.dirname(aaf_path)
    warnings = _WarningCollector()
    log.addHandler(warnings)
    try:
        status("Reading the AAF file...")
        try:
            aaf = aaf2.open(aaf_path, "r")
        except Exception as exc:
            raise RuntimeError(
                "Could not open this AAF file. Export it again from DaVinci Resolve and try once more."
            ) from exc
        with aaf:
            reader = AAFInterface(aaf, aaf_directory)
            meta = reader.get_aaf_metadata()
            if meta:
                log.info("AAF created on %(date)s with %(company)s %(product)s %(version)s on %(platform)s", meta)
            mob = reader.timeline_mob()
            project_name = safe_filename(mob.name or os.path.splitext(os.path.basename(aaf_path))[0])
            if output_folder is None:
                output_folder = os.path.join(os.path.dirname(aaf_directory), project_name + OUTPUT_SUFFIX)
            output_folder = os.path.abspath(output_folder)
            os.makedirs(output_folder, exist_ok=True)
            reader.essence_folder = output_folder
            timeline = reader.read_timeline(mob)

        audio_items = [item for track in get_tracks(timeline, "sound") for item in track["items"]]
        video_items = [item for track in get_tracks(timeline, "picture") for item in track["items"]]
        audio_media = list(dict.fromkeys(item_media(item) for item in audio_items if item_media(item)))
        video_media = list(dict.fromkeys(item_media(item) for item in video_items if item_media(item)))
        if not audio_media:
            log.warning("No audio clips were found in this AAF. The Reaper project may be empty.")
        if video_media or any(not (len(m) == 1 and is_wav(m[0])) for m in audio_media):
            find_ffmpeg()  # Fail early, with a clear message, if FFmpeg is missing.

        audio_names = plan_media(audio_media, output_folder, ".wav")
        prepare_media(audio_names, output_folder, prepare_audio, "wav", status, "Audio")
        video_names = {}
        if video_media:
            ext, options = video_format()
            video_names = plan_media(video_media, output_folder, ext)
            prepare_media(video_names, output_folder, prepare_video(options), " ".join(options), status,
                          "Video (this can take a few minutes)")

        # Reaper finds media relative to the .rpp, so items use bare file names.
        for items, names in ((audio_items, audio_names), (video_items, video_names)):
            for item in items:
                if item_media(item):
                    item["source"] = names[item_media(item)]
        sample_rate = project_sample_rate(os.path.join(output_folder, name) for name in audio_names.values())

        status("Writing the Reaper project...")
        with open(os.path.join(output_folder, JSON_FILE), "w", encoding="utf-8") as f:
            json.dump(timeline, f, indent=4, ensure_ascii=False)
        rpp_path = os.path.join(output_folder, project_name + ".rpp")
        with open(rpp_path, "w", encoding="utf-8") as f:
            f.write(build_reaper_project(timeline, sample_rate))
        status("Done.")
    finally:
        log.removeHandler(warnings)
    return {"project": rpp_path, "folder": output_folder, "warnings": warnings.messages}


def main():
    parser = argparse.ArgumentParser(description="Convert a DaVinci Resolve AAF into a Reaper project.")
    parser.add_argument("aaf", help="AAF file exported from Resolve")
    parser.add_argument("-o", "--output", help='project folder (default: "<timeline> - Reaper" next to the AAF\'s folder)')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    result = import_aaf(args.aaf, args.output)
    print("Done: %s (%d warnings)" % (result["project"], len(result["warnings"])))


if __name__ == "__main__":
    main()
