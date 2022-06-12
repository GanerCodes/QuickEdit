add_library('minim')
from minim import *

from collections import OrderedDict
import subprocess, threading, time, json, sys, re, os

tmp_dir = "/tmp/QuickEdit"
if not os.path.isdir(tmp_dir):
    os.mkdir(tmp_dir)
os.chdir(tmp_dir)

original_video_filename = os.environ["quickedit_import_vid"]
export_path = os.environ["quickedit_export_vid"]

disable_export = False
audio_ext = "mp3"
ffmpeg_audio_info_command = "ffprobe -hide_banner -print_format json -show_format -show_streams -select_streams a {}"
ffmpeg_frame_command = "ffmpeg -hide_banner -loglevel error -y -i {} -vf 'scale=128:-1:flags=neighbor,fps=60' -map 0:v:0 {}"
ffmpeg_audio_command = "ffmpeg -hide_banner -loglevel error -y -i {} {}"
filename_regex = re.compile("image_([0-9]{3,})\\.jpg")
frame_load_state = "..."

isPaused = False
amixAudio = False
playStartTime = playStartPos = frame_num = 0
active_tracks, cuts = {}, {}

base_directory = os.path.join(tmp_dir, "data")
image_directory = os.path.join(base_directory, "image")
audio_directory = os.path.join(base_directory, "audio")
clips_directory = os.path.join(base_directory, "clips")

quote = lambda x: '"' + str(x) + '"'

def init_frames():
    global frame_load_state, frame_list, frame_map, audio_map, minim
    
    frame_load_state = "Extracting frames"
    [os.path.isdir(d) or os.mkdir(d) for d in (base_directory, image_directory, audio_directory, clips_directory)]
    
    audio_tracks = json.loads(
        subprocess.check_output(
            ffmpeg_audio_info_command.format(quote(original_video_filename)),
            shell=True).decode())
    
    audio_map = OrderedDict((
        stream['tags']['title'] if 'title' in stream['tags'] else "track_{}".format(i),
        os.path.join(audio_directory, "audio_{:03d}.{}".format(i, audio_ext))
     ) for i, stream in enumerate(audio_tracks['streams']))
    
    disable_export or os.system(ffmpeg_frame_command.format(
        quote(original_video_filename),
        os.path.join(image_directory, "image_%06d.jpg")))
    
    frame_load_state = "Extracting audio"
    disable_export or os.system(ffmpeg_audio_command.format(quote(original_video_filename), ' '.join(
        "-vn -ac 2 -ar 48000 -f mp3 -map 0:a:{} {}".format(i, v) for i, v in enumerate(audio_map.values())
    )))
    
    frame_list = sorted(
        filter(
            filename_regex.match,
            os.listdir(image_directory)),
        key=(lambda x: int(filename_regex.search(x).groups(0)[0])))
    
    frame_load_state = "Loading frames"
    frame_map = {k: loadImage(os.path.join(image_directory, k)) for k in frame_list}
    
    frame_load_state = "Loading audio"
    minim = Minim(this)
    for k, v in audio_map.items():
        audio_map[k] = minim.loadFile(v)
        audio_map[k].setGain(-8.0)
    
    frame_load_state = None

def info(*objs):
    for obj in objs:
        print(str(obj) + ':\n\t' + ('\n\t'.join("{} [{}]".format(i, type(getattr(obj, i))) for i in dir(obj))) + '\n')

def getNormPos():
    return (playStartPos + (time.time() - playStartTime)) / (len(frame_list) / 60.0)

def cue_track(loc=0, check=True):
    global playStartTime, playStartPos, audio_map
    if check:
        playStartTime = time.time()
        playStartPos  = (loc * len(frame_list)) / 60.0
    
    vs = active_tracks.values()
    for track in vs:
        track.cue(int(0.5 * loc * track.length()))
    return vs

def play(loc=0):
    for track in cue_track(loc):
        if not track.isPlaying():
            track.play()

def pause(loc=None):
    if loc is None:
        loc = getNormPos()
    for track in active_tracks.values():
        track.pause()

def setup():
    threading.Thread(target=init_frames).start()
    g.surface.setResizable(True)
    size(512, 512, P2D)
    imageMode(CENTER)

