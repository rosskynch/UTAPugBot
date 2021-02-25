import collections
import time
import asyncpg
from datetime import datetime
import functools
import itertools
import random
import re
import requests # should replace with aiohttp. See https://discordpy.readthedocs.io/en/latest/faq.html#what-does-blocking-mean
import json
import discord
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
DEFAULT_POST_SERVER = 'https://www.utassault.net'
DEFAULT_POST_TOKEN = 'NoToken'
DEFAULT_CONFIG_FILE = 'servers/config.json'

# Valid modes with default config
Mode = collections.namedtuple('Mode', 'maxPlayers friendlyFireScale mutators')
MODE_CONFIG = {
    "stdAS": Mode(12, 0, None),
    "proAS": Mode(8, 100, None),
    "lcAS": Mode(12, 0, "LCWeapons_0025uta.LCMutator"),
    "iAS": Mode(8, 0, "LeagueAS-SP.iAS"),
    "ZPiAS": Mode(8, 0, "ZeroPingPlus103.ColorAccuGib")
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

# Server list:
#  List of Tuples, first element is the API reference, second element is the placeholder
#  Name / Description of the server, which is updated after a successful check.
#  This hardcoded list will be replaced through JSON config upon bot load, and subsequently
#  verified against the online API.

DEFAULT_SERVER_LIST = [
    ("pugs1","UTA Pug Server 1.uk")
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
# Utilities
#########################################################################################

resetRequest = collections.namedtuple('resetRequest', 'red blue')

def discord_md_escape(value):
    return DISCORD_MD_ESCAPE_RE.sub(lambda match: DISCORD_MD_ESCAPE_DICT[match.group(0)], value)

def display_name(member):
    return discord_md_escape(member.display_name)

def getDuration(then, now, interval = "default"):
    # Adapted from https://stackoverflow.com/a/47207182
    duration = now - then
    duration_in_s = duration.total_seconds()

    def years():                    return divmod(duration_in_s, 31536000) # Seconds in a year = 31536000.
    def days(seconds = None):       return divmod(seconds if seconds != None else duration_in_s, 86400) # Seconds in a day = 86400
    def hours(seconds = None):      return divmod(seconds if seconds != None else duration_in_s, 3600) # Seconds in an hour = 3600
    def minutes(seconds = None):    return divmod(seconds if seconds != None else duration_in_s, 60) # Seconds in a minute = 60
    def seconds(seconds = None):    return divmod(seconds, 1) if seconds != None else duration_in_s
    def totalDuration():
        y = years()
        d = days(y[1]) # Use remainder to calculate next variable
        h = hours(d[1])
        m = minutes(h[1])
        s = seconds(m[1])
        msg = []
        if y[0] > 0: msg.append('{} years'.format(int(y[0])))
        if d[0] > 0: msg.append('{} days'.format(int(d[0])))
        if h[0] > 0: msg.append('{} hours'.format(int(h[0])))
        if m[0] > 0: msg.append('{} minutes'.format(int(m[0])))
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

    def addMapToAvailableList(self, map: str):
        # Can't really verify the map, but ignore blank/None inputs.
        if map not in self.availableMapsList and map not in [None, '']:
            self.availableMapsList.append(map)
            return True
        return False

    def substituteMapInAvailableList(self, index: int, map: str):
        # Index is already checked
        if map not in self.availableMapsList and map not in [None, '']:
            self.availableMapsList[index] = map
            return True
        return False

    def removeMapFromAvailableList(self, map: str):
        # Can't really verify the map, but ignore blank/None inputs.
        if map and map in self.availableMapsList:
            self.availableMapsList.remove(map)
            return True
        return False

    def getMapFromAvailableList(self, index: int):
        if index < 0 or index >= len(self.availableMapsList):
            return None
        return self.availableMapsList[index]

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
    def __init__(self, maxPlayers, pickMode):
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
        return sum([self.red.captain != None, self.blue.captain != None])

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
            if self.red:
                self.softPugTeamReset()
            self.removePlayer(player)
            return True
        return False

    def softPugTeamReset(self):
        if self.red:
            self.players += self.red + self.blue
            self.players = list(filter(None, self.players))
            self.red.clear()
            self.blue.clear()
            self.here = [True, True]
            return True
        return False

    def fullPugTeamReset(self):
        self.players = []
        self.red.clear()
        self.blue.clear()
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
    def __init__(self, configFile=DEFAULT_CONFIG_FILE):
        # Initialise the class with hardcoded defaults, then parse in JSON config
        self.configFile = configFile
        self.configMaps = []
        # All servers
        self.allServers = DEFAULT_SERVER_LIST
        
        # POST server and game server info:
        self.postServer = DEFAULT_POST_SERVER
        self.authtoken = DEFAULT_POST_TOKEN

        # Chosen game server deetails
        self.gameServerRef = DEFAULT_GAME_SERVER_REF
        self.gameServerIP = DEFAULT_GAME_SERVER_IP
        self.gameServerPort = DEFAULT_GAME_SERVER_PORT
        self.gameServerName = DEFAUlT_GAME_SERVER_NAME
        
        # Setup details
        self.redPassword = DEFAULT_RED_PASSWORD
        self.bluePassword = DEFAULT_BLUE_PASSWORD
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
                    print('setupapi not found in config file.')
                if 'maplist' in info and len(info['maplist']):
                    print('Loaded {0} maps from config.json'.format(len(info['maplist'])))
                    self.configMaps = info['maplist']
                else:
                    print('Maplist not found in config file.')

                # Iterate through local cache of servers, and set the default if present
                if 'serverlist' in info and len(info['serverlist']):
                    for server in info['serverlist']:
                        self.updateServerReference(server['serverref'],server['servername'])
                        if 'serverdefault' in server.keys():
                            self.gameServerRef = server['serverref']
                else:
                    print('Serverlist not found in config file.')
            else:
                print("GameServer: Config file could not be loaded: {0}".format(configFile))
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
                    # allServers[x][3] = server url
                    serverinfo = {"serverref": s[0], "servername": s[1], "serverurl": s[2]}
                    if s[0] == self.gameServerRef:
                        serverinfo["serverdefault"] = True
                    info['serverlist'].append(serverinfo)
            f.close()
        with open(configFile, 'w') as f:
            json.dump(info, f, indent=4)
            f.close()
        return True

    #########################################################################################
    # Formatted JSON
    #########################################################################################
    @property
    def format_post_header_auth(self):
        fmt = {
                "Content-Type": "application/json; charset=UTF-8",
                "PugAuth": '{}'.format(self.authtoken)
        }
        return fmt

    @property
    def format_post_header_check(self):
        fmt = self.format_post_header_auth
        fmt.update({"Mode": "check"})
        return fmt
    
    @property
    def format_post_header_list(self):
        fmt = self.format_post_header_auth
        fmt.update({"Mode": "list"})
        return fmt
    
    @property
    def format_post_header_setup(self):
        fmt = self.format_post_header_auth
        fmt.update({"Mode": "setup"})
        return fmt

    @property
    def format_post_header_endgame(self):
        fmt = self.format_post_header_auth
        fmt.update({"Mode": "endgame"})
        return fmt

    def format_post_body_serverref(self):
        fmt = {
            "server": self.gameServerRef
        }
        return fmt

    def format_post_body_setup(self, numPlayers, maps, mode):
        fmt = {
            "server": self.gameServerRef,
            "authEnabled": True,
            "tiwEnabled": True,
            "matchLength": len(maps),
            "maxPlayers": numPlayers,
            "specLimit": self.numSpectators,
            "redPass": self.redPassword,
            "bluePass": self.bluePassword,
            "specPass": self.spectatorPassword,
            "maplist": maps,
            "gameType": "LeagueAS140.LeagueAssault",
            "mutators": MODE_CONFIG[mode].mutators,
            "friendlyFireScale": MODE_CONFIG[mode].friendlyFireScale,
            "initialWait": 180
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
            'uk':':flag_gb:',
            'fr':':flag_fr:',
            'nl':':flag_nl:',
            'de':':flag_de:',
            'us':':flag_us:'
        }
        msg = []
        i = 0
        for s in self.allServers:
            i += 1
            servername = '{0}'.format(s[1])
            for flag in flags:
                servername  = re.compile(flag, re.IGNORECASE).sub(flags[flag], servername)
                #servername = servername.replace(flag, flags[flag])
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

    #########################################################################################
    # Functions:
    ######################################################################################### 
    def makePostRequest(self, server, headers, json=None):
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

    def updateServerReference(self, serverref: str, serverdesc: str, serverurl: str = ''):
        if serverref in self.current_serverrefs() and serverref not in [None, '']:
            self.allServers.pop(self.current_serverrefs().index(serverref))
        self.allServers.append((serverref, serverdesc, serverurl))
        return True
    
    def useServer(self, index: int):
        """Sets the active server"""
        if index >= 0 and index < len(self.allServers):
            self.gameServerRef = self.allServers[index][0]
            self.updateServerStatus()
            self.saveServerConfig(self.configFile)
            return True
        return False

    def generatePasswords(self):
        """Generates random passwords for red and blue teams."""
        # Spectator password is not changed, think keeping it fixed is fine.
        self.redPassword = RED_PASSWORD_PREFIX + str(random.randint(0, 999))
        self.bluePassword = BLUE_PASSWORD_PREFIX + str(random.randint(0, 999))

    def getServerList(self, restrict: bool = False, delay: int = 0, allservers: bool = True):
        if restrict and (datetime.now() - self.lastUpdateTime).total_seconds() < delay:
            # 5 second delay between requests when restricted.
            return None

        if allservers:
            r = self.makePostRequest(self.postServer, self.format_post_header_list)
        else:
            body = self.format_post_body_serverref()
            r = self.makePostRequest(self.postServer, self.format_post_header_list, body)

        self.lastUpdateTime = datetime.now()
        if(r):            
            return r.json()
        else:
            return None

    def validateServers(self):
        if len(self.allServers):
            info = self.getServerList()
            if info and len(info):
                # firstly, determine if the primary server is online and responding, then drop the local list
                serverDefaultPresent = False
                for svc in info:
                    if svc['serverDefault'] == True and svc['serverStatus']['Summary'] not in [None,'','N/A','N/AN/A']:
                        # If for whatever reason the default server isn't working, then stick to local list for now.
                        serverDefaultPresent = True
                        break

                if serverDefaultPresent:
                    # Default is present and working, re-iterate through list and populate local var
                    self.allServers = []
                    for sv in info:
                        if sv['serverStatus']['Summary'] not in [None, '', 'N/A', 'N/AN/A']:
                            self.updateServerReference(sv['serverRef'], sv['serverName'],'unreal://{0}:{1}'.format(sv['serverAddr'], sv['serverPort']))

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
        r = self.makePostRequest(self.postServer, self.format_post_header_check, body)
        self.lastUpdateTime = datetime.now()
        if(r):
            return r.json()
        else:
            return None

    def updateServerStatus(self):
        info = self.getServerStatus()
        if info:
            self.gameServerName = info["serverName"]
            self.gameServerIP = info["serverAddr"]
            self.gameServerPort = info["serverPort"]
            if not self.endMatchPerformed:
                self.matchInProgress = info["matchStarted"]
            self.lastSetupResult = info["setupResult"]
            self.lastCheckJSON = info
            return True
        self.lastSetupResult = 'Failed'
        return False

    def setupMatch(self, numPlayers, maps, mode):
        if not self.updateServerStatus() or self.matchInProgress:
            return False

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

            # Get passwords from the server (doesn't currently seem to accept them)
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
        self.servers = [GameServer(configFile)]
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
        if self.teamsFull and self.maps.mapsFull:
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
    def format_players(self, players, number=False, mention=False):
        def name(p):
            return p.mention if mention else display_name(p)
        numberedPlayers = ((i, name(p)) for i, p in enumerate(players, 1) if p)
        fmt = '**{0})** {1}' if number else '{1}'
        return PLASEP.join(fmt.format(*x) for x in numberedPlayers)

    def format_all_players(self, number=False, mention=False):
        return self.format_players(self.all, number=number, mention=mention)

    def format_remaining_players(self, number=False, mention=False):
        return self.format_players(self.players, number=number, mention=mention)

    def format_red_players(self, number=False, mention=False):
        return self.format_players(self.red, number=number, mention=mention)

    def format_blue_players(self, number=False, mention=False):
        return self.format_players(self.blue, number=number, mention=mention)

    def format_teams(self, number=False, mention=False):
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

    def removeServer(self, index):
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

                if not result:
                    time.sleep(5)
                else:
                    self.pugLocked = True
                    self.storeLastPug()
                    return True
        return False

    def storeLastPug(self):
        if self.matchReady:
            fmt = []
            fmt.append('Last **{}** ({} ago)'.format(self.desc, '{}'))
            fmt.append(self.format_teams())
            fmt.append('Maps:\n{}'.format(self.maps.format_current_maplist))
            self.lastPugStr = '\n'.join(fmt)
            self.lastPugTimeStarted = datetime.now()
            return True
        return False

    def resetPug(self):
        self.maps.resetMaps()
        self.fullPugTeamReset()
        if self.pugLocked or (self.gameServer and self.gameServer.matchInProgress):
        # Is this a good idea? Might get abused.
            self.gameServer.endMatch()
        self.pugLocked = False
        return True

    def setMode(self, mode):
        # Dictionaries are case sensitive, so we'll do a map first to test case-insensitive input, then find the actual key after
        if mode.upper() in map(str.upper, MODE_CONFIG):
            ## Iterate through the keys to find the actual case-insensitive mode
            mode = next((key for key, value in MODE_CONFIG.items() if key.upper()==mode.upper()), None)

            ## ProAS and iAS are played with a different maximum number of players.
            ## Can't change mode from std to pro/ias if more than the maximum number of players allowed for these modes are signed.
            if mode.upper() != "STDAS" and mode.upper() != "LCAS" and len(self.players) > MODE_CONFIG[mode].maxPlayers:
                return False, str(MODE_CONFIG[mode].maxPlayers) + " or less players must be signed for a switch to " + mode
            else:
                ## If max players is more than mode max and there aren't more than mode max players signed, automatically reduce max players to mode max.
                if mode.upper() != "STDAS" and mode.upper() != "LCAS" and self.maxPlayers > MODE_CONFIG[mode].maxPlayers:
                    self.setMaxPlayers(MODE_CONFIG[mode].maxPlayers)
                self.mode = mode
                self.desc = 'Assault ' + mode + ' PUG'
                return True, "Pug mode changed to: **" + mode + "**"
        else:
            outStr = ["Mode not recognised. Valid modes are:"]
            for k in MODE_CONFIG:
                outStr.append(PLASEP + "**" + k + "**")
            outStr.append(PLASEP)
            return False, " ".join(outStr)
        

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
        self.pugInfo = AssaultPug(DEFAULT_PLAYERS, DEFAULT_MAPS, DEFAULT_PICKMODETEAMS, DEFAULT_PICKMODEMAPS, configFile)
        self.configFile = configFile

        self.loadPugConfig(configFile)

        # Used to keep track of if both teams have requested a reset while a match is in progress.
        # We'll only make use of this in the reset() function so it only needs to be put back to
        # (False, False) when a new match is setup.
        self.resetRequest = resetRequest(False, False)

        # Start the looped task which checks the server when a pug is in progress (to detect match finished)
        self.updateGameServer.add_exception_type(asyncpg.PostgresConnectionError)
        self.updateGameServer.start()

        self.lastPokeTime = datetime.now()

    def cog_unload(self):
        self.updateGameServer.cancel()

#########################################################################################
# Loops.
#########################################################################################
    @tasks.loop(seconds=60.0)
    async def updateGameServer(self):
        if self.pugInfo.pugLocked:
            print('Updating game server...\n')
            if not self.pugInfo.gameServer.updateServerStatus():
                print('Cannot contact game server.\n')
            if self.pugInfo.gameServer.processMatchFinished():
                await self.activeChannel.send('Match finished. Resetting pug...')
                if self.pugInfo.resetPug():
                    await self.activeChannel.send(self.pugInfo.format_pug())
                    print('Match over.')
                    return
                await self.activeChannel.send('Reset failed.')
                print('Reset failed')

    @updateGameServer.before_loop
    async def before_updateGameServer(self):
        print('Waiting before updating game server...')
        await self.bot.wait_until_ready()
        print('Ready.')

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
                    print("Loaded active channel id: {0} => channel: {1}".format(channelID, channel))
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
                        print("No active channel id found in config file.")
            else:
                print("PUG: Config file could not be loaded: {0}".format(configFile))
            f.close()
        return True

    def savePugConfig(self, configFile):
        with open(configFile) as f:
            info = json.load(f)
            last_active_channel_id = info['pug']['activechannelid']
            if 'pug' not in info:
                info['pug'] = {}
            if self.activeChannel:
                info['pug']['activechannelid'] = self.activeChannel.id
            else:
                info['pug']['activechannelid'] = 0
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
                    for p in self.pugInfo.players:
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

    def format_pick_next_player(self, mention=False):
        player = self.pugInfo.currentCaptainToPickPlayer
        return '{} to pick next player (**!pick <number>**)'.format(player.mention if mention else display_name(player))

    def format_pick_next_map(self, mention=False):
        player = self.pugInfo.currentCaptainToPickMap
        return '{} to pick next map (use **!map <number>** to pick and **!listmaps** to view available maps)'.format(player.mention if mention else display_name(player))

    #########################################################################################
    # Functions:
    #########################################################################################

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if error is PugIsInProgress:
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

    async def processPugStatus(self, ctx):
        # Big function to test which stage of setup we're at:
        if not self.pugInfo.playersFull:
            # Not filled, nothing to do.
            return

        # Work backwards from match ready.
        # Note match is ready once players are full, captains picked, players picked and maps picked.
        if self.pugInfo.mapsReady and self.pugInfo.matchReady:
            if self.pugInfo.setupPug():
                await self.sendPasswordsToTeams()
                await ctx.send(self.pugInfo.format_match_is_ready)
                self.resetRequest = resetRequest(False, False) # only need to reset this here because we only care about this when a match is in progress.
            else:
                msg = ['**PUG Setup Failed**. Try again or contact an admin.']
                msg.append('Resetting...')
                await ctx.send('\n'.join(msg))
                self.pugInfo.resetPug()
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
                await self.processPugStatus(ctx)
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
            raise PugIsInProgress("Pug In Progress")
        return not self.pugInfo.pugLocked

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
        "Adds a player to the pug. Admin only"
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
        if self.pugInfo.gameServer.useServer(svindex):
            await ctx.send('Server was activated by an admin - {0}.'.format(self.pugInfo.gameServer.format_current_serveralias))

            # Bit of a hack to get around the problem of a match being in progress when this is initialised.
            # Will improve this later.
            if self.pugInfo.gameServer.lastSetupResult == 'Match In Progress':
                self.pugLocked = True
        else:
            await ctx.send('Selected server **{0}** could not be activated.'.format(idx))

    @commands.command()
    @commands.check(admin.hasManagerRole_Check)
    @commands.check(isPugInProgress_Warn)
    async def refreshservers(self, ctx):
        """Refreshes the server list within the available pool. Admin only"""
        if self.pugInfo.gameServer.validateServers():
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
    async def adminreplacemap(self, ctx, *mapref: str):
        """Replaces a map within the available map list. Admin only"""
        if len(mapref) == 2 and mapref[0].isdigit() and (int(mapref[0]) > 0 and int(mapref[0]) <= len(self.pugInfo.maps.availableMapsList)):
            index = int(mapref[0]) - 1 # offset as users see them 1-based index; the range check is performed before it gets here
            map = mapref[1]
            oldmap = self.pugInfo.maps.availableMapsList[index]
            if self.pugInfo.maps.substituteMapInAvailableList(index, map):
                self.pugInfo.gameServer.saveMapConfig(self.pugInfo.gameServer.configFile, self.pugInfo.maps.availableMapsList)
                await ctx.send('**{1}** was added to the available maps by an admin in position #{0}, replacing {2}. The available maps are now:\n{3}'.format(mapref[0],map,oldmap,self.pugInfo.maps.format_available_maplist))
            else:
                await ctx.send('**{1}** could not be added in slot {0}. Is it already in the list? Is the position valid?'.format(mapref[0],map))
        else:
            await ctx.send('The valid format of this command is, for example: !adminreplacemap # AS-MapName, where # is a valid integer within the existing maplist.')

    @commands.command()
    @commands.check(admin.hasManagerRole_Check)
    async def adminremovemap(self, ctx, map: str):
        """Removes a map to from available map list. Admin only"""
        if self.pugInfo.maps.removeMapFromAvailableList(map):
            self.pugInfo.gameServer.saveMapConfig(self.pugInfo.gameServer.configFile,self.pugInfo.maps.availableMapsList)
            await ctx.send('**{0}** was removed from the available maps by an admin.\n{1}'.format(map, self.pugInfo.maps.format_available_maplist))
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

    @commands.command()
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    async def serverstatus(self, ctx):
        """Displays Pug server current status"""
        await ctx.send(self.pugInfo.gameServer.format_game_server_status)

    @commands.command()
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    async def listmodes(self, ctx):
        """Lists available modes for the pug"""
        outStr = ["Available modes are:"]
        for k in MODE_CONFIG:
            outStr.append(PLASEP + "**" + k + "**")
        outStr.append(PLASEP)
        await ctx.send(" ".join(outStr))

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
        if not admin.hasManagerRole_Check(ctx) and (self.pugLocked or self.pugInfo.gameServer.matchInProgress):
            if not self.resetRequest and ctx.author in self.pugInfo.red:
                self.resetRequest.red = True
                await ctx.send('Red team have requested reset.')
            elif not self.resetRequest and ctx.author in self.pugInfo.blue:
                self.resetRequest.blue = True
                await ctx.send('Blue team have requested reset.')
            if not self.resetRequest.red or not self.resetRequest.blue:
                return

        await ctx.send('Removing all signed players: {}'.format(self.pugInfo.format_all_players(number=False, mention=True)))
        if self.pugInfo.resetPug():
            await ctx.send('Pug Reset. {}'.format(self.pugInfo.format_pug_short))
        else:
            await ctx.send('Reset failed. Please, try again or inform an admin.')

    @commands.command()
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    @commands.check(isPugInProgress_Warn)
    async def resetcaptains(self, ctx):
        """Resets back to captain mode. Any players or maps picked will be reset."""
        if self.pugInfo.numCaptains < 1:
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

    @commands.command(aliases=['l'])
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    @commands.check(isPugInProgress_Warn)
    async def leave(self, ctx):
        """Leaves the pug"""
        player = ctx.message.author
        if self.pugInfo.removePlayerFromPug(player):
            await ctx.send('{0} left.'.format(display_name(player)))
            await self.processPugStatus(ctx)

    @commands.command()
    @commands.guild_only()
    @commands.check(isActiveChannel_Check)
    @commands.check(isPugInProgress_Ignore)
    async def captain(self, ctx):
        """Volunteer to be a captain in the pug"""
        if not self.pugInfo.playersReady or self.pugInfo.captainsReady or self.pugInfo.gameServer.matchInProgress:
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

    @commands.command()
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
            await ctx.send('Map already picked. Please, pick a different map.')
        
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

def setup(bot):
    bot.add_cog(PUG(bot, DEFAULT_CONFIG_FILE))