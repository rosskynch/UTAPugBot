import collections
import time
import asyncpg
from datetime import datetime
from datetime import timezone
from datetime import timedelta
import functools
import itertools
import os
import logging
import sys
import random
import re
import requests # should replace with aiohttp. See https://discordpy.readthedocs.io/en/latest/faq.html#what-does-blocking-mean
import json
import discord
import socket
import dns.resolver
from discord.ext import commands, tasks
from cogs import admin

# Commands and maps from the IRC bot:
#
#<UTAPugbot> !pughelp !reset !setmaps !setplayers !listmaps !pug !letter !status !server !captainmode !launchprotect !version
#<UTAPugbot> during pug setup: !player !randplayer !map !randmap !showteams !showmaps !captain
#
#Maplist:
#Server map list is: 1.AS-AsthenosphereSE 2.AS-AutoRip 3.AS-Ballistic 4.AS-Bridge 5.AS-Desertstorm 6.AS-Desolate][ 7.AS-Frigate
#8.AS-GolgothaAL 9.AS-Golgotha][AL 10.AS-Mazon 11.AS-RiverbedSE 12.AS-Riverbed]l[AL 13.AS-Rook 14.AS-Siege][
#15.AS-Submarinebase][ 16.AS-SaqqaraPE_preview3 17.AS-SnowDunes][AL_beta 18.AS-LostTempleBetaV2 19.AS-TheDungeon]l[AL
#20.AS-DustbowlALRev04 21.AS-NavaroneAL 22.AS-TheScarabSE 23.AS-Vampire 24.AS-ColderSteelSE_beta3 25.AS-HiSpeed
#26.AS-NaliColony_preview5 27.AS-LavaFort][PV 28.AS-BioassaultSE_preview2 29.AS-Razon_preview3 30.AS-Resurrection
#31.AS-WorseThings_preview 32.AS-GekokujouAL][

DEFAULT_PLAYERS = 12
DEFAULT_MAPS = 7
DEFAULT_PICKMODETEAMS = 1 # Fairer for even numbers (players should be even, 1st pick gets 1, 2nd pick gets 2)
DEFAULT_PICKMODEMAPS = 3 # Fairer for odd numbers (maps are usually odd, so 2nd pick should get more picks)

DEFAULT_GAME_SERVER_REF = 'pugs1'
DEFAULT_GAME_SERVER_IP = '0.0.0.0'
DEFAULT_GAME_SERVER_PORT = '7777'
DEFAUlT_GAME_SERVER_NAME = 'Unknown Server'
DEFAULT_POST_SERVER = 'https://utassault.net'
DEFAULT_POST_TOKEN = 'NoToken'
DEFAULT_THUMBNAIL_SERVER = '{0}/pugstats/images/maps/'.format(DEFAULT_POST_SERVER)
DEFAULT_CONFIG_FILE = 'servers/config.json'

# Valid modes with default config
Mode = collections.namedtuple('Mode', 'maxPlayers friendlyFireScale mutators')
MODE_CONFIG = {
    'stdAS': Mode(20, 0, None),
    'proAS': Mode(20, 100, None),
    'ASplus': Mode(20, 0, 'LeagueAS-SP.ASPlus'),
    'proASplus': Mode(20, 100, 'LeagueAS-SP.ASPlus'),
    'iAS': Mode(20, 0, 'LeagueAS-SP.iAS'),
    'ZPiAS': Mode(20, 0, 'ZeroPingPlus103.ColorAccuGib')
}

RED_PASSWORD_PREFIX = 'RP'
BLUE_PASSWORD_PREFIX = 'BP'
DEFAULT_SPECTATOR_PASSWORD = 'pug'
DEFAULT_NUM_SPECTATORS = 4
DEFAULT_RED_PASSWORD = RED_PASSWORD_PREFIX + '000'
DEFAULT_BLUE_PASSWORD = BLUE_PASSWORD_PREFIX + '000'

# Map list:
#  List of League Assault default maps.
#  This hardcoded list will be replaced through JSON config upon bot load

DEFAULT_MAP_LIST = [
    'AS-AsthenosphereSE',
    'AS-AutoRip',
    'AS-Ballistic',
    'AS-Bridge',
    'AS-Desertstorm',
    'AS-Desolate][',
    'AS-Frigate',
    'AS-GolgothaAL',
    'AS-Golgotha][AL',
    'AS-Guardia',
    'AS-GuardiaAL',
    'AS-HiSpeed',
    'AS-Mazon',
    'AS-OceanFloor',
    'AS-OceanFloorAL',
    'AS-Overlord',
    'AS-RiverbedSE',
    'AS-Riverbed]l[AL',
    'AS-Rook',
    'AS-Siege][',
    'AS-Submarinebase][',
    'AS-TheDungeon]l[AL',
]

REGULAR_MAP_LIST = [
    'AS-AsthenosphereSE',
    'AS-AutoRip',
    'AS-AutoRipSE_beta5',
    'AS-Ballistic',
    'AS-Bridge',
    'AS-BridgePV_beta6c',
    'AS-Desertstorm',
    'AS-Desolate][',
    'AS-Frigate',
    'AS-GolgothaAL',
    'AS-Golgotha][AL',
    'AS-Guardia',
    'AS-GuardiaAL',
    'AS-HiSpeed',
    'AS-Mazon',
    'AS-OceanFloor',
    'AS-OceanFloorAL',
    'AS-Overlord',
    'AS-RiverbedSE',
    'AS-Riverbed]l[AL',
    'AS-Riverbed]l[PE_beta3',
    'AS-Rook',
    'AS-Siege][',
    'AS-Submarinebase][',
    'AS-TheDungeon]l[AL',
]

# Server list:
#  List of Tuples, first element is the API reference, second element is the placeholder
#  Name / Description of the server, which is updated after a successful check.
#  This hardcoded list will be replaced through JSON config upon bot load, and subsequently
#  verified against the online API.

DEFAULT_SERVER_LIST = [
    ('pugs1','UTA Pug Server 1.uk','unreal://pug1.utassault.net',False,'')
]

PICKMODES = [
        [0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1],
        [0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0],
        [0, 1, 1, 0, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1],
        [0, 1, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0]]
MAX_PLAYERS_LIMIT = len(PICKMODES[0]) + 2

PLASEP = '\N{SMALL ORANGE DIAMOND}'
MODSEP = '\N{SMALL BLUE DIAMOND}'
OKMSG = '\N{OK HAND SIGN}'

DISCORD_MD_CHARS = '*~_`'
DISCORD_MD_ESCAPE_RE = re.compile('[{}]'.format(DISCORD_MD_CHARS))
DISCORD_MD_ESCAPE_DICT = {c: '\\' + c for c in DISCORD_MD_CHARS}

