#!/bin/python
import aaf2
import os
import sys
import wave
import urllib.parse
import urllib.request
import pprint
import json
from moviepy import AudioFileClip

have_tk = False

[NOTICE, WARNING, ERROR, NONE] = range(4)
log_level = WARNING

class AAFInterface:

    def __init__(self, myDirectory):
        self.aaf = None
        self.encoder = ""
        self.aaf_directory = myDirectory
        self.essence_data = {}

    def open(self, filename):
        try:
            self.aaf = aaf2.open(filename, "r")
        except Exception:
            print("Could not open AAF file.", ERROR)
            return False
        try:
            self.encoder = self.aaf.header["IdentificationList"][0]["ProductName"].value
        except Exception:
            print("Unable to find file encoder", WARNING)
        self.aaf_directory = os.path.abspath(os.path.dirname(filename))
        self.essence_data = {}
        return True

    def build_wav(self, fname, data, depth=24, rate=48000, channels=2):
        with wave.open(fname, "wb") as f:
            f.setnchannels(channels)
            f.setsampwidth(int(depth / 8))
            f.setframerate(rate)
            f.writeframesraw(data)
            f.close()

    def aafrational_value(self, rational):
        return rational.numerator / rational.denominator

    def get_point_list(self, varying, duration):
        data = []
        for point in varying["PointList"]:
            data.append({
                "time": point.time * duration,
                "value": point.value
            })
        return data

    def get_linked_essence(self, mob):
        try:
            url = mob.descriptor.locator.pop()["URLString"].value
            # file:///C%3a/Users/user/My%20video.mp4
            url = urllib.parse.urlparse(url)
            url = url.netloc + url.path
            # /C%3a/Users/user/My%20video.mp4
            url = urllib.parse.unquote(url)
            # /C:/Users/user/My video.mp4
            url = urllib.request.url2pathname(url)
            # C:\\Users\\user\\My video.mp4

            # If the AAF was built on another computer,
            # chances are the paths will differ.
            # Typically the source files are in the same directory as the AAF.
            if not os.path.isfile(url):
                local = os.path.join(self.aaf_directory, os.path.basename(url))
                if os.path.isfile(local):
                    url = local
            return url

        except Exception:
            print("Error retrieving file url for %s" % mob.name, WARNING)
            return ""

    def extract_embedded_essence(self, mob, filename):
        print("Extracting essence %s..." % filename)
        stream = mob.essence.open()
        data = stream.read()
        stream.close()

        meta = mob.descriptor
        data_fmt = meta["ContainerFormat"].value.name if "ContainerFormat" in meta else ""
        if data_fmt == "MXF":
            sample_depth = meta["QuantizationBits"].value
            sample_rate = meta["SampleRate"].value
            sample_rate = self.aafrational_value(sample_rate)
            self.build_wav(filename, data, sample_depth, sample_rate)
        else:
            with open(filename, "wb") as f:
                f.write(data)
                f.close()

        return filename

    def extract_essence(self, target, callback):
        for master_mob in self.aaf.content.mastermobs():
            self.essence_data[master_mob.name] = {}
            for slot in master_mob.slots:

                if isinstance(slot.segment, aaf2.components.Sequence):
                    source_mob = None
                    for component in slot.segment.components:
                        if isinstance(component, aaf2.components.SourceClip):
                            source_mob = component.mob
                            break
                    else:
                        self.essence_data[master_mob.name][slot.slot_id] = ""
                        print("Cannot find essence for %s slot %d" % (master_mob.name, slot.slot_id), WARNING)
                elif isinstance(slot.segment, aaf2.components.SourceClip):
                    source_mob = slot.segment.mob

                if slot.segment.media_kind == "Picture":
                    # Video files cannot be embedded in the AAF.
                    self.essence_data[master_mob.name][slot.slot_id] = self.get_linked_essence(source_mob)
                    continue
                if source_mob.essence:
                    filename = os.path.join(target, master_mob.name + slot.name + ".wav")
                    if callback:
                        callback("Extracting %s..." % (master_mob.name + slot.name + ".wav"))
                    self.essence_data[master_mob.name][slot.slot_id] = self.extract_embedded_essence(source_mob, filename)
                else:
                    self.essence_data[master_mob.name][slot.slot_id] = self.get_linked_essence(source_mob)

    def get_essence_file(self, mob_name, slot_id):
        try:
            return self.essence_data[mob_name][slot_id]
        except Exception:
            print("Cannot find essence for %s slot %d" % (mob_name, slot_id), WARNING)
            return ""

    def get_embedded_essence_count(self):
        count = 0
        for master_mob in self.aaf.content.mastermobs():
            for slot in master_mob.slots:
                if isinstance(slot.segment, aaf2.components.Sequence):
                    source_mob = None
                    for component in slot.segment.components:
                        if isinstance(component, aaf2.components.SourceClip):
                            source_mob = component.mob
                            break
                    else:
                        continue
                elif isinstance(slot.segment, aaf2.components.SourceClip):
                    source_mob = slot.segment.mob
                if slot.segment.media_kind == "Sound" and source_mob.essence:
                    count += 1
        return count


    # Instead of using per-item volume curves (aka take volume envelope),
    # we collect data from items and "render" it to the track volume envelope.
    def collect_vol_pan_automation(self, track):
        envelopes = {
            "volume_envelope": [],
            "panning_envelope": []
        }
        for envelope in envelopes:
            for item in track["items"]:
                if envelope in item:
                    for point in item[envelope]:
                        envelopes[envelope].append({
                            "time": item["position"] + point["time"],
                            "value": point["value"]
                        })
                    del item[envelope]
                else:
                    if not envelopes[envelope]: continue
                    # We don't want items without automation to be affected
                    # by automation added by other items
                    envelopes[envelope].append({
                        "time": item["position"],
                        "value": 1.0
                    })
                    envelopes[envelope].append({
                        "time": item["position"] + item["duration"],
                        "value": 1.0
                    })

        # Add only if not empty
        if envelopes["volume_envelope"]:
            track["volume_envelope"] = envelopes["volume_envelope"]
        if envelopes["panning_envelope"]:
            track["panning_envelope"] = envelopes["panning_envelope"]

        return track

    # Function is meant to be called recursively.
    # It is supposed to gather whatever information it can and pass it to
    # its caller, who will append the new data to its own.
    # The topmost caller sets "position" and "duration", as well as fades,
    def parse_operation_group(self, group, edit_rate):

        item = {}

        # We could base volume envelope extraction on either group.operation.name
        # or group.parameters[].name depending on which is more prone to be constant.
        # For now both conditions have to be met, which may cause some automation to
        # be ignored if other software picks different operation or parameter names.
        if group.operation.name in ["Mono Audio Gain", "Audio Gain"]:
            for p in group.parameters:
                if p.name not in ["Amplitude", "Amplitude multiplier", "Level"]: continue
                if isinstance(p, aaf2.misc.VaryingValue):
                    item["volume_envelope"] = self.get_point_list(p, group.length / edit_rate)
                elif isinstance(p, aaf2.misc.ConstantValue):
                    item["volume"] = self.aafrational_value(p.value)

        if group.operation.name == "Mono Audio Pan":
            for p in group.parameters:
                points = self.get_point_list(p, group.length / edit_rate)
                if p.name == "Pan value":
                    item["panning_envelope"] = [{
                        "time": point["time"],
                        "value": point["value"] * -2 + 1
                    } for point in points]

        if group.operation.name == "Audio Effect":
            for p in group.parameters:
                if p.name == "":
                    # Vegas/MC saves per-item volume and panning automation
                    # but I haven't figured out a way to find out which is which
                    # since the parameter name is blank.
                    pass
                if p.name == "SpeedRatio":
                    item["playbackrate"] = self.aafrational_value(p.value)

        segment = group.segments[0]

        # Aaaargh, why is this a thing?
        if isinstance(segment, aaf2.components.Sequence):
            segment = segment.components[0]

        if isinstance(segment, aaf2.components.OperationGroup):
            item.update(self.parse_operation_group(segment, edit_rate))
        elif isinstance(segment, aaf2.components.SourceClip):
            item.update({
                "source": self.get_essence_file(segment.mob.name, segment.slot_id),
                "offset": segment.start / edit_rate,
            })

        return item

    def parse_sequence(self, sequence, edit_rate):
        items = []
        time = 0.0
        fade = 0  # 0 = no fade, 1 = fade, -1 = last component was filler
        fade_length = None
        fade_type = 0  # 0 = linear, 1 = power

        for component in sequence.components:
            try:
                duration = component.length / edit_rate

                if isinstance(component, aaf2.components.SourceClip):
                    item = {
                        "source": self.get_essence_file(component.mob.name, component.slot_id),
                        "offset": component.start / edit_rate,
                        "position": time,
                        "duration": duration,
                    }
                    if fade == 1:
                        item["fadein"] = fade_length
                        item["fadeintype"] = fade_type
                    fade = 0
                    items.append(item)
                    time += duration

                elif isinstance(component, aaf2.components.OperationGroup):
                    item = {
                        "position": time,
                        "duration": duration
                    }
                    item.update(self.parse_operation_group(component, edit_rate))
                    if fade == 1:
                        item["fadein"] = fade_length
                        item["fadeintype"] = fade_type
                    fade = 0

                    if "source" not in item:
                        print("Failed to find item source at %f seconds." % time, WARNING)
                        item["source"] = ""
                    if "offset" not in item:
                        print("Failed to find item offset at %f seconds." % time, WARNING)
                        item["offset"] = 0

                    items.append(item)
                    time += duration

                elif isinstance(component, aaf2.components.Transition):
                    fade_length = duration
                    fade_type = 0
                    try:
                        if component["OperationGroup"].value.parameters.value[0].interpolation.name == "PowerInterp":
                            fade_type = 1
                    except Exception:
                        pass
                    if fade == 0:
                        items[-1]["fadeout"] = fade_length
                        items[-1]["fadeouttype"] = fade_type
                    if fade != 1:
                        fade = 1
                    time -= duration

                elif isinstance(component, aaf2.components.Filler):
                    fade = -1
                    time += duration

            except Exception:
                print("Failed to parse component at %f seconds." % time)

        return items

    def get_picture_tracks(self, slot):
        data = []
        edit_rate = self.aafrational_value(slot.edit_rate)

        if isinstance(slot.segment, aaf2.components.NestedScope):
            for sequence in slot.segment.slots.value:
                seq_data = self.parse_sequence(sequence, edit_rate)
                if seq_data:
                    data.append({
                        "name": "",
                        "items": seq_data
                    })
        elif isinstance(slot.segment, aaf2.components.Sequence):
            seq_data = self.parse_sequence(slot.segment, edit_rate)
            if seq_data:
                data.append({
                    "name": slot.name,
                    "items": seq_data
                })

        return data

    def get_sound_track(self, slot):
        data = {
            "name": slot.name
        }
        edit_rate = self.aafrational_value(slot.edit_rate)
        segment = slot.segment
        if isinstance(segment, aaf2.components.OperationGroup):
            # Maybe we should check for segment.operation.name as well?
            for p in segment.parameters:
                if p.name == "Pan value":
                    data["panning"] = self.aafrational_value(p.value) * 2 - 1
                if p.name in ["Pan", "Pan Level"]:
                    # Sometimes segment.length is wrong so we have to use
                    # the length of the data segment instead.
                    real_length = segment.length / edit_rate
                    if self.encoder == "DaVinci Resolve":
                        real_length = segment.segments[0].length / edit_rate
                    points = self.get_point_list(p, real_length)
                    data["panning_envelope"] = [{
                        "time": point["time"],
                        "value": point["value"] * -2 + 1
                        # Reaper can't make up its mind 
                    } for point in points]
            data["items"] = self.parse_sequence(segment.segments[0], edit_rate)
        elif isinstance(segment, aaf2.components.Sequence):
            data["items"] = self.parse_sequence(segment, edit_rate)
        return data

    def get_markers(self, slot):
        markers = []
        edit_rate = self.aafrational_value(slot.edit_rate)
        for component in slot.segment.components:
            marker = {
                "name": component["Comment"].value,
                "position": component["Position"].value / edit_rate
            }
            if "CommentMarkerColour" in component:
                col = component["CommentMarkerColour"].value
                marker["colour"] = {
                    "r": int(col["red"] / 256),
                    "g": int(col["green"] / 256),
                    "b": int(col["blue"] / 256)
                }
            markers.append(marker)
        return markers

    def get_composition_list(self):
        return [composition.name for composition in self.aaf.content.compositionmobs()]

    def get_composition(self, composition):
        data = {
            "tracks": [],
            "markers": []
        }

        for slot in list(self.aaf.content.compositionmobs())[composition].slots:
            try:
                if slot.media_kind == "Picture":
                    picture_tracks = self.get_picture_tracks(slot)
                    if picture_tracks:
                        data["tracks"] += picture_tracks
                elif slot.media_kind in ["Sound", "LegacySound"]:
                    track_data = self.get_sound_track(slot)
                    track_data = self.collect_vol_pan_automation(track_data)
                    data["tracks"].append(track_data)
                elif slot.media_kind == "DescriptiveMetadata":
                    data["markers"] += self.get_markers(slot)
            except Exception:
                print("Failed parsing slot %s" % slot.name, WARNING)
        return data

    def get_aaf_metadata(self):
        try:
            identity = self.aaf.header["IdentificationList"][0]
            return {
                "company": identity["CompanyName"].value,
                "product": identity["ProductName"].value,
                "version": identity["ProductVersionString"].value,
                "date": identity["Date"].value,
                "platform": identity["Platform"].value
            }
        except Exception:
            print("Could not get file identity metadata.", WARNING)
            return {}

