import string
import urllib.request
import binascii
import cherrypy
import time
import subprocess
import json
from threading import Timer

DEF_VOL = 40
DEF_SRC = [1, 0, 3] # Database ID, Container ID, Item ID
START_CMD = ["/bin/echo -n 'P' > /home/pi/.config/pianobar/ctl"]
END_CMD = ["/bin/echo -n 'S' > /home/pi/.config/pianobar/ctl"]
SPKR_TAG = ' (A)' # Speaker with this tag included in All-On
SPKR_TAG_X = ' (X)' # Speakers with this tag not included in All-On
SPKR_TAG_LEN = len(SPKR_TAG)
PENDING_SRC_VALID_SEC = 1800 # Pending source will revert to default after this.
PIANOBAR_CONFIG = "/home/pi/.config/pianobar/"

class AudioCtl(object):

    def __init__(self, server='localhost', port='3689'):
        # Settings
        self.server = server
        self.port = port
        
        # Object variables
        self.spkrs = []
        self.master_vol = 0
        self.last_login = 0
        self.last_get_spkrs = 0
        self.active_spkrs = []
        self.playing = False
        self.trackname = ""
        self.src = DEF_SRC[:]
        self.pending_src = DEF_SRC[:]
        self.pending_src_set = time.time()
        self.update_time = time.time()
        self.last_req = time.time()
        self.last_poll = time.time()
        self.reqs = []
        self.now_playing = {'artist':'', 'love':'0'}
        self.stationlist = {}
        self.poll_pianobar = True
        
        # Get forked_daapd state
        self.get_spkrs()
        self.get_mstr_vol()
        self.getplaying()
        
        # Poll Pianobar
        Timer(0, self.pand_poll).start()
        
        return

    @cherrypy.expose
    def index(self):
        fn = os.path.join(os.path.dirname(__file__), 'static/audioctl2.html')
        return open(fn).read()
    
    def request(self, url):
        start_time = time.time()
        print('Start request: {}'.format(url))
        self.last_req = start_time
        url = 'http://{0}:{1}/{2}'.format(self.server, self.port, url)
        try:
            s = urllib.request.urlopen(url)
        except urllib.error.HTTPError:
            self.login()
            s = urllib.request.urlopen(url)
        print('End request: {}'.format(str(time.time() - start_time)))
        return s
        
    def login(self):
        start_time = time.time()
        print('Start login')
        url = ("http://{0}:{1}/login?pairing-guid=0x1&request-session-id=50"
               "").format(self.server, self.port)
        s = urllib.request.urlopen(url)
        s.close()
        print('End login: {}'.format(str(time.time() - start_time)))
        return
    
    @cherrypy.expose
    def poll(self, last_update):
        start_time = time.time()
        self.last_poll = start_time
        print('Start poll')
        if start_time - self.last_get_spkrs > 5:
            self.get_spkrs()
        last = float(last_update)
        exp_time = start_time + 20
        while time.time() < exp_time:
            if self.update_time > last:
                print('End poll with update: {}'.format(str(time.time() - start_time)))
                print('Response: {}'.format(json.dumps([self.master_vol, self.spkrs, self.update_time, self.now_playing, self.stationlist])))
                return json.dumps([self.master_vol, self.spkrs, self.update_time, self.now_playing, self.stationlist])
            time.sleep(.2)
        print('End poll without update: {}'.format(str(time.time() - start_time)))
        return json.dumps('')
    
    def pand_poll(self):
        i = 9
        while self.poll_pianobar:
            if time.time() - self.last_poll < 31: #A client is active
                self.pand_parse_np()
                i+= 1
                if i > 9: #Every tenth time, update the station list
                    self.pand_parse_sl()
                    i = 0
            time.sleep(2)
    
    def pand_parse_np(self):
        prev = self.now_playing['artist'] + self.now_playing['love']
        fn = PIANOBAR_CONFIG + "nowplaying"
        np = open(fn)
        self.now_playing['artist'] = np.readline()[:-2]
        self.now_playing['title'] = np.readline()[:-2]
        self.now_playing['station'] = np.readline()[:-2]
        self.now_playing['love'] = np.readline()[:-2]
        self.now_playing['coverurl'] = np.readline()[:-2]
        self.now_playing['album'] = np.readline()[:-1]
        np.close()
        if prev != self.now_playing['artist'] + self.now_playing['love']:
            self.update_time = time.time()
        return
            
    def pand_parse_sl(self):
        prev_len = len(self.stationlist)
        fn = PIANOBAR_CONFIG + "stationlist"
        sl = open(fn)
        self.stationlist.clear()
        while True:
            line = sl.readline()
            paren_index = line.find(')')
            if paren_index > 0:
                id = line[:paren_index]
                name = line[paren_index + 2:-1]
                self.stationlist[str(id)] = name
            else:
                break
        sl.close()
        if prev_len != len(self.stationlist):
            self.update_time = time.time()
        return
    
    @cherrypy.expose
    def pand_down(self): # Call to thumb-down current song
        cmd = "/bin/echo '-' > " + PIANOBAR_CONFIG + "ctl"
        print('Calling: {}'.format(cmd))
        subprocess.call(cmd, shell=True)
        return 'OK'
        
    @cherrypy.expose
    def pand_up(self): # Call to thumb-up current song
        cmd = "/bin/echo '+' > " + PIANOBAR_CONFIG + "ctl"
        print('Calling: {}'.format(cmd))
        subprocess.call(cmd, shell=True)
        time.sleep(2)
        self.pand_parse_np()
        return 'OK'
        
    @cherrypy.expose
    def pand_playpause(self): #Call to toggle play/pause
        if self.src == DEF_SRC:
            cmd = "/bin/echo 'p' > " + PIANOBAR_CONFIG + "ctl"
            print('Calling: {}'.format(cmd))
            subprocess.call(cmd, shell=True)
        else:
            self.startplaying(*DEF_SRC)
        return 'OK'
        
    @cherrypy.expose
    def pand_skip(self): #Call to skip to next song
        cmd = "/bin/echo 'n' > " + PIANOBAR_CONFIG + "ctl"
        print('Calling: {}'.format(cmd))
        subprocess.call(cmd, shell=True)
        return 'OK'
        
    @cherrypy.expose
    def pand_station(self, id): #Call to change to staion 'id'
        cmd = "/bin/echo 's" + id + "' > " + PIANOBAR_CONFIG + "ctl"
        print('Calling: {}'.format(cmd))
        subprocess.call(cmd, shell=True)
        return 'OK'
    
    @cherrypy.expose
    def reboot(self): #Call to reboot the system
        cmd = "sudo shutdown -r now"
        print('Calling: {}'.format(cmd))
        subprocess.call(cmd, shell=True)
        return 'OK'

    @cherrypy.expose
    def touch(self):
        print('Touch')
        self.update_time = time.time()
        return 'OK'
    
    def get_pend_src(self):
        if time.time() - self.pending_src_set > PENDING_SRC_VALID_SEC:
            return DEF_SRC[:]
        # else
        return self.pending_src[:]
    
    def set_pend_src(self, src):
        self.pending_src = src[:];
        self.pending_src_set = time.time()
	
    def read_dict(self, s, slen):
        start_time = time.time()
        dict = {}
        sread = 0
        while sread < slen:
            name = s.read(4).decode()
            vlen = int(binascii.hexlify(s.read(4)), 16)
            if name in ['minm']:
                value = s.read(vlen).decode()
            elif name in ['cmvo', 'caia', 'caiv']:
                value = int(binascii.hexlify(s.read(vlen)), 16)
            elif name in ['msma']:
                value = '0x' + binascii.hexlify(s.read(vlen)).decode()
            else:
                value = s.read(vlen)
            sread += (8 + vlen)
            dict[name] = value
        print('read_dict: {}'.format(str(time.time() - start_time)))
        return dict

    @cherrypy.expose
    def startplaying(self, dbid, contid, itemid):
        start_time = time.time()
        print("Start startplaying")
        start_src = [int(dbid), int(contid), int(itemid)]
        if len(self.active_spkrs) == 0:
            # Don't start playing to avoid forked-daapd activating a speaker
            self.set_pend_src(start_src)
        else:
            url = ("ctrl-int/1/playspec?"
                   "database-spec='dmap.persistentid:{0}'&"
                   "container-spec='dmap.persistentid:{1}'&"
                   "container-item-spec='dmap.persistentid:{2}'&"
                   "session-id=50").format(hex(start_src[0]), \
                                           hex(start_src[1]), hex(start_src[2]))
            s = self.request(url)
            s.close()
            self.getplaying()
            if start_src == DEF_SRC:
                # If playing the default source, execute the default start command
                print('Calling: {}'.format(str(START_CMD)))
                subprocess.call(START_CMD, shell=True)
            else:
                # Else, execute the default end command
                print('Calling: {}'.format(str(END_CMD)))
                subprocess.call(END_CMD, shell=True)
        print('End startplaying: {}'.format(str(time.time() - start_time)))
        return 'OK'
        
    @cherrypy.expose
    def endplaying(self, dbid='', contid='', itemid=''):
        start_time = time.time()
        print("Start endplaying")
        self.getplaying()
        if dbid == '':
            stop_cur = True
            end_src = self.src
        else:
            end_src = [int(dbid), int(contid), int(itemid)]
        if end_src == DEF_SRC:
            # Stopping the default source, so execute the end command.
            print('Calling: {}'.format(str(END_CMD)))
            subprocess.call(END_CMD, shell=True)
        if stop_cur:
            # Stopping the currently-playing source, so pause.
            url = "ctrl-int/1/pause?session-id=50"
            s = self.request(url)
            s.close()
        print('End endplaying: {}'.format(str(time.time() - start_time)))
        return 'OK'
    
    def getplaying(self):
        start_time = time.time()
        print("Start getplaying")
        url = "ctrl-int/1/playstatusupdate?revision-number=1&session-id=50"
        s = self.request(url)
        name = s.read(4)
        slen = int(binascii.hexlify(s.read(4)), 16)
        if name != b'cmst':
            return "Unexpected response: name = " + str(name) + "\n"
        sread = 0
        while sread < slen:
            name = s.read(4)
            vlen = int(binascii.hexlify(s.read(4)), 16)
            data = s.read(vlen)
            if name == b'caps': #Play status
                self.playing = int(binascii.hexlify(data), 16) == 4
            elif name == b'cann': #Track name
                self.trackname = data.decode()
            elif name == b'canp': #Track id
                self.src[0] = int('0x' + binascii.hexlify(data[0:4]).decode(), 16)
                self.src[1] = int('0x' + binascii.hexlify(data[4:8]).decode(), 16)
                self.src[2] = int('0x' + binascii.hexlify(data[12:16]).decode(), 16)
            sread += (8 + vlen)
        s.close()
        print('End getplaying: {}'.format(str(time.time() - start_time)))
        return
        
    @cherrypy.expose
    def act_spkr(self, id, vol=DEF_VOL):
        start_time = time.time()
        print("Start act_spkr")
        self.get_spkrs(force = True)
        first_spkr = True if len(self.active_spkrs) == 0 else False
        print('first_spkr: {}'.format(str(first_spkr)))
        if id == 'all':
            self.active_spkrs = []
            for spkr in self.spkrs:
                if not spkr['excl'] or 'caia' in spkr:
                    self.active_spkrs.append(spkr['msma'])
        else:
            self.active_spkrs.append(id)
        ids = ','.join(str(x) for x in self.active_spkrs)
        url = "ctrl-int/1/setspeakers?session-id=50&speaker-id={0}".format(ids)
        s = self.request(url)
        s.close()
        if first_spkr:
            # If activating the first speaker, start the pending source, and
            # then reset it to default.
            self.startplaying(*self.get_pend_src())
            self.set_pend_src(DEF_SRC)
        new_ids = self.active_spkrs if id == 'all' else [id]
        # Set initial volume in multiple steps to account for device wake time.
        for i in range(4):
            for new_id in new_ids:
                flag_update = True if i == 0 else False
                Timer(i + .5, self.spkr_vol, [vol, new_id, flag_update]).start()
        self.get_spkrs(force = True)
        # Update master volume some time after volumes have been set.
        Timer(1.5, self.get_mstr_vol).start()
        print('End act_spkr: {}'.format(str(time.time() - start_time)))
        return 'OK'
    
    @cherrypy.expose
    def deact_spkr(self, id):
        start_time = time.time()
        print("Start deact_spkr")
        if id == 'all':
            ids = ''
        else:
            self.get_spkrs(force = True)
            self.active_spkrs.remove(id)
            ids = ','.join(str(x) for x in self.active_spkrs)
        url = "ctrl-int/1/setspeakers?session-id=50&speaker-id={0}".format(ids)
        s = self.request(url)
        s.close()
        self.get_spkrs(force = True)
        self.get_mstr_vol()
        print('master_vol: {}'.format(str(self.master_vol)))
        if len(self.active_spkrs) == 0:
            self.endplaying()
        self.update_time = time.time()
        print('End deact_spkr: {}'.format(str(time.time() - start_time)))
        return 'OK'

    @cherrypy.expose
    def set_mstr_vol(self, vol):
        start_time = time.time()
        print("Start set_mstr_vol")
        url = "ctrl-int/1/setproperty?session-id=50&dmcp.volume={0}".format(vol)
        s = self.request(url)
        s.close()
        self.get_spkrs(force = True)
        self.master_vol = int(vol)
        self.update_time = time.time()
        print('End set_mstr_vol: {}'.format(str(time.time() - start_time)))
        return 'OK'

    @cherrypy.expose
    def spkr_vol(self, vol, id, external=True):
        start_time = time.time()
        print("Start spkr_vol")
        vol = int(vol)
        master_vol = self.master_vol
        self.get_spkrs()
        vols = []
        for spkr in self.spkrs:
            if 'caia' in spkr:
                vols.append(spkr['cmvo'])
            if spkr['msma'] == id:
                cur_vol = int(spkr['cmvo'] * master_vol / 100 + .5)
        vols.sort(reverse = True)
        max_vol = int(vols[0] * master_vol / 100 + .5) if len(vols) > 0 else 0
        second_max_vol = int(vols[1] * self.master_vol / 100 + .5) if len(vols) > 1 else 0
        # If speaker is or will become the loudest
        if cur_vol == max_vol or vol > master_vol:
            # If speaker will no longer be the loudest
            if vol < second_max_vol:
                # First equalize volume with second loudest
                self.abs_vol(second_max_vol, id)
                # Then decrease relative volume of this speaker
                rel_vol = int(vol * 100 / second_max_vol + .5)
                self.rel_vol(rel_vol, id)
            else:
                # Set the speaker along with the master volume
                self.abs_vol(vol, id)
        else:
            # Just set the relative volume
            rel_vol = int(vol * 100 / master_vol + .5)
            self.rel_vol(rel_vol, id)
        if external:
            self.update_time = time.time()
        print('End spkr_vol: {}'.format(str(time.time() - start_time)))
        return 'OK'

    def abs_vol(self, vol, id):
        start_time = time.time()
        print('Start abs_vol')
        url = ("ctrl-int/1/setproperty?"
               "dmcp.volume={0}&include-speaker-id={1}&"
               "session-id=50").format(str(vol), str(int(id, 16)))
        s = self.request(url)
        s.close()
        old_master_vol = self.master_vol
        self.master_vol = vol
        # Reset other relative volumes (faster than calling get_spkrs)
        for spkr in self.spkrs:
            if spkr['msma'] == id:
                spkr['cmvo'] = 100
            else:
                spkr['cmvo'] = int(spkr['cmvo'] * old_master_vol / vol + .5)
        print("End abs_vol: " + str(time.time() - start_time))
        return
        
    def rel_vol(self, vol, id):
        start_time = time.time()
        print('Start rel_vol')
        url = ("ctrl-int/1/setproperty?"
               "speaker-id={0}&dmcp.volume={1}&"
               "session-id=50").format(str(int(id, 16)), vol)
        s = self.request(url)
        s.close()
        # Store new volume (faster than calling get_spkrs)
        for spkr in self.spkrs:
            if spkr['msma'] == id:
                spkr['cmvo'] = vol
                break
        print('End rel_vol: {}'.format(str(time.time() - start_time)))
        return

    def get_mstr_vol(self):
        start_time = time.time()
        print('Start get_mstr_vol')
        url = "ctrl-int/1/getproperty?session-id=50&properties=dmcp.volume"
        s = self.request(url)
        name = s.read(4)
        slen = int(binascii.hexlify(s.read(4)), 16)
        if name != b'cmgt':
            return -1
        sread = 0
        while sread < slen:
            name = s.read(4)
            vlen = int(binascii.hexlify(s.read(4)), 16)
            value = s.read(vlen)
            if name == b'cmvo': #Master Volume
                master_vol = int(binascii.hexlify(value), 16)
                master_vol = 0 if master_vol == 4294967295 else master_vol
            sread += (8 + vlen)
        s.close()
        self.master_vol = master_vol
        print('End get_mstr_vol: {}'.format(str(time.time() - start_time)))
        return

    def get_spkrs(self, force=False):
        start_time = time.time()
        print('Start get_spkrs')
        if start_time - self.last_get_spkrs < 2 and not force:
            # Speed up volume changes by assuming speakers are current
            self.last_get_spkrs = start_time
            print('End get_spkrs: {}'.format(str(time.time() - start_time)))
            return
        self.last_get_spkrs = start_time
        url = "ctrl-int/1/getspeakers?session-id=50"
        s = self.request(url)
        name = s.read(4)
        slen = int(binascii.hexlify(s.read(4)), 16)
        if name != b'casp':
            return "Unexpected response: name = " + str(name) + "\n"
        prev_spkrs = [spkr['msma'] for spkr in self.spkrs]
        prev_active_spkrs = self.active_spkrs[:]
        self.spkrs = []
        self.active_spkrs = []
        sread = 0
        while sread < slen:
            name = s.read(4)
            vlen = int(binascii.hexlify(s.read(4)), 16)
            if name == b'mstt':
                #Status
                status = int(binascii.hexlify(s.read(vlen)), 16)
                if status != 200:
                    return -1
            elif name == b'mdcl':
                #Dictionary
                spkr = self.read_dict(s, vlen)
                if SPKR_TAG in spkr['minm'] or SPKR_TAG_X in spkr['minm']:
                    spkr['excl'] = True if SPKR_TAG_X in spkr['minm'] else False
                    spkr['minm'] = spkr['minm'][:-SPKR_TAG_LEN]
                    if 'caia' in spkr:
                        self.active_spkrs.append(spkr['msma'])
                    self.spkrs.append(spkr)
            else:
                return -1
            sread += (8 + vlen)
        s.close()
        self.spkrs.sort(key=lambda spkr: spkr['minm'])
        self.active_spkrs.sort()
        # If the list of available speakers has changed, flag the update.
        if [spkr['msma'] for spkr in self.spkrs] != prev_spkrs:
            self.get_mstr_vol()
            self.update_time = time.time()
        # If the list of active speakers has changed, flag update.
        if self.active_spkrs != prev_active_spkrs:
            print('Active speakers changed.')
            # If no active speakers, end playing.
            if len(self.active_spkrs) == 0:
                self.endplaying()
            self.get_mstr_vol()
            self.update_time = time.time()
        print('End get_spkrs: {}'.format(str(time.time() - start_time)))
        return

        
import os.path
conf = os.path.join(os.path.dirname(__file__), 'allplay.conf')
cherrypy.engine.autoreload.frequency=10
		
if __name__ == '__main__':
    cherrypy.quickstart(AudioCtl(), config=conf)
    #self.poll_pianobar = False