#########################################################################################
# Logging
#########################################################################################
def setupPugLogging(name):
    formatter = logging.Formatter(fmt='%(asctime)s %(levelname)-8s %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
    logfilename = 'log//{0}-{1}.log'.format(name,datetime.now().strftime('%Y-%m-%d'))
    os.makedirs(os.path.dirname(logfilename), exist_ok=True)
    handler = logging.FileHandler(filename=logfilename, encoding='utf-8', mode='w')
    handler.setFormatter(formatter)
    handler.setLevel(logging.DEBUG)

    screen_handler = logging.StreamHandler(stream=sys.stdout)
    screen_handler.setFormatter(formatter)
    screen_handler.setLevel(logging.DEBUG)
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if handler not in logger.handlers:
        logger.addHandler(handler)
    if screen_handler not in logger.handlers:
        logger.addHandler(screen_handler)
    return logger

log = setupPugLogging('pugbot')
log.info('Extension loaded with logging...')
#########################################################################################
# Utilities
#########################################################################################

def discord_md_escape(value):
    return DISCORD_MD_ESCAPE_RE.sub(lambda match: DISCORD_MD_ESCAPE_DICT[match.group(0)], value)

def display_name(member):
    return discord_md_escape(member.display_name)

def getDuration(then, now, interval: str = 'default'):
    # Adapted from https://stackoverflow.com/a/47207182
    duration = now - then
    duration_in_s = duration.total_seconds()

    def years():                    return divmod(duration_in_s, 31536000) # Seconds in a year = 31536000.
    def days(seconds = None):       return divmod(seconds if seconds is not None else duration_in_s, 86400) # Seconds in a day = 86400
    def hours(seconds = None):      return divmod(seconds if seconds is not None else duration_in_s, 3600) # Seconds in an hour = 3600
    def minutes(seconds = None):    return divmod(seconds if seconds is not None else duration_in_s, 60) # Seconds in a minute = 60
    def seconds(seconds = None):    return divmod(seconds, 1) if seconds is not None else duration_in_s
    def totalDuration():
        y = years()
        d = days(y[1]) # Use remainder to calculate next variable
        h = hours(d[1])
        m = minutes(h[1])
        s = seconds(m[1])
        msg = []
        if y[0] > 0:
            msg.append('{} years'.format(int(y[0])))
        if d[0] > 0:
            msg.append('{} days'.format(int(d[0])))
        if h[0] > 0:
            msg.append('{} hours'.format(int(h[0])))
        if m[0] > 0:
            msg.append('{} minutes'.format(int(m[0])))
        msg.append('{} seconds'.format(int(s[0])))
        return ', '.join(msg)
    return {'years': int(years()[0]),'days': int(days()[0]),'hours': int(hours()[0]),'minutes': int(minutes()[0]),'seconds': int(seconds()),'default': totalDuration()}[interval]

#########################################################################################
# CLASS
#########################################################################################
class Players:
    """Maintains the state of a set of players"""
    def __init__(self, maxPlayers):
        self.maxPlayers = maxPlayers
        self.players = []

    def __contains__(self, player):
        return player in self.players

    def __iter__(self):
        return iter(self.players)

    def __len__(self):
        return len(self.players)

    def __getstate__(self):
        state = self.__dict__.copy()
        del state['players']
        return state

    def __setstate__(self, state):
        self.__dict__ = state
        self.players = []

    #########################################################################################
    # Properties
    #########################################################################################
    @property
    def numPlayers(self):
        return len(self)

    @property
    def playersBrief(self):
        return '[{}/{}]'.format(self.numPlayers, self.maxPlayers)

    @property
    def playersFull(self):
        return self.numPlayers == self.maxPlayers

    @property
    def playersNeeded(self):
        return self.maxPlayers - self.numPlayers

    #########################################################################################
    # Functions
    #########################################################################################
    def addPlayer(self, player):
        if player not in self and not self.playersFull:
            self.players.append(player)
            return True
        return False

    def removePlayer(self, player):
        if player in self:
            self.players.remove(player)
            return True
        return False

    def resetPlayers(self):
        self.players = []

    def setMaxPlayers(self, numPlayers):
        if (numPlayers < 1 or numPlayers % 2 > 0):
            return
        if numPlayers < MAX_PLAYERS_LIMIT:
            self.maxPlayers = numPlayers
        else:
            self.maxPlayers = MAX_PLAYERS_LIMIT
        # If we have more players, then prune off the end.
        while(len(self) > self.maxPlayers):
            self.players.pop()

#########################################################################################
# CLASS
#########################################################################################
class PugMaps:
    """Maintains the state of a set of maps for a pug"""
    def __init__(self, maxMaps, pickMode, mapList):
        self.maxMaps = maxMaps
        self.pickMode = pickMode
        self.availableMapsList = mapList
        self.maps = []
        # List of non regular maps in a maplist
        self.exoticMaps = 0

    def __contains__(self, map):
        return map in self.maps

    def __iter__(self):
        return iter(self.maps)

    def __len__(self):
        return len(self.maps)

    def __getstate__(self):
        state = self.__dict__.copy()
        del state['maps']
        return state

    def __setstate__(self, state):
        self.__dict__ = state
        self.maps = []

    #########################################################################################
    # Properties
    #########################################################################################
    @property
    def mapsFull(self):
        return len(self) == self.maxMaps

    @property
    def currentTeamToPickMap(self):
        return PICKMODES[self.pickMode][len(self.maps)]

    @property
    def maxMapsLimit(self):
        return len(self.availableMapsList)

    #########################################################################################
    # Formatted strings
    #########################################################################################
    def format_maplist(self, maps):
        indexedMaps = self.indexMaps(maps)
        fmt = '**{0})** {1}'
        return PLASEP.join(fmt.format(*x) for x in indexedMaps)

    @property
    def format_available_maplist(self):
        return self.format_maplist(self.availableMapsList)

    @property
    def format_current_maplist(self):
        return self.format_maplist(self.maps)

    #########################################################################################
    # Functions
    #########################################################################################
    def indexMaps(self, maps):
        indexedMaplist = ((i, m) for i, m in enumerate(maps, 1) if m)
        return indexedMaplist

    #########################################################################################
    # Maintaining Available Maplist
    #########################################################################################
    def validateAvailableListIndex(self, index: int):
        return index >= 0 and index < len(self.availableMapsList)

    def validateAvailableListInsertIndex(self, index: int):
        return index >= 0 and index <= len(self.availableMapsList)

    def validateAvailableListNewMap(self, map: str):
        # Can't really verify the map, but ignore blank/number/None inputs.
        return (map not in self.availableMapsList and map not in [None, ''] and not map.isdigit())

    def addMapToAvailableList(self, map: str):
        if self.validateAvailableListNewMap(map):
            self.availableMapsList.append(map)
            return True
        return False

    def substituteMapInAvailableList(self, index: int, map: str):
        # Index must be passed in as 0-based.
        if self.validateAvailableListIndex(index) and self.validateAvailableListNewMap(map):
            self.availableMapsList[index] = map
            return True
        return False

    def insertMapIntoAvailableList(self, index: int, map: str):
        # Index must be passed in as 0-based.
        if self.validateAvailableListInsertIndex(index) and self.validateAvailableListNewMap(map):
            self.availableMapsList.insert(index, map)
            return True
        return False

    def removeMapFromAvailableList(self, map: str):
        if map and map in self.availableMapsList:
            self.availableMapsList.remove(map)
            return True
        return False

    def getMapFromAvailableList(self, index: int):
        # Index must be passed in as 0-based.
        if self.validateAvailableListIndex(index):
            return self.availableMapsList[index]
        return None

    #########################################################################################
    # Picking a set of maps for a pug
    #########################################################################################
    def setMaxMaps(self, numMaps: int):
        if numMaps > 0 and numMaps <= self.maxMapsLimit:
            self.maxMaps = numMaps
            return True
        return False

    def addMap(self, index: int):
        if self.mapsFull:
            return False
        map = self.getMapFromAvailableList(index)
        if map and map not in self:
            # Check if 7 maps and if map chosen is non-regular.
            if (map not in REGULAR_MAP_LIST) and (self.maxMaps == 7) and (self.exoticMaps != 2):
                self.exoticMaps += 1
                self.maps.append(map)
            elif (self.maxMaps == 7) and (self.exoticMaps == 2):
                return False
            else:
                self.maps.append(map)
            return True
        return False

    def removeMap(self, map: str):
        if map in self:
            self.maps.remove(map)
            return True
        return False

    def resetMaps(self):
        self.maps = []

#########################################################################################
# CLASS
#########################################################################################
class Team(list):
    """Represents a team of players with a captain"""
    def __init__(self):
        super().__init__()

    #########################################################################################
    # Properties
    #########################################################################################
    @property
    def captain(self):
        if len(self):
            return self[0]
        return None
   
#########################################################################################
# CLASS
#########################################################################################
class PugTeams(Players):
    """Represents players who can be divided into 2 teams who captains pick."""
    def __init__(self, maxPlayers: int, pickMode: int):
        super().__init__(maxPlayers)
        self.teams = (Team(), Team())
        self.pickMode = pickMode

    def __contains__(self, player):
        return player in self.all

    def __getstate__(self):
        state = super().__getstate__()
        del state['teams']
        return state

    def __setstate__(self, state):
        super().__setstate__(state)
        self.teams = (Team(), Team())

    #########################################################################################
    # Properties
    #########################################################################################
    @property
    def numCaptains(self):
        return sum([self.red.captain is not None, self.blue.captain is not None])

    @property
    def captainsFull(self):
        return self.red and self.blue
    
    @property
    def maxPicks(self):
        return self.maxPlayers - 2

    @property
    def currentPickIndex(self):
        return (len(self.red) + len(self.blue) - 2) if self.captainsFull else 0

    @property
    def currentTeamToPickPlayer(self):
        return PICKMODES[self.pickMode][self.currentPickIndex]

    @property
    def currentCaptainToPickPlayer(self):
        return self.teams[self.currentTeamToPickPlayer].captain if self.captainsFull else None

    @property
    def teamsFull(self):
        return len(self.red) + len(self.blue) == self.maxPlayers

    @property
    def currentTeam(self):
        return PICKMODES[self.pickMode][self.currentPickIndex]

    @property
    def red(self):
        return self.teams[0]

    @property
    def blue(self):
        return self.teams[1]

    @property
    def all(self):
        return list(filter(None, self.players + self.red + self.blue)) 

    #########################################################################################
    # Functions:
    #########################################################################################
    def removePugTeamPlayer(self, player):
        if player in self:
            self.softPugTeamReset()
            self.removePlayer(player)
            return True
        return False

    def softPugTeamReset(self):
        if self.red or self.blue:
            self.players += self.red + self.blue
            self.players = list(filter(None, self.players))
            self.teams = (Team(), Team())
            self.here = [True, True]
            return True
        return False

    def fullPugTeamReset(self):
        self.softPugTeamReset()
        self.resetPlayers()
        self.here = [True, True]

    def setCaptain(self, player):
        if player and player in self.players and self.playersFull:
            index = self.players.index(player)
            # Pick a random team.
            remaining = []
            if not self.red:
                remaining.append('red')
            if not self.blue:
                remaining.append('blue')
            team = random.choice(remaining)

            # Add player to chosen team.
            if team == 'red':
                self.red.append(player)
            elif team == 'blue':
                self.blue.append(player)
            else:
                return False
            self.players[index] = None
            return True
        return False

    def pickPlayer(self, captain, index: int):
        if captain == self.currentCaptainToPickPlayer:

            if index < 0 or index >= len(self) or not self.players[index]:
                return False

            player = self.players[index]
            self.teams[self.currentTeam].append(player)
            self.players[index] = None

            # Check if the next team has any choice of pick, if not fill automatically.
            remainingPicks = PICKMODES[self.pickMode][self.currentPickIndex:self.maxPicks]
            if len(set(remainingPicks)) == 1:
                for i, p in enumerate(self.players):
                    if p:
                        self.teams[self.currentTeam].append(p)
                        self.players[i] = None
            return True

#########################################################################################
# CLASS
#########################################################################################
class GameServer:
    def __init__(self, configFile=DEFAULT_CONFIG_FILE, parent=None):
        # Initialise the class with hardcoded defaults, then parse in JSON config
        self.parent = parent
        self.configFile = configFile
        self.configMaps = []

        # All servers
        self.allServers = DEFAULT_SERVER_LIST
        
        # POST server, game server and map thumbnails / info:
        self.postServer = DEFAULT_POST_SERVER
        self.authtoken = DEFAULT_POST_TOKEN
        self.thumbnailServer = DEFAULT_THUMBNAIL_SERVER

        # Chosen game server details
        self.gameServerRef = DEFAULT_GAME_SERVER_REF
        self.gameServerIP = DEFAULT_GAME_SERVER_IP
        self.gameServerPort = DEFAULT_GAME_SERVER_PORT
        self.gameServerName = DEFAUlT_GAME_SERVER_NAME
        self.gameServerState = ''
        self.gameServerOnDemand = False
        self.gameServerOnDemandReady = True
        self.gameServerRotation = []

        # Setup details and live score
        self.redPassword = DEFAULT_RED_PASSWORD
        self.bluePassword = DEFAULT_BLUE_PASSWORD
        self.redScore = 0
        self.blueScore = 0
        self.spectatorPassword = DEFAULT_SPECTATOR_PASSWORD
        self.numSpectators = DEFAULT_NUM_SPECTATORS

        # We keep a track of the server's match status and also if we have used "endMatch" since the last server setup, which
        # can be used to override the updating matchInProgress when a match has been ended since the last server setup.
        # This avoids the need to wait for the last map to complete before the server shows as match finished.
        self.matchInProgress = False
        self.endMatchPerformed = False

        # Store the responses from the setup server.
        self.lastSetupResult = ''
        self.lastCheckJSON = {}
        self.lastSetupJSON = {}
        self.lastEndGameJSON = {}

        self.lastUpdateTime = datetime.now()

        self.loadConfig(configFile)
        self.validateServers()
        self.updateServerStatus()
        
        # Stream GameSpy Unreal Query data using UDP sockets to send packets to the query port of the target server, then
        # receive back data into an array. Protocol info: https://wiki.beyondunreal.com/Legacy:UT_Server_Query
        # UTA servers extend the protocol server-side to offer Assault-related info and Event streams (e.g. chat)
        self.udpSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udpSock.settimeout(3)
        self.utQueryStatsActive = False
        self.utQueryReporterActive = False
        self.utQueryConsoleWatermark = self.format_new_watermark
        self.utQueryData = {}
        self.utQueryEmbedCache = {}

    # Load configuration defaults (some of this will later be superceded by live API data)
    def loadConfig(self, configFile):
        with open(configFile) as f:
            info = json.load(f)
            if info:
                if 'setupapi' in info:
                    setupapi = info['setupapi']
                    if 'postserver' in setupapi:
                        self.postServer = setupapi['postserver']
                    if 'authtoken' in setupapi:
                        self.authtoken = info['setupapi']['authtoken']
                else:
                    log.warn('setupapi not found in config file.')
                if 'thumbnailserver' in info:
                    self.thumbnailServer = info['thumbnailserver']
                if 'maplist' in info and len(info['maplist']):
                    log.info('Loaded {0} maps from config.json'.format(len(info['maplist'])))
                    self.configMaps = info['maplist']
                else:
                    log.warn('Maplist not found in config file.')

                # Iterate through local cache of servers, and set the default if present
                if 'serverlist' in info and len(info['serverlist']):
                    for server in info['serverlist']:
                        if 'serverondemand' in server.keys() and server['serverondemand'] is True:
                            ondemand = True
                        else:
                            ondemand = False
                        self.updateServerReference(server['serverref'],server['servername'],'',ondemand)
                        if 'serverdefault' in server.keys():
                            self.gameServerRef = server['serverref']
                else:
                    log.warn('Serverlist not found in config file.')
                if 'serverrotation' in info and len(info['serverrotation']):
                    self.gameServerRotation = []
                    for x in info['serverrotation']:
                        svindex = int(x)-1
                        if svindex >= 0 and svindex < len(self.allServers):
                            self.gameServerRotation.append(int(x))
            else:
                log.error('GameServer: Config file could not be loaded: {0}'.format(configFile))
            f.close()
        return True

    # Update config (currently only maplist is being saved)
    def saveMapConfig(self, configFile, maplist):
        with open(configFile) as f:
            info = json.load(f)
            if len(self.configMaps):
                info['maplist'] = self.configMaps
            if len(maplist):
                info['maplist'] = maplist
            f.close()
        with open(configFile, 'w') as f:
            json.dump(info, f, indent=4)
            f.close()
        return True

    def saveServerConfig(self, configFile):
        with open(configFile) as f:
            info = json.load(f)
            if len(self.allServers):
                info['serverlist'] = []
                for s in self.allServers:
                    # allServers[x][0] = server ref
                    # allServers[x][1] = server name
                    # allServers[x][2] = server url
                    # allServers[x][3] = on-demand server (bool)
                    # allServers[x][4] = last state (e.g. OPEN - PUBLIC, N/A)
                    serverinfo = {'serverref': s[0], 'servername': s[1], 'serverurl': s[2], 'serverondemand': s[3]}
                    if s[0] == self.gameServerRef:
                        serverinfo['serverdefault'] = True
                    info['serverlist'].append(serverinfo)
            if len(self.gameServerRotation):
                info['serverrotation'] = self.gameServerRotation
            f.close()
        with open(configFile, 'w') as f:
            json.dump(info, f, indent=4)
            f.close()
        return True
    
    def utQueryServer(self, queryType):
        if 'ip' not in self.utQueryData:
            self.utQueryData['ip'] = self.gameServerIP
        if 'game_port' not in self.utQueryData:
            self.utQueryData['game_port'] = self.gameServerPort
            self.utQueryData['query_port'] = (self.gameServerPort)+1
        try:
            self.udpSock.sendto(str.encode('\\{0}\\'.format(queryType)),(self.utQueryData['ip'], self.utQueryData['query_port']))
            udpData = []
            while True:
                if queryType == 'consolelog': # Larger buffer required for consolelog
                    udpRcv, _ = self.udpSock.recvfrom(65536)
                else:
                    udpRcv, _ = self.udpSock.recvfrom(4096)
                try:
                    udpData.extend(udpRcv.decode('utf-8','ignore').split('\\')[1:-2]) 
                except UnicodeDecodeError as e:
                    log.error('UDP decode error: {0}'.format(e.reason))
                    log.debug('Attempted sending UDP query {0} to {1}:{2}.'.format(queryType, self.utQueryData['ip'], self.utQueryData['query_port']))
                    return
                if udpRcv.split(b'\\')[-2] == b'final':
                    break
            parts = zip(udpData[::2], udpData[1::2])
            for part in parts:
                self.utQueryData[part[0]] = part[1]
            self.utQueryData['code'] = 200
            self.utQueryData['lastquery'] = int(time.time())
        except socket.timeout:
            log.error('UDP socket timeout when connecting to {0}:{1} to perform a query: {2}'.format(self.utQueryData['ip'], self.utQueryData['query_port'],queryType))
            self.utQueryData['status'] = 'Timeout connecting to server.'
            self.utQueryData['code'] = 408
            self.utQueryData['lastquery'] = 0

        return True

    #########################################################################################
    # Formatted JSON
    #########################################################################################
    @property
    def format_post_header_auth(self):
        fmt = {
                'Content-Type': 'application/json; charset=UTF-8',
                'PugAuth': '{}'.format(self.authtoken),
                'Accept':'*/*',
                'Accept-Encoding':'gzip, deflate, br'
        }
        return fmt

    @property
    def format_post_header_check(self):
        fmt = self.format_post_header_auth
        fmt.update({'Mode': 'check'})
        return fmt
    
    @property
    def format_post_header_list(self):
        fmt = self.format_post_header_auth
        fmt.update({'Mode': 'list'})
        return fmt
    
    @property
    def format_post_header_setup(self):
        fmt = self.format_post_header_auth
        fmt.update({'Mode': 'setup'})
        return fmt

    @property
    def format_post_header_endgame(self):
        fmt = self.format_post_header_auth
        fmt.update({'Mode': 'endgame'})
        return fmt
    
    def format_post_header_control(self, state: str = 'start'):
        fmt = self.format_post_header_auth
        fmt.update({'Mode': 'remote{0}'.format(state)})
        return fmt

    def format_post_body_serverref(self, serverref: str = ''):
        if len(serverref) == 0:
            serverref = self.gameServerRef
        fmt = {
            'server': serverref
        }
        return fmt

    def format_post_body_setup(self, numPlayers: int, maps, mode: str):
        fmt = {
            'server': self.gameServerRef,
            'authEnabled': True,
            'tiwEnabled': True,
            'matchLength': len(maps),
            'maxPlayers': numPlayers,
            'specLimit': self.numSpectators,
            'redPass': self.redPassword,
            'bluePass': self.bluePassword,
            'specPass': self.spectatorPassword,
            'maplist': maps,
            'gameType': 'LeagueAS140.LeagueAssault',
            'mutators': MODE_CONFIG[mode].mutators,
            'friendlyFireScale': MODE_CONFIG[mode].friendlyFireScale,
            'initialWait': 180
        }
        return fmt

    def current_serverrefs(self):
        allServerRefs = []
        for s in self.allServers:
            allServerRefs.append(s[0])
        return allServerRefs

    #########################################################################################
    # Formatted strings
    #########################################################################################
    @property
    def format_current_serveralias(self):
        serverName = self.allServers[self.current_serverrefs().index(self.gameServerRef)][1]
        if self.gameServerIP not in [None, '', '0.0.0.0']:
            serverName = self.gameServerName
        return '{0}'.format(serverName)
    
    @property
    def format_showall_servers(self):
        flags = {
            'UK':':flag_gb:',
            'FR':':flag_fr:',
            'NL':':flag_nl:',
            'DE':':flag_de:',
            'SE':':flag_se:',
            'ES':':flag_es:',
            'IT':':flag_it:',
            'DK':':flag_dk:',
            'JP':':flag_jp:',
            'AU':':flag_au:',
            'AT':':flag_at:',
            'BE':':flag_be:',
            'CA':':flag_ca:',
            'PL':':flag_pl:',
            'FI':':flag_fi:',
            'HU':':flag_hu:',
            'NO':':flag_no:',
            'CN':':flag_cn:',
            'XX':':pirate_flag:',
            'GP':':rainbow_flag:',
            'US':':flag_us:'
        }
        msg = []
        i = 0
        for s in self.allServers:
            i += 1
            servername = '{0}'.format(s[1])
            for flag in flags:
                servername  = re.compile(flag).sub(flags[flag], servername)
            msg.append('{0}. {1} - {2}'.format(i, servername, s[2]))
        return '\n'.join(msg)

    @property
    def format_gameServerURL(self):
        return 'unreal://{0}:{1}'.format(self.gameServerIP, self.gameServerPort)

    @property
    def format_gameServerURL_red(self):
        return '{0}{1}{2}'.format(self.format_gameServerURL, '?password=', self.redPassword)

    @property
    def format_gameServerURL_blue(self):
        return '{0}{1}{2}'.format(self.format_gameServerURL, '?password=', self.bluePassword)

    @property
    def format_gameServerURL_spectator(self):
        return '{0}{1}{2}'.format(self.format_gameServerURL, '?password=', self.spectatorPassword)

    @property
    def format_gameServerState(self):
        return '{0}'.format(self.gameServerState)

    @property
    def format_server_info(self):
        fmt = '{0} | {1}'.format(self.gameServerName, self.format_gameServerURL)
        return fmt

    @property
    def format_red_password(self):
        fmt = 'Red team password: **{}**'.format(self.redPassword)
        return fmt

    @property
    def format_blue_password(self):
        fmt = 'Blue team password: **{}**'.format(self.bluePassword)
        return fmt

    @property
    def format_spectator_password(self):
        fmt = 'Spectator password: **{}**'.format(self.spectatorPassword)
        return fmt

    @property
    def format_game_server(self):
        fmt = 'Pug Server: **{}**'.format(self.format_gameServerURL)
        return fmt
    
    @property
    def format_game_server_status(self):
        info = self.getServerStatus(restrict=True, delay=5)
        if not info:
            info = self.lastCheckJSON
        msg = ['```']
        try:
            msg.append('Server: ' + info['serverName'])
            msg.append(self.format_gameServerURL)
            msg.append('Summary: ' + info['serverStatus']['Summary'])
            msg.append('Map: ' + info['serverStatus']['Map'])
            msg.append('Mode: ' + info['serverStatus']['Mode'])
            msg.append('Players: ' + info['serverStatus']['Players'])
            msg.append('Remaining Time: ' + info['serverStatus']['RemainingTime'])
            msg.append('TournamentMode: ' + info['serverStatus']['TournamentMode'])
            msg.append('Status: ' + info['setupResult'])
        except:
            msg.append('WARNING: Unexpected or incomplete response from server.')
        msg.append('```')
        return '\n'.join(msg)

    @property
    def format_new_watermark(self):
        return int(datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S000'))

    #########################################################################################
    # Functions:
    ######################################################################################### 
    def makePostRequest(self, server: str, headers, json=None):
        if json:
            try:
                r = requests.post(server, headers=headers, json=json)
            except requests.exceptions.RequestException:
                return None
        else:
            try:
                r = requests.post(server, headers=headers)
            except requests.exceptions.RequestException:
                return None
        return r

    def removeServerReference(self, serverref: str):
        if serverref in self.current_serverrefs() and serverref not in [None, '']:
            self.allServers.pop(self.current_serverrefs().index(serverref))
            return True
        return False
    
    def updateServerReference(self, serverref: str, serverdesc: str, serverurl: str = '', serverondemand: bool = False, serverlaststatus: str = ''):
        if serverref in self.current_serverrefs() and serverref not in [None, '']:
            self.allServers.pop(self.current_serverrefs().index(serverref))
        self.allServers.append((serverref, serverdesc, serverurl,serverondemand,serverlaststatus))
        return True
    
    def useServer(self, index: int, autostart: bool = False, byref: str = ''):
        """Sets the active server"""
        serverchanged = False
        if index >= 0 and index < len(self.allServers):
            # check if current server needs to be shut down first
            if self.gameServerOnDemand:
                self.controlOnDemandServer('stop', self.gameServerRef)
            # update to new server
            self.gameServerRef = self.allServers[index][0]
            self.gameServerOnDemand = self.allServers[index][3]
            if autostart and self.gameServerOnDemand:
                self.controlOnDemandServer('start')
            else:
                self.updateServerStatus()
            serverchanged = True
        elif len(byref) > 0:
            for s in self.allServers:
                if s[0] == byref:
                    self.gameServerRef = s[0]
                    self.gameServerOnDemand = s[3]
                    self.updateServerStatus()
                    serverchanged = True
        if serverchanged:
            self.saveServerConfig(self.configFile)
            self.utQueryData = {}
            return True
        return False

    def generatePasswords(self):
        """Generates random passwords for red and blue teams."""
        # Spectator password is not changed, think keeping it fixed is fine.
        self.redPassword = RED_PASSWORD_PREFIX + str(random.randint(0, 999))
        self.bluePassword = BLUE_PASSWORD_PREFIX + str(random.randint(0, 999))

    def getServerList(self, restrict: bool = False, delay: int = 0, listall: bool = True):
        if restrict and (datetime.now() - self.lastUpdateTime).total_seconds() < delay:
            # 5 second delay between requests when restricted.
            return None
        log.debug('Sending API request, fetching server list...')
        if listall:
            r = self.makePostRequest(self.postServer, self.format_post_header_list)
        else:
            body = self.format_post_body_serverref()
            r = self.makePostRequest(self.postServer, self.format_post_header_list, body)
       
        self.lastUpdateTime = datetime.now()
        if(r):            
            try:
                validatedJSON = r.json()
                log.debug('API response validated.')
                return validatedJSON
            except:
                log.error('Invalid JSON returned from server, URL: {0} HTTP reponse: {1}; content:{2}'.format(r.url,r.status_code,r.content))
                return None
        else:
            return None

    def validateServers(self):
        if len(self.allServers):
            info = self.getServerList()
            if info and len(info):
                # firstly, determine if the primary server is online and responding, then drop the local list
                serverDefaultPresent = False
                for svc in info:
                    if svc['serverDefault'] is True and (svc['cloudManaged'] is True or svc['serverStatus']['Summary'] not in [None,'','N/A','N/AN/A']):
                        # If for whatever reason the default server isn't working, then stick to local list for now.
                        serverDefaultPresent = True
                        break

                if serverDefaultPresent:
                    # Default is present and working, re-iterate through list and populate local var
                    # Populate only those either online now, or that are "cloudManaged" on-demand servers
                    self.allServers = []
                    for sv in info:
                        if sv['cloudManaged'] is True or sv['serverStatus']['Summary'] not in [None, '', 'N/A', 'N/AN/A']:
                            self.updateServerReference(sv['serverRef'], sv['serverName'],'unreal://{0}:{1}'.format(sv['serverAddr'], sv['serverPort']), sv['cloudManaged'], sv['serverStatus']['Summary'])

                # Write the server config:
                self.saveServerConfig(self.configFile)
                return True
            else:
                return True # query failed, fall back to local json config
            return True
        return False

    def getServerStatus(self, restrict: bool = False, delay: int = 0):
        if restrict and (datetime.now() - self.lastUpdateTime).total_seconds() < delay:
            # 5 second delay between requests when restricted.
            return None
        body = self.format_post_body_serverref()
        log.debug('Posting "Check" to API {0} - {1}'.format(self.postServer,body))
        r = self.makePostRequest(self.postServer, self.format_post_header_check, body)
        log.debug('Received data from API - Status: {0}; Content-Length: {1}'.format(r.status_code,r.headers['content-length']))
        self.lastUpdateTime = datetime.now()
        if(r):
            return r.json()
        else:
            return None

    def updateServerStatus(self, ignorematchStarted: bool = False):
        log.debug('Running updateServerStatus')
        info = self.getServerStatus()
        log.debug('updateServerStatus - info fetched')
        log.debug('serverStatus: {0}'.format(info['serverStatus']))
        if info:
            self.gameServerName = info['serverName']
            self.gameServerIP = info['serverAddr']
            self.gameServerPort = info['serverPort']
            self.gameServerOnDemand = info['cloudManaged']
            self.gameServerOnDemandReady = True
            self.gameServerState = info['serverStatus']['Summary']
            self.matchInProgress = False
            if self.gameServerState.startswith('OPEN - PUBLIC') is not True and self.gameServerState.startswith('LOCKED - PRIVATE') is not True:
                self.redScore = info['serverStatus']['ScoreRed']
                self.blueScore = info['serverStatus']['ScoreBlue']
            if not self.endMatchPerformed and ignorematchStarted is False:
                self.matchInProgress = info['matchStarted']
            self.lastSetupResult = info['setupResult']
            self.lastCheckJSON = info
            return True
        self.lastSetupResult = 'Failed'
        return False
    
    def controlOnDemandServer(self, state: str = 'start', serverref: str = ''):
        if len(serverref) == 0:
            serverref = self.gameServerRef
        log.debug('Running controlOnDemandServer-{0} for {1}...'.format(state,serverref))
        if state not in [None, 'stop','halt','shutdown']:
            if not self.updateServerStatus(True): # or self.matchInProgress:
                return None

        headers = self.format_post_header_control(state)
        body = self.format_post_body_serverref(serverref)
        log.debug('Posting "Remote{0}" to API {1} - {2}'.format(state,self.postServer,body))
        r = self.makePostRequest(self.postServer, headers, body)
        log.debug('Received data from API - Status: {0}; Content-Length: {1}'.format(r.status_code,r.headers['content-length']))
        if(r):
            log.debug('controlOnDemandServer-{0} returned JSON info...'.format(state))
            info = r.json()
            return info
        else:
            log.error('controlOnDemandServer-{0} failed.'.format(state))
        return None

    def stopOnDemandServer(self, index: int):
        log.debug('Running stopOnDemandServer...')
        if index >= 0 and index < len(self.allServers):
            if self.allServers[index][3] is True:
                self.controlOnDemandServer('stop',self.allServers[index][0])
                log.debug('stopOnDemandServer - Control command issued.')
                return True
        log.debug('stopOnDemandServer - Invalid server selected.')
        return False

    def setupMatch(self, numPlayers, maps, mode):
        if self.matchInProgress:
            return False

        # Start the looped task which checks whether the server is ready
        if self.gameServerOnDemand:
            self.gameServerOnDemandReady = False
            # TODO - Unblock thread and move setup and checks to background
            #      - Lots of re-work required for this

            # log.debug('Starting Server state checker...')
            # self.updateOnDemandServerState.start(ctx, log, False)
            # log.debug('Server state checker started.')
        else:
            self.gameServerOnDemandReady = True

        i = 0
        while self.gameServerOnDemandReady is False:
            log.debug('Waiting for gameServerOnDemandReady...')
            if i < 5:
                self.controlOnDemandServer('start')
            else:
                if self.parent.gameServer.updateServerStatus():
                    self.gameServerOnDemandReady=True
                else:
                    time.sleep(5)
            i+=1
            if i > 12:
               # Stop trying after a minute
               self.gameServerOnDemandReady=True # fail the setup instead, and allow for manual retry.

        if not self.gameServerOnDemandReady:
            return False

        self.blueScore = 0
        self.redScore = 0
        self.generatePasswords()
        headers = self.format_post_header_setup
        body = self.format_post_body_setup(numPlayers, maps, mode)

        r = self.makePostRequest(self.postServer, headers, body)
        if(r):
            info = r.json()
            self.lastSetupResult = info['setupResult']
            self.matchInProgress = info['matchStarted']
            self.lastSetupJSON = info
            self.endMatchPerformed = False

            # Get passwords from the server
            self.redPassword = info['setupConfig']['redPass']
            self.bluePassword = info['setupConfig']['bluePass']
            self.spectatorPassword = info['setupConfig']['specPass']
            
            return self.lastSetupResult == 'Completed'

        self.matchInProgress = False
        self.lastSetupResult = 'Failed'
        return False

    def endMatch(self):
        # returns server back to public
        if not self.updateServerStatus():
            return False
        # Cache last scores from server status
        log.debug('endMatch ({0}): redScore = {1} - blueScore = {2}'.format(self.endMatchPerformed, self.redScore, self.blueScore))
        if self.endMatchPerformed is True:
            if self.parent.storeLastPug('**Score:** Red {0} - {1} Blue'.format(self.redScore, self.blueScore)):
                log.info('Pug reset; last scores appended successfully.')
            else:
                log.info('Pug reset; last scores did not append successfully.')
        # Tear down match
        body = self.format_post_body_serverref()
        r = self.makePostRequest(self.postServer, self.format_post_header_endgame, body)
        if(r):
            info = r.json()
            self.lastSetupResult = info['setupResult']
            self.lastEndGameJSON = info
            if self.lastSetupResult == 'Completed':
                self.matchInProgress = False
                self.endMatchPerformed = True
                return True

            return False
        self.lastSetupResult = 'Failed'
        return False

    def processMatchFinished(self):
        if self.lastSetupResult == 'Failed' or not self.updateServerStatus():
            return False

        if not self.matchInProgress and self.lastSetupResult == 'Match Finished':
            return self.endMatch()
        return False

    def waitUntilServerStarted(self):

        return True

    def checkServerRotation(self):
        # An imprecise science here, as where there is a mismatch between number of rotation items and weeks in a year,
        # the pattern may break when crossing over between week 52 and week 1 at new year.
        if len(self.gameServerRotation) > 0:
            # Extended the input a little, rather than simply week number, it's a combination of yearweek (e.g., 202201 - 202252),
            # which works better with smaller rotation pools
            newServer = int(self.gameServerRotation[int('{:0}{:0>2}'.format(datetime.now().year,datetime.now().isocalendar()[1]))%len(self.gameServerRotation)])-1
            if self.gameServerRef != self.allServers[newServer][0]:
                log.debug('checkServerRotation - Updating current server to: {0}'.format(self.allServers[newServer][1]))
                self.useServer(newServer)
        return True

    #########################################################################################
    # Loops
    #########################################################################################
    @tasks.loop(seconds=15.0, count=8)
    async def updateOnDemandServerState(self, ctx):
        log.debug('Checking on-demand server state...')
        if self.parent.gameServer.updateServerStatus():
            serverOnline=True
        else:
            serverOnline=False

        if serverOnline:
            log.info('Server online.')
            self.gameServerOnDemandReady = True
            await ctx.send('{0} is ready for action.'.format(self.parent.gameServer.gameServerName))
            self.updateOnDemandServerState.cancel()
        else:
            log.warn('Server not yet online.')
    
    @updateOnDemandServerState.after_loop
    async def on_updateOnDemandServerState_cancel(self):
        # Assume after loop completion that the servers is ready, and fall back to pug setup to confirm
        self.gameServerOnDemandReady = True

#########################################################################################
# CLASS
#########################################################################################
class AssaultPug(PugTeams):
    """Represents a Pug of 2 teams (to be selected), a set of maps to be played and a server to play on."""
    def __init__(self, numPlayers, numMaps, pickModeTeams, pickModeMaps, configFile=DEFAULT_CONFIG_FILE):
        super().__init__(numPlayers, pickModeTeams)
        self.name = 'Assault'
        self.mode = 'stdAS'
        self.desc = self.name + ': ' + self.mode + ' PUG'
        self.servers = [GameServer(configFile,self)]
        self.serverIndex = 0
        self.maps = PugMaps(numMaps, pickModeMaps, self.servers[self.serverIndex].configMaps)

        self.lastPugStr = 'No last pug info available.'
        self.lastPugTimeStarted = None
        self.pugLocked = False

        # Bit of a hack to get around the problem of a match being in progress when this is initialised.
        # Will improve this later.
        if self.gameServer.lastSetupResult == 'Match In Progress':
            self.pugLocked = True

    #########################################################################################
    # Properties:
    #########################################################################################
    @property
    def playersReady(self):
        if self.playersFull:
            return True
        return False

    @property
    def captainsReady(self):
        if self.captainsFull:
            return True
        return False

    @property
    def teamsReady(self):
        if self.captainsFull and self.teamsFull:
            return True
        return False

    @property
    def currentCaptainToPickMap(self):
        if self.captainsFull and not self.maps.mapsFull:
            return self.teams[self.maps.currentTeamToPickMap].captain
        else:
            return None

    @property
    def mapsReady(self):
        if self.maps.mapsFull:
            return True
        return False

    @property
    def matchReady(self):
        if self.playersReady and self.teamsReady and self.mapsReady:
            return True
        return False

    @property
    def gameServer(self):
        if len(self.servers):
            return self.servers[self.serverIndex]
        else:
            return None

    #########################################################################################
    # Formatted strings:
    #########################################################################################
    def format_players(self, players, number: bool = False, mention: bool = False):
        def name(p):
            return p.mention if mention else display_name(p)
        numberedPlayers = ((i, name(p)) for i, p in enumerate(players, 1) if p)
        fmt = '**{0})** {1}' if number else '{1}'
        return PLASEP.join(fmt.format(*x) for x in numberedPlayers)

    def format_all_players(self, number: bool = False, mention: bool = False):
        return self.format_players(self.all, number=number, mention=mention)

    def format_remaining_players(self, number: bool = False, mention: bool = False):
        return self.format_players(self.players, number=number, mention=mention)

    def format_red_players(self, number: bool = False, mention: bool = False):
        return self.format_players(self.red, number=number, mention=mention)

    def format_blue_players(self, number: bool = False, mention: bool = False):
        return self.format_players(self.blue, number=number, mention=mention)

    def format_teams(self, number: bool = False, mention: bool = False):
        teamsStr = '**Red Team:** {}\n**Blue Team:** {}'
        red = self.format_red_players(number=number, mention=mention)
        blue = self.format_blue_players(number=number, mention=mention)
        return teamsStr.format(red, blue)

    @property
    def format_pug_short(self):
        fmt = '**__{0.desc} [{1}/{0.maxPlayers}] \|\| {2} \|\| {3} maps__**'
        return fmt.format(self, len(self), self.gameServer.gameServerName, self.maps.maxMaps)

    def format_pug(self, number=True, mention=False):
        fmt = '**__{0.desc} [{1}/{0.maxPlayers}] \|\| {2} \|\| {3} maps:__**\n{4}'
        return fmt.format(self, len(self), self.gameServer.gameServerName, self.maps.maxMaps, self.format_all_players(number=number, mention=mention))

    @property
    def format_match_is_ready(self):
        fmt = ['Match is ready:']
        fmt.append(self.format_teams(mention=True))
        fmt.append('Maps ({}):\n{}'.format(self.maps.maxMaps, self.maps.format_current_maplist))
        fmt.append(self.gameServer.format_game_server)
        fmt.append(self.gameServer.format_spectator_password)
        return '\n'.join(fmt)

    @property
    def format_match_in_progress(self):
        if self.pugLocked:
            if not self.matchReady:
                # Handles the case when the bot has been restarted so doesn't have previous info.
                # Could improve this in future by caching the state to disk when shutting down and loading back in on restart.
                return 'Match is in progress, but do not have previous pug info. Please use **!serverstatus** to monitor this match'

            fmt = ['Match in progress ({} ago):'.format(getDuration(self.lastPugTimeStarted, datetime.now()))]
            fmt.append(self.format_teams(mention=False))
            fmt.append('Maps ({}):\n{}'.format(self.maps.maxMaps, self.maps.format_current_maplist))
            fmt.append('Mode: ' + self.mode)
            fmt.append(self.gameServer.format_game_server)
            fmt.append(self.gameServer.format_spectator_password)
            return '\n'.join(fmt)
        return None

    @property
    def format_last_pug(self):
        if self.lastPugTimeStarted and '{}' in self.lastPugStr:
            return self.lastPugStr.format(getDuration(self.lastPugTimeStarted, datetime.now()))
        else:
            return 'No last pug info available.'

    @property
    def format_list_servers(self):
        indexedServers = ((i,s) for i,s in enumerate(self.servers, 1) if s)
        fmt = []
        for x in indexedServers:
            fmt.append('**{0})** {1}'.format(str(x[0]), x[1].format_server_info))

        return '\n'.join(fmt)

    #########################################################################################
    # Functions:
    #########################################################################################
    def addServer(self, serverfile: str):
        try:
            self.servers.add(GameServer(serverfile))
            return True
        except:
            return False

    def removeServer(self, index: int):
        if index >= 0 and index < len(self.servers):
            self.servers.pop(index)
            if self.serverIndex == index and len(self.servers) > 0:
                self.serverIndex = 0

    def removePlayerFromPug(self, player):
        if self.removePugTeamPlayer(player):
            # Reset the maps too. If maps have already been picked, removing a player will mean teams and maps must be re-picked.
            self.maps.resetMaps()
            return True
        else:
            return False

    def pickMap(self, captain, index: int):
        if captain != self.currentCaptainToPickMap:
            return False
        return self.maps.addMap(index)

    def setupPug(self):
        if not self.pugLocked and self.matchReady:
            # Try to set up 5 times with a 5s delay between attempts.
            result = False
            for x in range(0, 5):
                result = self.gameServer.setupMatch(self.maxPlayers, self.maps.maps, self.mode)
                log.debug('Setup attempt {0}/5: Result returned: {1}'.format(x+1,result))
                if not result:
                    time.sleep(5)
                else:
                    self.pugLocked = True
                    self.storeLastPug()
                    return True
        return False

    def storeLastPug(self, appendstr: str = ''):
        if self.matchReady:
            fmt = []
            fmt.append('Last **{}** ({} ago)'.format(self.desc, '{}'))
            fmt.append(self.format_teams())
            fmt.append('Maps ({}):\n{}'.format(self.maps.maxMaps, self.maps.format_current_maplist))
            self.lastPugStr = '\n'.join(fmt)
            self.lastPugTimeStarted = datetime.now()
            return True
        elif len(appendstr):
            fmt = []
            fmt.append(self.lastPugStr)
            fmt.append(appendstr)
            self.lastPugStr = '\n'.join(fmt)
            return True
        return False

    def resetPug(self):
        self.maps.resetMaps()
        self.fullPugTeamReset()
        if self.pugLocked or (self.gameServer and self.gameServer.matchInProgress):
        # Is this a good idea? Might get abused.
            self.gameServer.endMatch()
        self.gameServer.utQueryReporterActive = False
        self.gameServer.utQueryStatsActive = False
        self.pugLocked = False
        return True

    def setMode(self, mode: str):
        # Dictionaries are case sensitive, so we'll do a map first to test case-insensitive input, then find the actual key after
        if mode.upper() in map(str.upper, MODE_CONFIG):
            ## Iterate through the keys to find the actual case-insensitive mode
            mode = next((key for key, value in MODE_CONFIG.items() if key.upper()==mode.upper()), None)

            ## ProAS and iAS are played with a different maximum number of players.
            ## Can't change mode from std to pro/ias if more than the maximum number of players allowed for these modes are signed.
            if mode.upper() != 'STDAS' and mode.upper() != 'LCAS' and len(self.players) > MODE_CONFIG[mode].maxPlayers:
                return False, str(MODE_CONFIG[mode].maxPlayers) + ' or fewer players must be signed for a switch to ' + mode
            else:
                ## If max players is more than mode max and there aren't more than mode max players signed, automatically reduce max players to mode max.
                if mode.upper() != 'STDAS' and mode.upper() != 'LCAS' and self.maxPlayers > MODE_CONFIG[mode].maxPlayers:
                    self.setMaxPlayers(MODE_CONFIG[mode].maxPlayers)
                self.mode = mode
                self.desc = 'Assault ' + mode + ' PUG'
                return True, 'Pug mode changed to: **' + mode + '**'
        else:
            outStr = ['Mode not recognised. Valid modes are:']
            for k in MODE_CONFIG:
                outStr.append(PLASEP + '**' + k + '**')
            outStr.append(PLASEP)
            return False, ' '.join(outStr)
        

#########################################################################################
# Static methods for cogs.
#########################################################################################
def isActiveChannel_Check(ctx): return ctx.bot.get_cog('PUG').isActiveChannel(ctx)

def isPugInProgress_Warn(ctx): return ctx.bot.get_cog('PUG').isPugInProgress(ctx, warn=True)

def isPugInProgress_Ignore(ctx): return ctx.bot.get_cog('PUG').isPugInProgress(ctx, warn=False)

#########################################################################################
# Custom Exceptions
#########################################################################################
class PugIsInProgress(commands.CommandError):
    """Raised when a pug is in progress"""
    pass

#########################################################################################
# Main pug cog class.
#########################################################################################
class PUG(commands.Cog):
    def __init__(self, bot, configFile=DEFAULT_CONFIG_FILE):
        self.bot = bot
        self.activeChannel = None
        self.customStaticEmojis = {}
        self.customAnimatedEmojis = {}
        self.utReporterChannel = None
        self.pugInfo = AssaultPug(DEFAULT_PLAYERS, DEFAULT_MAPS, DEFAULT_PICKMODETEAMS, DEFAULT_PICKMODEMAPS, configFile)
        self.configFile = configFile

        self.loadPugConfig(configFile)
        self.cacheGuildEmojis()

        # Used to keep track of if both teams have requested a reset while a match is in progress.
        # We'll only make use of this in the reset() function so it only needs to be put back to
        # False when a new match is setup.
        self.resetRequestRed = True
        self.resetRequestBlue = True

        # Start the looped task which checks the server when a pug is in progress (to detect match finished)
        self.updateGameServer.add_exception_type(asyncpg.PostgresConnectionError)
        self.updateGameServer.start()

        # Start the GameSpy query loops
        self.updateUTQueryReporter.start()
        self.updateUTQueryStats.start()
        
        # Start the Emoji update loop
        self.updateGuildEmojis.start()

        # Start the looped task for server rotation
        self.updateServerRotation.start()
        
        self.lastPokeTime = datetime.now()

    def cog_unload(self):
        self.updateGameServer.cancel()
        self.updateUTQueryReporter.cancel()
        self.updateUTQueryStats.cancel()
        self.updateGuildEmojis.cancel()
        self.updateServerRotation.cancel()

#########################################################################################
# Loops.
#########################################################################################
    @tasks.loop(seconds=60.0)
    async def updateGameServer(self):
        if self.pugInfo.pugLocked:
            log.info('Updating game server [pugLocked=True]..')
            if not self.pugInfo.gameServer.updateServerStatus():
                log.warn('Cannot contact game server.')
            if self.pugInfo.gameServer.processMatchFinished():
                await self.activeChannel.send('Match finished. Resetting pug...')
                if self.pugInfo.resetPug():
                    await self.activeChannel.send(self.pugInfo.format_pug())
                    log.info('Match over.')
                    return
                await self.activeChannel.send('Reset failed.')
                log.error('Reset failed')

    @updateGameServer.before_loop
    async def before_updateGameServer(self):
        log.info('Waiting before updating game server...')
        await self.bot.wait_until_ready()
        log.info('Ready.')

    @tasks.loop(seconds=4.0)
    async def updateUTQueryReporter(self):
        if self.pugInfo.gameServer.utQueryReporterActive and self.utReporterChannel is not None:
            await self.queryServerConsole()
        return

    @updateUTQueryReporter.before_loop
    async def before_updateUTQueryReporter(self):
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=60.0)
    async def updateUTQueryStats(self):
        if self.utReporterChannel is not None:
            if self.pugInfo.gameServer.utQueryStatsActive:
                if ('laststats' not in self.pugInfo.gameServer.utQueryData) or ('laststats' in self.pugInfo.gameServer.utQueryData and int(time.time())-int(self.pugInfo.gameServer.utQueryData['laststats']) > 55):
                    await self.queryServerStats()
            elif self.pugInfo.gameServer.utQueryReporterActive and self.pugInfo.pugLocked:
                # Skip one cycle, then re-enable stats
                self.pugInfo.gameServer.utQueryStatsActive = True
        return

    @updateUTQueryStats.before_loop
    async def before_updateUTQueryStats(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=5)
    async def updateGuildEmojis(self):
        self.cacheGuildEmojis()
        return
    
    @tasks.loop(hours=1)
    async def updateServerRotation(self):
        # Only auto-rotate between 6:00 and 9:59 am on a Monday
        if datetime.now().weekday() == 0 and datetime.now().hour >= 6 and datetime.now().hour <= 9 and not self.pugInfo.pugLocked:
            log.debug('updateServerRotation loop - calling checkServerRotation()')
            self.pugInfo.gameServer.checkServerRotation()
        return
#########################################################################################
# Utilities.
#########################################################################################
    def loadPugConfig(self, configFile):
        with open(configFile) as f:
            info = json.load(f)
            if info:
                if 'pug' in info and 'activechannelid' in info['pug']:
                    channelID = info['pug']['activechannelid']
                    channel = discord.Client.get_channel(self.bot, channelID)
                    log.info('Loaded active channel id: {0} => channel: {1}'.format(channelID, channel))
                    if channel:
                        self.activeChannel = channel
                        # Only load current info if the channel is valid, otherwise the rest is useless.
                        if 'current' in info['pug']:
                            if 'mode' in info['pug']['current']:
                                self.pugInfo.setMode(info['pug']['current']['mode'])
                            if 'playerlimit' in info['pug']['current']:
                                self.pugInfo.setMaxPlayers(info['pug']['current']['playerlimit'])
                            if 'maxmaps' in info['pug']['current']:
                                self.pugInfo.maps.setMaxMaps(info['pug']['current']['maxmaps'])
                            if 'timesaved' in info['pug']['current']:
                                time_saved = datetime.fromisoformat(info['pug']['current']['timesaved'])
                                # Only load signed players if timesaved is present and it is within 60 seconds of when the file was last saved.
                                # This is to avoid people thinking they were unsigned and causing a no-show.
                                if (datetime.now() - time_saved).total_seconds() < 60 and 'signed' in info['pug']['current']:
                                    players = info['pug']['current']['signed']
                                    if players:
                                        for player_id in players:
                                            player = self.activeChannel.guild.get_member(player_id)
                                            if player:
                                                self.pugInfo.addPlayer(player)
                        if 'lastpug' in info['pug']:
                            if 'pugstr' in info['pug']['lastpug']:
                                self.pugInfo.lastPugStr = info['pug']['lastpug']['pugstr']
                                if 'timestarted' in info['pug']['lastpug']:
                                    try:
                                        self.pugInfo.lastPugTimeStarted = datetime.fromisoformat(info['pug']['lastpug']['timestarted'])
                                    except:
                                        self.pugInfo.lastPugTimeStarted = None
                    else:
                        log.warn('No active channel id found in config file.')
                if 'pug' in info and 'reporterchannelid' in info['pug']:
                    channelID = info['pug']['reporterchannelid']
                    channel = discord.Client.get_channel(self.bot,channelID)
                    if channel:
                        self.utReporterChannel = channel
                if 'pug' in info and 'reporterconsolewatermark' in info['pug']:
                    self.pugInfo.gameServer.utQueryConsoleWatermark = info['pug']['reporterconsolewatermark']
            else:
                log.error('PUG: Config file could not be loaded: {0}'.format(configFile))
            f.close()
        return True

    def savePugConfig(self, configFile):
        with open(configFile) as f:
            info = json.load(f)
            if 'pug' in info and 'activechannelid' in info['pug']:
                last_active_channel_id = info['pug']['activechannelid']
            if 'pug' not in info:
                info['pug'] = {}
            if self.activeChannel:
                info['pug']['activechannelid'] = self.activeChannel.id
            else:
                info['pug']['activechannelid'] = 0
            if self.utReporterChannel:
                info['pug']['reporterchannelid'] = self.utReporterChannel.id
            else:
                info['pug']['reporterchannelid'] = 0
            if self.pugInfo.gameServer.utQueryConsoleWatermark > 0:
               info['pug']['reporterconsolewatermark'] = self.pugInfo.gameServer.utQueryConsoleWatermark
            else:
               info['pug']['reporterconsolewatermark'] = 0
            # Only save info about the current/last pugs if the channel id is valid and unchanged in this save.
            if self.activeChannel and self.activeChannel.id == last_active_channel_id:
                # current pug info:
                info['pug']['current'] = {}
                info['pug']['current']['timesaved'] = datetime.now().isoformat()
                info['pug']['current']['mode'] = self.pugInfo.mode
                info['pug']['current']['playerlimit'] = self.pugInfo.maxPlayers
                info['pug']['current']['maxmaps'] = self.pugInfo.maps.maxMaps
                if len(self.pugInfo.players) > 0:
                    info['pug']['current']['signed'] = []
                    for p in self.pugInfo.all:
                        if (p not in [None]):
                            info['pug']['current']['signed'].append(p.id)

                # last pug info:
                info['pug']['lastpug'] = {}
                if self.pugInfo.lastPugTimeStarted:
                    info['pug']['lastpug']['timestarted'] = self.pugInfo.lastPugTimeStarted.isoformat()
                if self.pugInfo.lastPugStr:
                    info['pug']['lastpug']['pugstr'] = self.pugInfo.lastPugStr
        with open(configFile,'w') as f:
            json.dump(info, f, indent=4)
        return True

    #########################################################################################
    # Formatted strings:
    #########################################################################################

    def format_pick_next_player(self, mention: bool = False):
        player = self.pugInfo.currentCaptainToPickPlayer
        return '{} to pick next player (**!pick <number>**)'.format(player.mention if mention else display_name(player))

    def format_pick_next_map(self, mention: bool = False):
        player = self.pugInfo.currentCaptainToPickMap
        return '{} to pick next map (use **!map <number>** to pick and **!listmaps** to view available maps)'.format(player.mention if mention else display_name(player))

    #########################################################################################
    # Functions:
    #########################################################################################

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if type(error) is PugIsInProgress:
            # To handle messages returned when disabled commands are used when pug is already in progress.
            msg = ['Match is currently in progress.']
            if ctx.message.author in self.pugInfo:
                msg.append('{},  please, join the match or find a sub.'.format(ctx.message.author.mention))
                msg.append('If the match has just ended, please, wait at least 60 seconds for the pug to reset.')
            else:
                msg.append('Pug will reset when it is finished.')
            await ctx.send('\n'.join(msg))

    def isActiveChannel(self, ctx):
        return self.activeChannel is not None and self.activeChannel == ctx.message.channel
    
    async def checkOnDemandServer(self, ctx):
        if self.pugInfo.gameServer.gameServerState in ('N/A','N/AN/A') and self.pugInfo.gameServer.gameServerOnDemand is True:
            await ctx.send('Starting on-demand server: {0}...'.format(self.pugInfo.gameServer.gameServerName))
            info = self.pugInfo.gameServer.controlOnDemandServer('start')
            if (info):
                log.info('On-demand server start {0} returned: {1}'.format(self.pugInfo.gameServer.gameServerName,info['cloudManagementResponse']))
                return True
            else:
                log.error('Failed to start on-demand server: {0}'.format(self.pugInfo.gameServer.gameServerName))
                await ctx.send('Failed to start on-demand server: {0}. Select another server before completing map selection.'.format(self.pugInfo.gameServer.gameServerName))
                return False
        return True

    async def processPugStatus(self, ctx):
        # Big function to test which stage of setup we're at:
        if not self.pugInfo.playersFull:
            # Not filled, nothing to do.
            return

        # Work backwards from match ready.
        # Note match is ready once players are full, captains picked, players picked and maps picked.
        if self.pugInfo.mapsReady and self.pugInfo.matchReady:
            if self.pugInfo.gameServer.gameServerOnDemand and not self.pugInfo.gameServer.gameServerOnDemandReady:
                await ctx.send('Waiting for {0} to be ready for action...'.format(self.parent.gameServer.gameServerName))
            if self.pugInfo.setupPug():
                await self.sendPasswordsToTeams()
                await ctx.send(self.pugInfo.format_match_is_ready)
                self.pugInfo.gameServer.utQueryConsoleWatermark = self.pugInfo.gameServer.format_new_watermark
                self.pugInfo.gameServer.utQueryData = {}
                self.pugInfo.gameServer.utQueryReporterActive = True
                self.pugInfo.gameServer.utQueryStatsActive = True
                self.resetRequestRed = False # only need to reset this here because we only care about this when a match is in progress.
                self.resetRequestBlue = False # only need to reset this here because we only care about this when a match is in progress.
            else:
                await ctx.send('**PUG Setup Failed**. Use **!retry** to attempt setting up again with current configuration, or **!reset** to start again from the beginning.')
            return

        if self.pugInfo.teamsReady:
            # Need to pick maps.
            await ctx.send(self.format_pick_next_map(mention=True))
            return
        
        if self.pugInfo.captainsReady:
            # Special case to display captains on the first pick.
            if len(self.pugInfo.red) == 1 and len(self.pugInfo.blue) == 1:
                await ctx.send(self.pugInfo.red[0].mention + ' is captain for the **Red Team**')
                await ctx.send(self.pugInfo.blue[0].mention + ' is captain for the **Blue Team**')
            # Need to pick players.
            msg = '\n'.join([
                self.pugInfo.format_remaining_players(number=True),
                self.pugInfo.format_teams(),
                self.format_pick_next_player(mention=True)])
            await ctx.send(msg)
            # Check server state and fire a start-up command if needed
            await self.checkOnDemandServer(ctx)
            return
        
        if self.pugInfo.numCaptains == 1:
            # Need second captain.
            await ctx.send('Waiting for 2nd captain. Type **!captain** to become a captain. To choose a random captain type **!randomcaptains**')
            return

        if self.pugInfo.playersReady:
            # Need captains.
            msg = ['**{}** has filled.'.format(self.pugInfo.desc)]
            if len(self.pugInfo) == 2 and self.pugInfo.playersFull:
                # Special case, 1v1: assign captains instantly, so jump straight to map picks.
                self.pugInfo.setCaptain(self.pugInfo.players[0])
                self.pugInfo.setCaptain(self.pugInfo.players[1])
                await ctx.send('Teams have been automatically filled.\n{}'.format(self.pugInfo.format_teams(mention=True)))
                await ctx.send(self.format_pick_next_map(mention=False))
                # Check server state and fire a start-up command if needed
                await self.checkOnDemandServer(ctx)
                return

            # Standard case, moving to captain selection.
            msg.append(self.pugInfo.format_pug(mention=True))
            # Need first captain
            msg.append('Waiting for captains. Type **!captain** to become a captain. To choose random captains type **!randomcaptains**')
            await ctx.send('\n'.join(msg))
            return

    async def sendPasswordsToTeams(self):
        if self.pugInfo.matchReady:
            msg_redPassword = self.pugInfo.gameServer.format_red_password
            msg_redServer = self.pugInfo.gameServer.format_gameServerURL_red
            msg_bluePassword = self.pugInfo.gameServer.format_blue_password
            msg_blueServer = self.pugInfo.gameServer.format_gameServerURL_blue
            for player in self.pugInfo.red:
                try:
                    await player.send('{0}\nJoin the server @ **{1}**'.format(msg_redPassword, msg_redServer))
                except:
                    await self.activeChannel.send('Unable to send password to {} - are DMs enabled? Please ask your teammates for the red team password.'.format(player.mention))
            for player in self.pugInfo.blue:
                try:
                    await player.send('{0}\nJoin the server @ **{1}**'.format(msg_bluePassword, msg_blueServer))
                except:
                    await self.activeChannel.send('Unable to send password to {} - are DMs enabled? Please ask your teammates for the blue team password.'.format(player.mention))
        if self.activeChannel:
            await self.activeChannel.send('Check private messages for server passwords.')
        return True

    async def isPugInProgress(self, ctx, warn: bool=False):
        if not self.isActiveChannel(ctx):
            return False
        if warn and self.pugInfo.pugLocked:
            log.warn('Raising PugIsInProgress')
            raise PugIsInProgress('Pug In Progress')
        return not self.pugInfo.pugLocked
    
    async def queryServerConsole(self):
        # Fetch watermark from previous messages
        consoleWatermark = self.pugInfo.gameServer.utQueryConsoleWatermark
        reportToChannel = self.utReporterChannel
        # Fetch console log
        if self.pugInfo.gameServer.utQueryServer('consolelog') and reportToChannel is not None:
            if 'code' in self.pugInfo.gameServer.utQueryData and self.pugInfo.gameServer.utQueryData['code'] == 200:
                if 'consolelog' in self.pugInfo.gameServer.utQueryData:
                    bReportScoreLine = False
                    # Attempt to serialize to JSON, otherwise if server doesn't support this, use simple string manipulation
                    try:
                        utconsole = json.loads(self.pugInfo.gameServer.utQueryData['consolelog'])
                    except:
                        utconsole = {}
                        utconsole['messages'] = str(self.pugInfo.gameServer.utQueryData['consolelog']).split('|')

                    for m in utconsole['messages']:
                        try:
                            # Message format: {"stamp":"20220101133700666", "type":"Say", "gametime":"120", "displaytime":"02:00", "message": ":robot::guitar:", "teamindex":"0", "team":"Red", "player":"Sizzl"}
                            if 'message' in m and 'stamp' in m and int(m['stamp']) > self.pugInfo.gameServer.utQueryConsoleWatermark:
                                if 'type' in m and m['type'] == 'Say':
                                    for em in self.customStaticEmojis:
                                        m['message']  = re.compile(em).sub('<{0}{1}>'.format(em,self.customStaticEmojis[em]), m['message'])
                                    for em in self.customAnimatedEmojis:
                                        m['message']  = re.compile(em).sub('<a{0}{1}>'.format(em,self.customAnimatedEmojis[em]), m['message'])
                                    if 'team' in m:
                                        if m['team'] == 'Spectator':
                                            await reportToChannel.send('[{0}] {1} (*{2}*): {3}'.format(m['displaytime'],m['player'].strip(),m['team'],m['message'].strip()))
                                        else:
                                            await reportToChannel.send('[{0}] {1} (**{2}**): {3}'.format(m['displaytime'],m['player'].strip(),m['team'],m['message'].strip()))
                                    else:
                                        await reportToChannel.send('[{0}] {1}: {2}'.format(m['displaytime'],m['player'].strip(),m['message'].strip()))
                                else:
                                    if re.search('1\sminutes\suntil\sgame\sstart|conquered\sthe\sbase|defended\sthe\sbase',m['message'],re.IGNORECASE) is not None:
                                        bReportScoreLine = True
                                    if len(m['message'].strip()) > 0:
                                        await reportToChannel.send('[{0}] {1}'.format(m['displaytime'],m['message'].strip()))
                                consoleWatermark = int(m['stamp'])
                        except:
                            try:
                                # Message format: 20220101133700666 [13:37] Player: Message
                                # We won't do any fancy replacements here, just drop the message verbatim.
                                stamp = int(m[:17])
                            except:
                                stamp = 0
                            if stamp > self.pugInfo.gameServer.utQueryConsoleWatermark:
                                await reportToChannel.send('{0}'.format(m[-(len(m)-18):]))
                                if re.search('1\sminutes\suntil\sgame\sstart|conquered\sthe\sbase|defended\sthe\sbase',m,re.IGNORECASE) is not None:
                                    bReportScoreLine = True
                            if stamp > 0:
                                consoleWatermark = stamp
                            else:
                                consoleWatermark = self.pugInfo.gameServer.format_new_watermark
                    self.pugInfo.gameServer.utQueryConsoleWatermark = consoleWatermark

                    if self.pugInfo.gameServer.utQueryStatsActive is False:
                        # Picking up a deferred stats request (from bReportScoreLine)
                        await self.queryServerStats()
                        # Reset the requirement for scoreline and re-enable the infrequent stats embed
                        bReportScoreLine = False
                        self.pugInfo.gameServer.utQueryStatsActive = True

                    if bReportScoreLine:
                        # Defer a scoreline report to the next cycle of this function by disabling the infrequent stats embed
                        self.pugInfo.gameServer.utQueryStatsActive = False
                        
        return True

    async def queryServerStats(self, cacheonly: bool=False):
        embedInfo = discord.Embed(color=discord.Color.greyple(),title=self.pugInfo.gameServer.format_current_serveralias,description='Waiting for server info...')
        # Send "info" to get basic server details and confirm online
        if self.pugInfo.gameServer.utQueryServer('info'):
            if 'code' in self.pugInfo.gameServer.utQueryData and self.pugInfo.gameServer.utQueryData['code'] == 200:
                if cacheonly is False:
                    # Rate-limit reporter-channel stats cards to one a minute, even after an on-demand stats call
                    self.pugInfo.gameServer.utQueryData['laststats'] = int(time.time())

                # Send multi-query request for lots of info
                if self.pugInfo.gameServer.utQueryServer('status\\\\level_property\\timedilation\\\\game_property\\teamscore\\\\game_property\\teamnamered\\\\game_property\\teamnameblue\\\\player_property\\Health\\\\game_property\\elapsedtime\\\\game_property\\remainingtime\\\\game_property\\bmatchmode\\\\game_property\\friendlyfirescale\\\\game_property\\currentdefender\\\\game_property\\bdefenseset\\\\game_property\\matchcode\\\\game_property\\fraglimit\\\\game_property\\timelimit\\\\rules'):
                    queryData = self.pugInfo.gameServer.utQueryData

                    # Build embed data
                    summary = {
                        'Colour': discord.Color.greyple(),
                        'Title': 'Pug Match',
                        'RoundStatus': '',
                        'Map': '',
                        'Objectives': '',
                        'Hostname': '',
                        'PlayerCount': ''
                    }
                    for x in range(0,4):
                        summary['PlayerList{0}'.format(x)] = '*(No players)*'
                        summary['PlayerList{0}_data'.format(x)] = ''
                    summary['PlayerList255'] = '*(No Spectators)*'
                    summary['PlayerList255_data'] = ''
                    # Pick out generic UT info
                    if 'hostname' in queryData:
                        if 'mutators' in queryData and re.search('Lag\sCompensator',str(queryData['mutators']),re.IGNORECASE) is not None:
                            summary['Title'] = summary['Hostname'] = queryData['hostname'].replace('| StdAS |','| lcAS |')
                        else:
                            summary['Title'] = summary['Hostname'] = queryData['hostname'].replace('| iAS | zp|','| zp-iAS |')
                    if 'mapname' in queryData:
                        embedInfo.set_thumbnail(url='{0}{1}.jpg'.format(self.pugInfo.gameServer.thumbnailServer,str(queryData['mapname']).lower()))
                        summary['Map'] = queryData['mapname']
                    if 'remainingtime' in queryData:
                        summary['RemainingTime'] = '{0}'.format(str(time.strftime('%M:%S',time.gmtime(int(queryData['remainingtime'])))))
                    elif 'elapsedtime' in queryData:
                        summary['ElapsedTime'] = '{0}'.format(str(time.strftime('%M:%S',time.gmtime(int(queryData['elapsedtime'])))))
                    elif 'timelimit' in queryData and int(queryData['timelimit']) > 0:
                        summary['TimeLimit'] = '{0}:00'.format(int(queryData['timelimit']))
                    if 'maptitle' in queryData:
                        summary['Map'] = queryData['maptitle']
                    if 'numplayers' in queryData and 'maxplayers' in queryData:
                        summary['PlayerCount'] = '{0}/{1}'.format(queryData['numplayers'],queryData['maxplayers'])
                        if 'maxteams' in queryData and int(queryData['numplayers']) > 0:
                            for x in range(int(queryData['numplayers'])):
                                if 'player_{0}'.format(x) in queryData:
                                    player = {}
                                    player['Name'] = queryData['player_{0}'.format(x)].replace('`','').strip()
                                    if len(player['Name']) > 19:
                                        player['Name'] = '{0}...'.format(player['Name'][:17]).strip()
                                    player['Frags'] = '0'
                                    if 'frags_{0}'.format(x) in queryData:
                                        player['Frags'] = queryData['frags_{0}'.format(x)].strip()                                                                                        
                                    player['Ping'] = '0'
                                    if 'ping_{0}'.format(x) in queryData:
                                        player['Ping'] = queryData['ping_{0}'.format(x)].strip()
                                        if len(str(player['Ping'])) > 3:
                                            player['Ping'] = '---'
                                    if 'team_{0}'.format(x) in queryData:
                                        player['TeamId'] = queryData['team_{0}'.format(x)]
                                    if player['TeamId'] == '255':
                                        summary['PlayerList{0}_data'.format(player['TeamId'])] = '{0}\n{1}\t {2} {3}'.format(summary['PlayerList{0}_data'.format(player['TeamId'])],player['Name'].ljust(20),''.rjust(5),player['Ping'].rjust(4))
                                    else:
                                        summary['PlayerList{0}_data'.format(player['TeamId'])] = '{0}\n{1}\t {2} {3}'.format(summary['PlayerList{0}_data'.format(player['TeamId'])],player['Name'].ljust(20),player['Frags'].rjust(5),player['Ping'].rjust(4))

                            for x in range(int(queryData['maxteams'])):
                                if summary['PlayerList{0}_data'.format(x)] not in ['',None]:
                                    summary['PlayerList{0}'.format(x)] = '```Player Name{0}\t Score Ping'.format('\u2800'*8)
                                    summary['PlayerList{0}'.format(x)] = '{0}{1}\n```'.format(summary['PlayerList{0}'.format(x)],summary['PlayerList{0}_data'.format(x)])
                            
                            if summary['PlayerList255_data'] not in ['',None]:
                                summary['PlayerList255'] = '```Name       {0}\t       Ping'.format('\u2800'*8)
                                summary['PlayerList255'] = '{0}{1}\n```'.format(summary['PlayerList255'],summary['PlayerList255_data'])

                    # Set basic embed info
                    embedInfo.color = summary['Colour']
                    embedInfo.title = summary['Title']
                    embedInfo.description = '```unreal://{0}:{1}```'.format(queryData['ip'],queryData['game_port'])

                    if 'password' in queryData and queryData['password'] == 'True' and self.pugInfo.gameServer.format_gameServerURL=='unreal://{0}:{1}'.format(queryData['ip'],queryData['game_port']):
                        embedInfo.set_footer(text='Spectate @ {0}/?password={1}'.format(self.pugInfo.gameServer.format_gameServerURL,self.pugInfo.gameServer.spectatorPassword))

                    # Pick out info for UTA-only games
                    if 'bmatchmode' in queryData and 'gametype' in queryData and queryData['gametype'] == 'Assault':
                        # Send individual requests for objectives and UTA-enhanced team info, refresh local variable
                        self.pugInfo.gameServer.utQueryServer('objectives')
                        self.pugInfo.gameServer.utQueryServer('teams')
                        queryData = self.pugInfo.gameServer.utQueryData
    
                        if 'AdminName' in queryData and queryData['AdminName'] not in ['OPEN - PUBLIC','LOCKED - PRIVATE']:
                            # Match mode is active
                            if 'score_0' in queryData and 'score_1' in queryData:
                                if queryData['score_0'] > queryData['score_1']:
                                    summary['Colour'] = discord.Color.red()
                                elif queryData['score_0'] < queryData['score_1']:
                                    summary['Colour'] = discord.Color.blurple()
                                if 'teamnamered' in queryData and 'teamnameblue' in queryData:
                                    summary['Title'] = '{0} | {1} {2} - {3} {4}'.format(self.pugInfo.desc,queryData['teamnamered'],queryData['score_0'],queryData['score_1'],queryData['teamnameblue'])
                                else:
                                    summary['Title'] = '{0} | RED {1} - {2} BLUE'.format(self.pugInfo.desc,queryData['score_0'],queryData['score_1'])
                            summary['Hostname'] = '```unreal://{0}:{1}```'.format(queryData['ip'],queryData['game_port'])
                        elif 'AdminName' in queryData and queryData['AdminName'] in ['OPEN - PUBLIC','LOCKED - PRIVATE']:
                            summary['Hostname'] = '```unreal://{0}:{1}```'.format(queryData['ip'],queryData['game_port'])
                        # Build out round info
                        if 'bdefenseset' in queryData and 'currentdefender' in queryData:
                            if queryData['bdefenseset'] in ['true','True','1']:
                                summary['RoundStatus'] = '2/2'
                            else:
                                summary['RoundStatus'] = '1/2'
                            if queryData['currentdefender'] == '1':
                                if 'teamnamered' in queryData and queryData['AdminName'] not in ['OPEN - PUBLIC','LOCKED - PRIVATE']:
                                    summary['RoundStatus'] = '{0}\tRound {1}; {2} attacking'.format(summary['Hostname'],summary['RoundStatus'],queryData['teamnamered'])
                                else:
                                    summary['RoundStatus'] = '{0}\tRound {1}; {2} attacking'.format(summary['Hostname'],summary['RoundStatus'],'Red Team')
                            else:
                                if 'teamnameblue' in queryData and queryData['AdminName'] not in ['OPEN - PUBLIC','LOCKED - PRIVATE']:
                                    summary['RoundStatus'] = '{0}\tRound {1}; {2} attacking'.format(summary['Hostname'],summary['RoundStatus'],queryData['teamnameblue'])
                                else:
                                    summary['RoundStatus'] = '{0}\tRound {1}; {2} attacking'.format(summary['Hostname'],summary['RoundStatus'],'Blue Team')
                        if 'fortcount' in queryData:
                            summary['Objectives'] = ''
                            for x in range(int(queryData['fortcount'])):
                                if x == 0:
                                    summary['Objectives'] = ' \t {0} - {1}'.format(str(queryData['fort_{0}'.format(x)]),str(queryData['fortstatus_{0}'.format(x)]))
                                else:
                                    summary['Objectives'] = '{0}\n \t {1} - {2}'.format(summary['Objectives'],str(queryData['fort_{0}'.format(x)]),str(queryData['fortstatus_{0}'.format(x)]))
                        # Build out embed card with UTA enhanced information
                        embedInfo.color = summary['Colour']
                        embedInfo.title = summary['Title']
                        embedInfo.description = summary['RoundStatus']
                        embedInfo.add_field(name='Map',value=summary['Map'],inline=True)
                        embedInfo.add_field(name='Players',value=summary['PlayerCount'],inline=True)
                        if 'RemainingTime' in summary:
                            embedInfo.add_field(name='Time Left',value=summary['RemainingTime'],inline=True)
                        embedInfo.add_field(name='Objectives',value=summary['Objectives'],inline=False)
                    else:
                        # No UTA enhanced information available, report basic statistics
                        queryData = self.pugInfo.gameServer.utQueryData
                        embedInfo.add_field(name='Map',value=summary['Map'],inline=True)
                        embedInfo.add_field(name='Players',value=summary['PlayerCount'],inline=True)
                        if 'RemainingTime' in summary:
                            embedInfo.add_field(name='Time Left',value=summary['RemainingTime'],inline=True)
                        elif 'ElapsedTime' in summary:
                            embedInfo.add_field(name='Time Elapsed',value=summary['ElapsedTime'],inline=True)
                        elif 'TimeLimit' in summary:
                            embedInfo.add_field(name='Time Limit',value=summary['TimeLimit'],inline=True)
                        elif 'goalteamscore' in queryData and int(queryData['goalteamscore']) > 0:
                            embedInfo.add_field(name='Req. Team Score',value=queryData['goalteamscore'],inline=True)
                        elif 'fraglimit' in queryData and int(queryData['fraglimit']) > 0:
                            embedInfo.add_field(name='Frag Limit',value=queryData['fraglimit'],inline=True)
                        elif 'gametype' in queryData:
                            embedInfo.add_field(name='Mode',value=queryData['gametype'],inline=True)
                    if 'numplayers' in queryData and int(queryData['numplayers']) > 0:
                        embedInfo.add_field(name='Red Team',value=summary['PlayerList0'],inline=False)
                        embedInfo.add_field(name='Blue Team',value=summary['PlayerList1'],inline=False)

                    if summary['PlayerList255_data'] != '':
                        embedInfo.add_field(name='Spectators',value=summary['PlayerList255'],inline=False)

                    if cacheonly is False:
                        await self.utReporterChannel.send(embed=embedInfo)
                # Store the embed data for other functions to use
                self.pugInfo.gameServer.utQueryEmbedCache = embedInfo.to_dict()

        if ('code' not in self.pugInfo.gameServer.utQueryData) or ('code' in self.pugInfo.gameServer.utQueryData and self.pugInfo.gameServer.utQueryData['code'] > 400):
            # Server offline
            embedInfo.color = discord.Color.darker_gray()
            if self.pugInfo.gameServer.gameServerOnDemand is True:
                embedInfo.description = '```{0}```\nOn-demand server is currently offline. Start a !pug to use this server.'.format(self.pugInfo.gameServer.format_gameServerURL)
                self.pugInfo.gameServer.utQueryEmbedCache = embedInfo.to_dict()
            else:
                self.pugInfo.gameServer.utQueryEmbedCache = {} # fall back to old method
        return True

    def cacheGuildEmojis(self):
        if self.activeChannel is not None:
            for x in self.activeChannel.guild.emojis:
                if x.animated:
                    self.customAnimatedEmojis[':{0}:'.format(x.name)] = x.id
                else:
                    self.customStaticEmojis[':{0}:'.format(x.name)] = x.id

    #########################################################################################
    # Bot Admin ONLY commands.
    #########################################################################################
    @commands.command()
    @commands.guild_only()
    @commands.check(admin.hasManagerRole_Check)
    async def enable(self, ctx):
        """Enables PUG commands in the channel. Note only one channel can be active at a time. Admin only"""
        if self.activeChannel:
            if self.activeChannel == ctx.message.channel:
                await ctx.send('PUG commands are already enabled in {}'.format(ctx.message.channel.mention))
                return
            await self.activeChannel.send('PUG commands have been disabled in {0}. They are now enabled in {1}'.format(self.activeChannel.mention, ctx.message.channel.mention))
            await ctx.send('PUG commands have been disabled in {}'.format(self.activeChannel.mention))
        self.activeChannel = ctx.message.channel
        self.savePugConfig(self.configFile)
        await ctx.send('PUG commands are enabled in {}'.format(self.activeChannel.mention))

    @commands.command()
    @commands.guild_only()
    @commands.check(admin.hasManagerRole_Check)
    @commands.check(isActiveChannel_Check)
    @commands.check(isPugInProgress_Warn)
    async def adminadd(self, ctx, *players: discord.Member):
        """Adds a player to the pug. Admin only"""
        failed = False
        for player in players:
            if not self.pugInfo.addPlayer(player):
                failed = True
                if self.pugInfo.playersReady:
                    await ctx.send('Cannot add {0}: Pug is already full.'.format(display_name(player)))
                else:
                    await ctx.send('Cannot add {0}: They are already signed.'.format(display_name(player)))
            else:
                await ctx.send('{0} was added by an admin. {1}'.format(display_name(player), self.pugInfo.format_pug()))
        if not failed:
            await self.processPugStatus(ctx)

    @commands.command()
    @commands.guild_only()
    @commands.check(admin.hasManagerRole_Check)
    @commands.check(isActiveChannel_Check)
    @commands.check(isPugInProgress_Warn)
    async def adminremove(self, ctx, *players: discord.Member):
        """Removes a player from the pug. Admin only"""
        for player in players:
            if self.pugInfo.removePlayerFromPug(player):
                await ctx.send('**{0}** was removed by an admin.'.format(display_name(player)))
            else:
                await ctx.send('{0} is not in the pug.'.format(display_name(player)))
        await self.processPugStatus(ctx)

    @commands.command(aliases=['setserver','setactiveserver'])
    @commands.check(admin.hasManagerRole_Check)
    @commands.check(isPugInProgress_Warn)
    async def adminsetserver(self, ctx, idx: int):
        """Sets the active server to the index chosen from the pool of available servers. Admin only"""
        svindex = idx - 1 # offset as users see them 1-based index.
        if self.pugInfo.gameServer.useServer(svindex,self.pugInfo.captainsReady): # auto start eligible servers when caps are ready
            await ctx.send('Server was activated by an admin - {0}.'.format(self.pugInfo.gameServer.format_current_serveralias))
            self.pugInfo.gameServer.utQueryConsoleWatermark = self.pugInfo.gameServer.format_new_watermark
            if self.pugInfo.gameServer.gameServerState in ('N/A','N/AN/A'):
                # Check whether server is being changed when captains are already ready
                if not self.pugInfo.captainsReady:
                    await ctx.send('Server is currently offline, but will be fired up upon Captains being selected.')

            # Bit of a hack to get around the problem of a match being in progress when this is initialised. - TODO consider off state too
            # Will improve this later.
            if self.pugInfo.gameServer.lastSetupResult == 'Match In Progress':
                self.pugLocked = True
        else:
            await ctx.send('Selected server **{0}** could not be activated.'.format(idx))
    
    @commands.command(aliases=['startserver'])
    @commands.check(admin.hasManagerRole_Check)
    @commands.check(isPugInProgress_Warn)
    async def adminstartserver(self, ctx, idx: int):
        """Starts up an on-demand server. Admin only"""
        previousRef = self.pugInfo.gameServer.gameServerRef
        svindex = idx - 1 # offset as users see them 1-based index.
        if self.pugInfo.gameServer.useServer(svindex,True):
            await ctx.send('**{0}** is starting up (allow up to 60s).'.format(self.pugInfo.gameServer.gameServerName))
        else:
            await ctx.send('Selected server **{0}** could not be activated.'.format(idx))
        self.pugInfo.gameServer.useServer(-1,True,previousRef) # return to active server

    @commands.command(aliases=['stopserver'])
    @commands.check(admin.hasManagerRole_Check)
    @commands.check(isPugInProgress_Warn)
    async def adminstopserver(self, ctx, idx: int):
        """Queues up an on-demand server to shut down. Admin only"""
        svindex = idx - 1 # offset as users see them 1-based index.
        if self.pugInfo.gameServer.stopOnDemandServer(svindex):
            if len(self.pugInfo.gameServer.allServers[svindex][1]) > 0:
                await ctx.send('**{0}** is queued for shut-down.'.format(self.pugInfo.gameServer.allServers[svindex][1]))
        else:
            await ctx.send('Selected server **{0}** could not be activated.'.format(idx))

    @commands.command(aliases=['refreshservers'])
    @commands.check(admin.hasManagerRole_Check)
    @commands.check(isPugInProgress_Warn)
    async def adminrefreshservers(self, ctx):
        """Refreshes the server list within the available pool. Admin only"""
        if self.pugInfo.gameServer.validateServers():
            if len(self.pugInfo.gameServer.gameServerRotation) > 0:
                await ctx.send('Server list refreshed. Check whether the server rotation is still valid.')
            else:
                await ctx.send('Server list refreshed.')
        else:
            await ctx.send('Server list could not be refreshed.')

    @commands.command()
    @commands.check(admin.hasManagerRole_Check)
    async def adminremoveserver(self, ctx, svref: str):
        # Removed add server in favour of pulling from API; left remove server in here in case one needs temporarily removing until restart
        """Removes a server from available pool. Admin only"""
        if self.pugInfo.gameServer.removeServerReference(svref):
            await ctx.send('Server was removed from the available pool by an admin.')
        else:
            await ctx.send('Server could not be removed. Is it even in the list?')
    
    @commands.command(aliases=['setrotation','rotate'])
    @commands.check(admin.hasManagerRole_Check)
    @commands.check(isPugInProgress_Warn)
    async def adminsetserverrotation(self, ctx, *rotation: str):
        """Rotates servers weekly based on the provided servers. Admin only"""
        tempRotation = self.pugInfo.gameServer.gameServerRotation
        self.pugInfo.gameServer.gameServerRotation = []
        for index in rotation:
            if index.isdigit() and (int(index) > 0 and int(index) <= len(self.pugInfo.gameServer.allServers)):
                self.pugInfo.gameServer.gameServerRotation.append(int(index))
        # Reset to previous selection if given rotation was invalid
        if self.pugInfo.gameServer.gameServerRotation == [] and tempRotation != []:
            self.pugInfo.gameServer.gameServerRotation = tempRotation
            await ctx.send('Server rotation unchanged.')
        else:
            self.pugInfo.gameServer.saveServerConfig(self.pugInfo.gameServer.configFile)
            await ctx.send('Server rotation set to: {0}'.format(', '.join(map(str,self.pugInfo.gameServer.gameServerRotation))))

    @commands.command(aliases=['checkrotation','checkrotate'])
    @commands.check(isPugInProgress_Warn)
    async def checkserverrotation(self, ctx):
        """Checks current server and rotates accordingly."""
        tempRotation = self.pugInfo.gameServer.gameServerRef
        if len(self.pugInfo.gameServer.gameServerRotation) > 0:
            self.pugInfo.gameServer.checkServerRotation()
            if self.pugInfo.gameServer.gameServerRef != tempRotation:
                await ctx.send('Server rotation changed server to: {0}.'.format(self.pugInfo.gameServer.format_current_serveralias))
            else:
                await ctx.send('Server is already correctly set.')
        else:
            await ctx.send('Server rotation is not configured.')

    @commands.command(aliases=['getrotation'])
    async def getserverrotation(self, ctx):
        """Shows server rotation."""
        if len(self.pugInfo.gameServer.gameServerRotation) > 0:
            thisWeek = int(self.pugInfo.gameServer.gameServerRotation[int('{:0}{:0>2}'.format(datetime.now().year,datetime.now().isocalendar()[1]))%len(self.pugInfo.gameServer.gameServerRotation)])
            nextWeek = int(self.pugInfo.gameServer.gameServerRotation[int('{:0}{:0>2}'.format((datetime.now()+timedelta(weeks=1)).year,(datetime.now()+timedelta(weeks=1)).isocalendar()[1]))%len(self.pugInfo.gameServer.gameServerRotation)])
            await ctx.send('Server rotation:')
            for x in self.pugInfo.gameServer.gameServerRotation:
                svindex = int(x)-1
                if svindex >= 0 and svindex < len(self.pugInfo.gameServer.allServers):
                    if (thisWeek == int(x)):
                        await ctx.send(' - {0}{1}'.format(self.pugInfo.gameServer.allServers[svindex][1],' :arrow_forward: This week'))
                        thisWeek = -1
                    elif (nextWeek == int(x)):
                        await ctx.send(' - {0}{1}'.format(self.pugInfo.gameServer.allServers[svindex][1],' :fast_forward: Next week'))
                        nextWeek = -1
                    else:
                        await ctx.send(' - {0}'.format(self.pugInfo.gameServer.allServers[svindex][1]))
        else:
            await ctx.send('Server rotation is not configured.')

    @commands.command()
    @commands.check(admin.hasManagerRole_Check)
    async def adminaddmap(self, ctx, map: str):
        """Adds a map to the available map list. Admin only"""
        if self.pugInfo.maps.addMapToAvailableList(map):
            self.pugInfo.gameServer.saveMapConfig(self.pugInfo.gameServer.configFile, self.pugInfo.maps.availableMapsList)
            await ctx.send('**{0}** was added to the available maps by an admin. The available maps are now:\n{1}'.format(map, self.pugInfo.maps.format_available_maplist))
        else:
            await ctx.send('**{0}** could not be added. Is it already in the list?'.format(map))

    @commands.command()
    @commands.check(admin.hasManagerRole_Check)
    async def admininsertmap(self, ctx, index: int, map: str):
        """Insert a map into the available map list at the given index. Admin only"""
        if index > 0 and index <= self.pugInfo.maps.maxMapsLimit + 1:
            offset_index = index - 1 # offset as users see them 1-based index
            if self.pugInfo.maps.insertMapIntoAvailableList(offset_index, map):
                self.pugInfo.gameServer.saveMapConfig(self.pugInfo.gameServer.configFile, self.pugInfo.maps.availableMapsList)
                await ctx.send('**{0}** was inserted into the available maps by an admin. The available maps are now:\n{1}'.format(map, self.pugInfo.maps.format_available_maplist))
            else:
                await ctx.send('**{0}** could not be inserted. Is it already in the list?'.format(map))
        else:
            await ctx.send('The valid format of this command is, for example: !admininsertmap # AS-MapName, where # is in the range (1, NumMaps + 1).')

    @commands.command()
    @commands.check(admin.hasManagerRole_Check)
    async def adminreplacemap(self, ctx, *mapref: str):
        """Replaces a map within the available map list. Admin only"""
        if len(mapref) == 2 and mapref[0].isdigit() and (int(mapref[0]) > 0 and int(mapref[0]) <= len(self.pugInfo.maps.availableMapsList)):
            index = int(mapref[0]) - 1 # offset as users see in a 1-based index; the range check is performed before it gets here
            map = mapref[1]
            oldmap = self.pugInfo.maps.availableMapsList[index]
            if self.pugInfo.maps.substituteMapInAvailableList(index, map):
                self.pugInfo.gameServer.saveMapConfig(self.pugInfo.gameServer.configFile, self.pugInfo.maps.availableMapsList)
                await ctx.send('**{1}** was added to the available maps by an admin in position #{0}, replacing {2}. The available maps are now:\n{3}'.format(mapref[0],map,oldmap,self.pugInfo.maps.format_available_maplist))
            else:
                await ctx.send('**{1}** could not be added in slot {0}. Is it already in the list? Is the position valid?'.format(mapref[0],map))
        else:
            await ctx.send('The valid format of this command is, for example: !adminreplacemap # AS-MapName, where # is in the range (1, NumMaps).')

    @commands.command()
    @commands.check(admin.hasManagerRole_Check)
    async def adminremovemap(self, ctx, map: str):
        """Removes a map to from available map list. Admin only"""
        if map.isdigit():
            index = int(map) - 1 # offset as users see in a 1-based index
            mapNameToRemove = self.pugInfo.maps.getMapFromAvailableList(index)
        else:
            mapNameToRemove = map
        if self.pugInfo.maps.removeMapFromAvailableList(mapNameToRemove):
            self.pugInfo.gameServer.saveMapConfig(self.pugInfo.gameServer.configFile,self.pugInfo.maps.availableMapsList)
            await ctx.send('**{0}** was removed from the available maps by an admin.\n{1}'.format(mapNameToRemove, self.pugInfo.maps.format_available_maplist))
        else:
            await ctx.send('**{0}** could not be removed. Is it in the list?'.format(map))

    @commands.command()
    @commands.check(admin.hasManagerRole_Check)
    async def passwords(self, ctx):
        """Provides current game passwords to the requesting administrator. Admin only"""
        if self.isPugInProgress:
            await ctx.message.author.send('For the game currently running at {0}'.format(self.pugInfo.gameServer.format_gameServerURL))
            await ctx.message.author.send('{0} - {1}'.format(self.pugInfo.gameServer.format_red_password, self.pugInfo.gameServer.format_blue_password))
            await ctx.send('Check your private messages!')
        else:
            await ctx.send('There is no game in progress.')

    #########################################################################################
    # Bot commands.
    #########################################################################################
    @commands.command()
    @commands.guild_only()
    @commands.check(admin.hasManagerRole_Check)
    async def disable(self, ctx):
        """Disables PUG commands in the channel. Note only one channel can be active at a time. Admin only"""
        if self.activeChannel:
            await self.activeChannel.send('PUG commands now disabled.')
            if ctx.message.channel != self.activeChannel:
                await ctx.send('PUG commands are disabled in ' + self.activeChannel.mention)
            self.activeChannel = None
            self.savePugConfig(self.configFile)
            return
        await ctx.send('PUG commands were not active in any channels.')
    
    @commands.command(aliases = ['pug'])
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    async def list(self, ctx):
        """Displays pug status"""
        if self.pugInfo.pugLocked:
            # Pug in progress, show the teams/maps.
            await ctx.send(self.pugInfo.format_match_in_progress)
        elif self.pugInfo.teamsReady:
            # Picking maps, just display teams.
            msg = '\n'.join([
                self.pugInfo.format_pug_short,
                self.pugInfo.format_teams(),
                self.pugInfo.maps.format_current_maplist,
                self.format_pick_next_map(mention=False)])
            await ctx.send(msg)
        elif self.pugInfo.captainsReady:
            # Picking players, show remaining players to pick, but don't
            # highlight the captain to avoid annoyance.
            msg = '\n'.join([
                self.pugInfo.format_pug_short,
                self.pugInfo.format_remaining_players(number=True),
                self.pugInfo.format_teams(),
                self.format_pick_next_player(mention=False)])
            await ctx.send(msg)
        else:
            # Default, show sign ups.
            msg = []
            msg.append(self.pugInfo.format_pug())
            if self.pugInfo.playersReady:
                # Copy of what's in processPugStatus, not ideal, but avoids the extra logic it does.
                if self.pugInfo.numCaptains == 1:
                    # Need second captain.
                    msg.append('Waiting for 2nd captain. Type **!captain** to become a captain. To choose a random captain type **!randomcaptains**')
                else:
                    msg.append('Waiting for captains. Type **!captain** to become a captain. To choose random captains type **!randomcaptains**')
            await ctx.send('\n'.join(msg))

    @commands.command(aliases = ['pugtime'])
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    @commands.check(isPugInProgress_Ignore)
    async def promote(self, ctx):
        """Promotes the pug. Limited to once per minute alongside poke."""
        # TODO: Switch the use of these times of limits to use the "cooldown" decorator. see https://stackoverflow.com/questions/46087253/cooldown-for-command-on-discord-bot-python
        delay = 60
        # reusing lastpoketime, so both are limited to one of the two per 60s
        if (datetime.now() - self.lastPokeTime).total_seconds() < delay:
            return
        self.lastPokeTime = datetime.now()
        await ctx.send('Hey @here it\'s PUG TIME!!!\n**{0}** needed for **{1}**!'.format(self.pugInfo.playersNeeded, self.pugInfo.desc))

    @commands.command()
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    @commands.check(isPugInProgress_Ignore)
    async def poke(self, ctx):
        """Highlights those signed to pug. Limited to once per minute alongside promote."""
        # TODO: Switch the use of these times of limits to use the "cooldown" decorator. see https://stackoverflow.com/questions/46087253/cooldown-for-command-on-discord-bot-python
        minPlayers = 2
        delay = 60
        if self.pugInfo.numPlayers < minPlayers or (datetime.now() - self.lastPokeTime).total_seconds() < delay:
            return
        self.lastPokeTime = datetime.now()
        await ctx.send('Poking those signed (you will be unable to poke for {0} seconds): {1}'.format(delay, self.pugInfo.format_all_players(number=False, mention=True)))

    @commands.command(aliases = ['serverlist'])
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    async def listservers(self,ctx):
        await ctx.send(self.pugInfo.gameServer.format_showall_servers)

    @commands.command()
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    async def server(self, ctx):
        """Displays Pug server info"""
        await ctx.send(self.pugInfo.gameServer.format_game_server)

    @commands.command(aliases = ['serverinfo'])
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    async def serverstatus(self, ctx):
        """Displays Pug server current status"""
        await self.queryServerStats(True)
        if self.pugInfo.gameServer.utQueryEmbedCache != {}:
            embedInfo = discord.Embed().from_dict(self.pugInfo.gameServer.utQueryEmbedCache)
            # Strip objectives from the card data
            for x, f in enumerate(embedInfo.fields):
                if 'Objectives' in f.name:
                    embedInfo.remove_field(x)
            await ctx.message.channel.send(embed=embedInfo)
        else:
            await ctx.send(self.pugInfo.gameServer.format_game_server_status)

    @commands.command()
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    async def serverquery(self, ctx, serveraddr: str):
        """Displays status of a given server"""
        serverinfo = {}
        if (self.pugInfo.gameServer.utQueryReporterActive or self.pugInfo.gameServer.utQueryStatsActive):
            await ctx.send('Server query cannot be run while pug reporting is in progress.')
        else:
            if serveraddr not in ['',None]:
                # Check for valid server input
                for x in ['unreal://','\w+://','\\\\','localhost','^127\.']:
                    try:
                        serveraddr = re.compile(x).sub('', serveraddr)
                    except:
                        log.error('Failed to parse input to !serverquery')
                # Check for IP with or without port, or FQDN with or without port
                for x in ['^(?P<ip>((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)):(?P<port>\d{1,5})$',
                          '^(?P<ip>((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?))$',
                          '^(?P<dns>(?=^.{4,253}$)(^((?!-)[a-zA-Z0-9-]{1,63}(?<!-)\.)+[a-zA-Z]{2,63})):(?P<port>\d{1,5})$',
                          '^(?P<dns>(?=^.{4,253}$)(^((?!-)[a-zA-Z0-9-]{1,63}(?<!-)\.)+[a-zA-Z]{2,63})$)']:
                    if re.search(x,serveraddr):
                        servermatch = re.match(r'{0}'.format(x),serveraddr)
                        if 'ip' not in servermatch.groupdict() and 'dns' in servermatch.groupdict():
                            try:
                                for ip in dns.resolver.resolve(servermatch['dns'], 'A'):
                                    serverinfo['ip'] = ip.address
                            except:
                                log.warn('DNS lookup failure for {0}'.format(serveraddr))
                            if 'port' in servermatch.groupdict():
                                serverinfo['game_port'] = int(servermatch.groupdict()['port'])
                            else:
                                serverinfo['game_port'] = 7777
                        elif 'ip' in servermatch.groupdict() and 'port' in servermatch.groupdict():
                            serverinfo['ip'] = servermatch.groupdict()['ip']
                            serverinfo['game_port'] = int(servermatch.groupdict()['port'])
                        elif 'ip' in servermatch.groupdict():
                            serverinfo['ip'] = servermatch.groupdict()['ip']
                            serverinfo['game_port'] = 7777
            if serverinfo != {}:
                serverinfo['query_port'] = int(serverinfo['game_port'])+1
                # Set the utQueryData base
                self.pugInfo.gameServer.utQueryData = serverinfo
                await self.queryServerStats(True)
                if self.pugInfo.gameServer.utQueryEmbedCache != {}:
                    embedInfo = discord.Embed().from_dict(self.pugInfo.gameServer.utQueryEmbedCache)
                    # Reset caches
                    self.pugInfo.gameServer.utQueryData = {}
                    self.pugInfo.gameServer.utQueryEmbedCache = {}
                    # Strip objectives from the card data
                    for x, f in enumerate(embedInfo.fields):
                        if 'Objectives' in f.name:
                            embedInfo.remove_field(x)
                    await ctx.message.channel.send(embed=embedInfo)
                else:
                    await ctx.send('Could not resolve server from provided information.')
            else:
                await ctx.send('Could not resolve server from provided information.')

    @commands.command()
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    async def listmodes(self, ctx):
        """Lists available modes for the pug"""
        outStr = ['Available modes are:']
        for k in MODE_CONFIG:
            outStr.append(PLASEP + '**' + k + '**')
        outStr.append(PLASEP)
        await ctx.send(' '.join(outStr))

    @commands.command()
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    @commands.check(isPugInProgress_Warn)
    async def setmode(self, ctx, mode):
        """Sets mode of the pug"""
        if self.pugInfo.captainsReady:
            await ctx.send('Pug already in picking mode. Reset if you wish to change mode.')
        else:
            result = self.pugInfo.setMode(mode)
            # Send result message to channel regardless of success/failure
            await ctx.send(result[1])
            # If mode successfully changed, process pug status
            if result[0]:
                await self.processPugStatus(ctx)

    @commands.command()
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    @commands.check(isPugInProgress_Warn)
    async def setplayers(self, ctx, limit: int):
        """Sets number of players"""
        if self.pugInfo.captainsReady:
            await ctx.send('Pug already in picking mode. Reset if you wish to change player limit.')
        elif (limit > 1 and limit % 2 == 0 and limit <= MODE_CONFIG[self.pugInfo.mode].maxPlayers):
            self.pugInfo.setMaxPlayers(limit)
            await ctx.send('Player limit set to ' + str(self.pugInfo.maxPlayers))
            await self.processPugStatus(ctx)
        else:
            await ctx.send('Player limit unchanged. Players must be a multiple of 2 + between 2 and ' + str(MODE_CONFIG[self.pugInfo.mode].maxPlayers))

    @commands.command()
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    @commands.check(isPugInProgress_Warn)
    async def setmaps(self, ctx, limit: int):
        """Sets number of maps"""
        if (self.pugInfo.maps.setMaxMaps(limit)):
            await ctx.send('Map limit set to ' + str(self.pugInfo.maps.maxMaps))
            if self.pugInfo.teamsReady:
                # Only need to do this if maps already being picked, as it could mean the pug needs to be setup.
                await self.processPugStatus(ctx)
        else:
            await ctx.send('Map limit unchanged. Map limit is {}'.format(self.pugInfo.maps.maxMapsLimit))

    @commands.command()
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    async def reset(self, ctx):
        """Resets the pug. Players will need to rejoin. This will reset the server, even if a match is running. Use with care."""
        reset = False
        if (admin.hasManagerRole_Check(ctx) or not(self.pugInfo.pugLocked or (self.pugInfo.gameServer and self.pugInfo.gameServer.matchInProgress))):
            reset = True
        else:
            requester = ctx.message.author
            if requester in self.pugInfo.red:
                if self.resetRequestRed:
                    await ctx.send('Red team have already requested reset. Blue team must also request.')
                else:
                    self.resetRequestRed = True
                    await ctx.send('Red team have requested reset. Blue team must also request.')
            elif requester in self.pugInfo.blue:
                if self.resetRequestBlue:
                    await ctx.send('Blue team have already requested reset. Red team must also request.')
                else:
                    self.resetRequestBlue = True
                    await ctx.send('Blue team have requested reset. Red team must also request.')
            else:
                await ctx.send('Pug is in progress, only players involved the pug or admins can reset.')
            if self.resetRequestRed and self.resetRequestBlue:
                self.resetRequestRed = False
                self.resetRequestBlue = False
                reset = True
        if reset:
            await ctx.send('Removing all signed players: {}'.format(self.pugInfo.format_all_players(number=False, mention=True)))
            if self.pugInfo.resetPug():
                await ctx.send('Pug Reset. {}'.format(self.pugInfo.format_pug_short))
            else:
                await ctx.send('Reset failed. Please, try again or inform an admin.')

    @commands.command(aliases=['replay'])
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    async def retry(self, ctx):
        if self.pugInfo.gameServer.matchInProgress is False or self.pugInfo.gameServer.gameServerOnDemand:
            retryAllowed = True
        else:
            retryAllowed = False

        if self.pugInfo.matchReady and retryAllowed:
            await self.processPugStatus(ctx)
        else:
            # TODO: Recall saved data from last match and play it back into the bot
            await ctx.send('Retry can only be utilised after a failed setup.')

    @commands.command(aliases=['resetcaps','resetcap'])
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    @commands.check(isPugInProgress_Warn)
    async def resetcaptains(self, ctx):
        """Resets back to captain mode. Any players or maps picked will be reset."""
        if self.pugInfo.numCaptains < 1 or self.pugInfo.pugLocked:
            return

        self.pugInfo.maps.resetMaps()
        self.pugInfo.softPugTeamReset()
        await ctx.send('Captains have been reset.')
        await self.processPugStatus(ctx)

    @commands.command(aliases=['j'])
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    @commands.check(isPugInProgress_Warn)
    async def join(self, ctx):
        """Joins the pug"""
        player = ctx.message.author
        if not self.pugInfo.addPlayer(player):
            if self.pugInfo.playersReady:
                await ctx.send('Pug is already full.')
                return
            else:
                await ctx.send('Already added.')
                return

        await ctx.send('{0} was added. {1}'.format(display_name(player), self.pugInfo.format_pug()))
        await self.processPugStatus(ctx)

    @commands.command(aliases=['l', 'lva'])
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    @commands.check(isPugInProgress_Warn)
    async def leave(self, ctx):
        """Leaves the pug"""
        player = ctx.message.author
        if self.pugInfo.removePlayerFromPug(player):
            await ctx.send('{0} left.'.format(display_name(player)))
            await self.processPugStatus(ctx)

    @commands.command(aliases=['cap','сфзефшт'])
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    @commands.check(isPugInProgress_Ignore)
    async def captain(self, ctx):
        """Volunteer to be a captain in the pug"""
        if not self.pugInfo.playersReady or self.pugInfo.captainsReady or self.pugInfo.gameServer.matchInProgress:
            log.debug('!captain rejected: Players Ready = {0}, Captains Ready = {1}, Match In Progress {2}'.format(self.pugInfo.playersReady,self.pugInfo.captainsReady,self.pugInfo.gameServer.matchInProgress))
            return

        player = ctx.message.author
        if self.pugInfo.setCaptain(player):
            await ctx.send(player.mention + ' has volunteered as a captain!')
            await self.processPugStatus(ctx)

    @commands.command(aliases=['randcap'])
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    @commands.check(isPugInProgress_Ignore)
    async def randomcaptains(self, ctx):
        """Picks a random captain for each team without a captain."""
        if not self.pugInfo.playersReady or self.pugInfo.captainsReady:
            return

        while not self.pugInfo.captainsReady:
            pick = None
            while not pick:
                pick = random.choice(self.pugInfo.players)
            self.pugInfo.setCaptain(pick)
        await self.processPugStatus(ctx)

    @commands.command(aliases=['p'])
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    async def pick(self, ctx, *players: int):
        """Picks a player for a team in the pug"""
        captain = ctx.message.author
        # TODO: improve this, don't think we should use matchInProgress
        if self.pugInfo.teamsFull or not self.pugInfo.captainsFull or not captain == self.pugInfo.currentCaptainToPickPlayer or self.pugInfo.pugLocked or self.pugInfo.gameServer.matchInProgress:
            return

        picks = list(itertools.takewhile(functools.partial(self.pugInfo.pickPlayer, captain), (x - 1 for x in players)))

        if picks:
            if self.pugInfo.teamsFull:
                await ctx.send('Teams have been selected:\n{}'.format(self.pugInfo.format_teams(mention=True)))
            await self.processPugStatus(ctx)

    @commands.command(aliases=['maplist'])
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    async def listmaps(self, ctx):
        """Returns the list of maps to pick from"""
        msg = ['Server map list is: ']
        msg.append(self.pugInfo.maps.format_available_maplist)
        await ctx.send('\n'.join(msg))

    @commands.command(aliases=['m'])
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    async def map(self, ctx, idx: int):
        """Picks a map in the pug"""

        captain = ctx.message.author
        if (self.pugInfo.matchReady or not self.pugInfo.teamsReady or captain != self.pugInfo.currentCaptainToPickMap):
            # Skip if not in captain mode with full teams or if the author is not the next map captain.
            return

        mapIndex = idx - 1 # offset as users see them 1-based index.
        if mapIndex < 0 or mapIndex >= len(self.pugInfo.maps.availableMapsList):
            await ctx.send('Pick a valid map. Use !map <map_number>. Use !listmaps to see the list of available maps.')
            return

        if not self.pugInfo.pickMap(captain, mapIndex):
            await ctx.send('Map already picked or maximum number of non-regular maps reached. Please, pick a different map.')
        
        msg = ['Maps chosen **({0} of {1})**:'.format(len(self.pugInfo.maps), self.pugInfo.maps.maxMaps)]
        msg.append(self.pugInfo.maps.format_current_maplist)
        await ctx.send(' '.join(msg))
        await self.processPugStatus(ctx)

    @commands.command()
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    async def last(self, ctx):
        """Shows the last pug info"""
        if self.pugInfo.gameServer.matchInProgress:
            msg = ['Last match not complete...']
            msg.append(self.pugInfo.format_match_in_progress)
            await ctx.send('\n'.join(msg))
        else:
            await ctx.send(self.pugInfo.format_last_pug)

    @commands.command(aliases = ['setrep','repchan'])
    @commands.guild_only()
    @commands.check(admin.hasManagerRole_Check)
    async def setreporter(self, ctx):
        """Configures the UT Server Reporter channel. Admin only"""
        self.utReporterChannel = ctx.message.channel
        await ctx.send('UT Reporter threads will be active in this channel for the next PUG.')
        return

    @commands.command(aliases = ['muterep'])
    @commands.guild_only()
    @commands.check(admin.hasManagerRole_Check)
    async def mutereporter(self, ctx):
        """Mutes the UT Server Reporter until the next active pug. Admin only"""
        if (self.pugInfo.gameServer.utQueryReporterActive or self.pugInfo.gameServer.utQueryStatsActive) and self.utReporterChannel is not None:
            self.pugInfo.gameServer.utQueryReporterActive = False
            self.pugInfo.gameServer.utQueryStatsActive = False
            await ctx.send('Muted UT Reporter threads in the reporter channel')
        else:
            await ctx.send('UT Reporter channel not defined, or threads not currently running.')
        return

    @commands.command(aliases = ['startrep','forcerep'])
    @commands.guild_only()
    @commands.check(admin.hasManagerRole_Check)
    async def startreporter(self, ctx):
        """Force-starts the UT Server Reporter, whether an active pug is running or not. Admin only"""
        if self.pugInfo.gameServer.utQueryStatsActive or self.pugInfo.gameServer.utQueryReporterActive:
            if self.utReporterChannel is None:
                await ctx.send('UT Reporter channel has not yet been configured, use **!setreporter** to configure the target channel.')
            elif self.utReporterChannel != ctx.message.channel:
                await ctx.send('UT Reporter is already active in another channel.')
            else:
                await ctx.send('UT Reporter is already active in this channel.')
        else:
            if self.pugInfo.gameServer.utQueryServer('info'):
                self.utReporterChannel = ctx.message.channel
                if 'code' in self.pugInfo.gameServer.utQueryData and self.pugInfo.gameServer.utQueryData['code'] == 200:
                    self.pugInfo.gameServer.utQueryStatsActive = True
                    self.pugInfo.gameServer.utQueryReporterActive = True
                    await ctx.send('Force-started UT Reporter threads in this channel')
        return
async def setup(bot):
    await bot.add_cog(PUG(bot, DEFAULT_CONFIG_FILE))