def extract_audio_from_mxf(mxf_file_path, output_file_path):
    audio_clip = AudioFileClip(mxf_file_path)
    audio_clip.write_audiofile(output_file_path)
    audio_clip.close()


def import_aaf(myDirectory, myAFFfile):

    global log_level
    aaf_interface = AAFInterface(myDirectory)

    #if len(sys.argv) < 2:
        #print("No input file provided.", ERROR)
        #return
    #filename = sys.argv[1]
    filename = myAFFfile
    print(filename)

    #name of the destination folder for translation
    target = "Reaper_from_DaVinci"

    if not os.path.exists(target):
        os.mkdir(target)
    log_level = NOTICE

    if not aaf_interface.open(filename): return
    print("geting data from %s..." % filename)
    meta = aaf_interface.get_aaf_metadata()
    print("AAF created on %s with %s %s version %s using %s" % 
        (str(meta["date"]), meta["company"], meta["product"], meta["version"], meta["platform"])
    )

    aaf_interface.extract_essence(target, None)

    composition_list = aaf_interface.get_composition_list()
    composition_id = 0
    if len(composition_list) > 1:
        composition_id = UserInteraction.get_composition(composition_list)
    composition = aaf_interface.get_composition(composition_id)

    #print(json.dumps(composition))
    json_dados= json.dumps(composition, indent=4)

    #file_path refere-se ao caminho para o ficheiro json
    file_path = os.path.join(target, "Audio_data_from_aaf.json")
    with open(file_path, "w") as json_file:
        json_file.write(json_dados)

    #SCRIPT 2
    # Directory paths
    # Construct the full paths to where the mxf are located
    mxf_directory = myDirectory
    
    # The destination project folder
    destination_folder = os.path.join(mxf_directory, target)

    # Iterate through MXF files in the subdirectory
    for filename in os.listdir(mxf_directory):
        if filename.endswith('.mxf'):
            mxf_file_path = os.path.join(mxf_directory, filename)
            audio_filename = os.path.splitext(filename)[0] + '.wav'
            output_file_path = os.path.join(destination_folder, audio_filename)
            extract_audio_from_mxf(mxf_file_path, output_file_path)

    #SCRIPT 3
    with open(file_path, "r") as json_file:
        data = json.load(json_file)

    tracks = data["tracks"]

    for track in data['tracks']:
        for item in track['items']:
            if 'source' in item:
                filename = os.path.basename(item['source']).replace('mxf', 'wav')
                new_source = filename
                item['source']= new_source
                print(item['source'])

    with open(file_path, "w") as json_file:
        json.dump(data, json_file, indent=4)

    #SCRIPT 4
    with open(file_path, "r") as json_file:
        data = json.load(json_file)

    # Start building the Reaper project file
    reaper_project = '''<REAPER_PROJECT 0.1 "7.15/OSX64-clang" 1746964994\n
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
      CURSOR 36
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
      SAMPLERATE 48000 0 0
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
      <MASTERPLAYSPEEDENV
        EGUID {D4B273DC-4864-8147-9834-B9721B266C59}
        ACT 0 -1
        VIS 0 1 1
        LANEHEIGHT 0 0
        ARM 0
        DEFSHAPE 0 -1 -1
      >
      <TEMPOENVEX
        EGUID {348B8534-B465-0A47-A8E6-752B78926A42}
        ACT 0 -1
        VIS 1 0 1
        LANEHEIGHT 0 0
        ARM 0
        DEFSHAPE 1 -1 -1
      >
      <PROJBAY
      >
    '''

    # Add tracks
    #reaper_project += '  <TRACKS {}\n'.format(len(data['tracks']))
    for track in data['tracks']:
        reaper_project += '   <TRACK\n'
        reaper_project += '    NAME {}\n'.format(track['name'].replace(' ', '\u00A0'))
        reaper_project += '    PEAKCOL 0\n'
        reaper_project += '    BEAT -1\n'
        reaper_project += '    AUTOMODE 0\n'
        reaper_project += '    VOLPAN 1 0 -1 -1 1\n'
        reaper_project += '    MUTESOLO 0 0 0\n'
        reaper_project += '    IPHASE 0\n'
        reaper_project += '    PLAYOFFS 0 1\n'
        reaper_project += '    ISBUS 0 0\n'
        reaper_project += '    BUSCOMP 0 0 0 0 0\n'
        reaper_project += '    SHOWINMIX 1 0.6667 0.5 1 0.5 0 0 0\n'
        reaper_project += '    SEL 1\n'
        reaper_project += '    REC 0 0 1 0 0 0 0 0\n'
        reaper_project += '    VU 2\n'
        reaper_project += '    TRACKHEIGHT 0 0 0 0 0 0\n'
        reaper_project += '    INQ 0 0 0 0.5 100 0 0 100\n'
        reaper_project += '    NCHAN 2\n'
        reaper_project += '    FX 1\n'
        reaper_project += '    PERF 0\n'
        reaper_project += '    MIDIOUT -1\n'
        reaper_project += '    MAINSEND 1 0\n'    
        #reaper_project += '   PANNING {}\n'.format(track['panning'])
        
        # Add items
        #reaper_project += '      <ITEM {}\n'.format(len(track['items']))
        for item in track['items']:
            file_name = os.path.basename(item['source'])
            reaper_project += '       <ITEM\n'
            reaper_project += '        POSITION {}\n'.format(item['position'])
            reaper_project += '        SNAPOFFS 0\n'
            reaper_project += '        LENGTH {}\n'.format(item['duration'])
            reaper_project += '        LOOP 0\n'
            reaper_project += '        ALLTAKES 0\n'
            reaper_project += '        FADEIN 1 0.01 0 1 0 0 0\n'
            reaper_project += '        FADEOUT 1 0.01 0 1 0 0 0\n'
            reaper_project += '        MUTE 0 0\n'
            reaper_project += '        SEL 0\n'
            reaper_project += '        IID 1\n'
            reaper_project += '        NAME {}\n'.format(file_name)
            reaper_project += '        VOLPAN 1 0 1 -1\n'
            reaper_project += '        SOFFS 0\n'
            reaper_project += '        PLAYRATE 1 1 0 -1 0 0.0025\n'
            reaper_project += '        CHANMODE 0\n'
            reaper_project += '        <SOURCE WAVE\n'
            reaper_project += '        FILE "{}"\n'.format(item['source'])
            reaper_project += '        >\n'
            #reaper_project += '       OFFSET {}\n'.format(item['offset'])
            reaper_project += '        >\n'
        reaper_project += '      >\n'
        
    reaper_project += '  >\n'
    reaper_project += '>\n'

    # Print the resulting Reaper project file
    print(reaper_project)

    filenameReaper = "my_project.rpp"  # Specify the desired file name with the ".rpp" extension

    #destination folder for reaper file
    destination_folder_reaper_file = os.path.join(destination_folder, filenameReaper)

    with open(destination_folder_reaper_file, "w") as file:
        file.write(reaper_project)