def draw():
    global frame_load_state, frame_list, frame_num, frame_map, audio_map, playStartPos, playStartTime
    
    background(0)
    if frame_load_state:
        fill(255)
        text(frame_load_state, 100, 100)
        return
    if frame_load_state is None:
        frame_load_state = False
        k, v = audio_map.items()[0]
        active_tracks[k] = v
        play()
    
    prop = playStartPos if isPaused else getNormPos()
    
    frame_num  = constrain(int(prop * len(frame_list)), 0, len(frame_list) - 1)
    frame = frame_map[frame_list[frame_num]]
    
    mins = min(float(width) / frame.width, float(height - 125) / frame.height)
    sz_x, sz_y = int(frame.width  * mins), int(frame.height * mins)
    image(frame, width / 2, sz_y / 2, sz_x, sz_y)
    
    strokeWeight(3)
    
    stroke(0, 0, 255)
    line(0, height - 30, prop * width, height - 30)
    
    stroke(255, 0, 0)
    line(0, height - 75, width, height - 75)
    stroke(0, 255, 0)
    d = float(width) / len(frame_list)
    px = -1
    for i in sorted(cuts.keys()):
        x = d * i
        if px != -1:
            line(px, height - 75, x, height - 75)
            px = -1
        else:
            px = x
        line(x, height - 80, x, height - 65)
    
    fillB = lambda v: fill(18, 222, 18) if v else fill(222, 18, 18)
    
    x = 3
    for v in audio_map:
        fillB(v in active_tracks)
        text(v, x, height - 7)
        x += textWidth(v + '   ')
    
    fillB(amixAudio)
    text("Amix", width - textWidth("Amix") - 4, height - 7)

def keyPressed():
    global isPaused, playStartPos, amixAudio, frame_num
    if frame_load_state is not False: return
    
    if keyCode in range(49, 58):
        num = keyCode - 49
        if num < len(audio_map):
            k, v = audio_map.items()[num]
            if k in active_tracks:
                if active_tracks[k].isPlaying():
                    active_tracks[k].pause()
                del active_tracks[k]
            else:
                active_tracks[k] = v
                if not isPaused:
                    v.play()
                v.cue(int(0.5 * getNormPos() * v.length()))
        return
    
    if keyCode == 32:
        isPaused = not isPaused
        if isPaused:
            playStartPos = getNormPos()
            pause()
        else:
            play(playStartPos)
        return
    
    if key == 'a':
        amixAudio = not amixAudio
        return
    if key == 'e':
        def render():
            global frame_load_state
            
            frame_load_state = "Generating clips"
            
            new_cuts = []
            
            l = sorted(cuts.keys())
            px = l[0]
            for i in l[1:]:
                if px != -1:
                    if i - px > 0:
                        new_cuts.append((px, i))
                    px = -1
                else:
                    px = i
            
            m = 1.0 / 60.0
            q = [(i,
                m * s,
                m * (e - s)) for i, (s, e) in enumerate(new_cuts)]
            
            vid_paths = [os.path.join(
                clips_directory,
                "{}.mp4".format(i[0])
            ) for i in q]
            
            g = map(audio_map.keys().index, active_tracks)
            if amixAudio:
                aud_list = '-map 0:a'
                amix_pass = " -filter_complex {}amix=inputs={} ".format(
                    ''.join(
                        "[0:a:{}]".format(i) for i in g),
                    len(g))
            else:
                aud_list = ' '.join("-map 0:a:{}".format(i) for i in g)
                amix_pass = ""
            
            cmd = "ffmpeg -y -hide_banner -loglevel warning -i {}{} {}".format(
                quote(original_video_filename),
                amix_pass,
                " ".join(
                    "-map 0:v {} -ss {} -t {} {}".format(
                        aud_list, s, d, vid_paths[i]) for i, s, d in q))
            
            os.system(cmd)
            
            frame_load_state = "Joining clips"
            
            file_list = os.path.join(clips_directory, 'clip_list.txt')
            f = open(file_list, 'w')
            f.write("\n".join("file '{}'".format(os.path.abspath(i)) for i in vid_paths))
            f.close()
            os.system("ffmpeg -hide_banner -loglevel warning -y -safe 0 -f concat -i {} -map 0:v {} {}".format(
                quote(file_list),
                aud_list,
                quote(export_path)))
            frame_load_state = False
            print("Rendered")
        
        threading.Thread(target=render).start()
        
def mouseClicked():
    global playStartPos, isPaused
    if frame_load_state is not False: return
    
    if mouseButton == LEFT:
        p = float(mouseX) / width
        if isPaused:
            playStartPos = p
            cue_track(p, check=False)
        else:
            play(p)
        return
    if mouseButton == RIGHT:
        cuts[frame_num] = 1
        return
    if mouseButton == CENTER:
        v = 0
        for i in sorted(cuts.keys()):
            if i <= frame_num:
                v = i
            else:
                break
        if v in cuts:
            del cuts[v]
        elif v == 0:
            cuts[v] = 1
        return
