import asyncio
from discord.ext import commands
import discord
from cogs import admin

VERSION = '1.0.0.0'
URL = 'www.utassault.net'
UTASSAULT = 250997389308067841

class Info(commands.Cog):
    """Information about the bot"""
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def info(self, ctx):
        result = ['**__About Me:__**']
        result.append('- Version: {}'.format(VERSION))
        result.append('- Author: uZi')
        result.append('- GitHub: <https://github.com/rosskynch/UTAPugBot>')
        result.append('- Library: discord.py')        
        await ctx.send('\n'.join(result))

    @commands.command()
    async def website(self, ctx):
        await ctx.send(URL)

    @commands.command()
    @commands.guild_only()
    async def invite(self, ctx):
        """Returns an active instant invite for a Server

        Bot must have proper permissions to get this information
        """
        # Note that the command 'invite' checks if it came from a particular server
        if ctx.message.guild.id == UTASSAULT:
            # Stuff for UTAssault discord server
            # Perma-invite I created.
            await ctx.send('https://discord.gg/H7FDYqM')
        else:
            try:
                invites = await ctx.message.guild.invites()
            except discord.Forbidden:
                await ctx.send('I do not have the proper permissions')
            except discord.HTTPException:
                await ctx.send('Invite failed')
            else:
                if invites:
                    await ctx.send(invites[0])
                else:
                    await ctx.send('No invites available')

    @commands.command()
    @commands.check(commands.check(admin.hasManagerRole_Check))
    async def checkpermissions(self, ctx):
        """Checks user permissions are correct to use elevated commands"""
        await ctx.send('You have permissions.')

    @commands.command()
    @commands.guild_only()
    async def downloads(self, ctx):
        """Shows useful downloads"""
        str = ["Useful Downloads:"]
        str.append("Note:")
        str.append("To PUG you'll need a UT install with LeagueAS140 and the UTA Mappack. To run the game smoothly above 90 FPS you'll need to use the new 469 patch (currently in beta).")
        str.append("To run smoothly, it's recommended you use the D3D9 Renderer.")
        str.append("")
        str.append("**__Unreal Tournament 99__**")
        # Removed because smant is being a bitch.
        #str.append("**UT clean install**(*with patch, optional updated renderers, LeagueAS140, UTAMapPack, XConsole*): <https://mega.nz/file/YJwXVKoD#bmxaFkJXnbdkPNPMA6VfAqNAjO4qyrpNAK-X0CKHjz4> (Setup Required use README)")
        str.append("**MLUT clean install**: <http://www.prounreal.org/UTMLUT-edition3d.rar>")
        str.append("**UT1337 install**(*Includes UTBonusPacks, SpecFix, Demo Manager 3.4, XConsole, XBrowser and crosshairs*): <https://mega.nz/#!tigC1JhJ!EHbt26RWd7eX6v81-S0zVPuKLaREaAyY75OHawtunqs>")
        str.append("")
        str.append("**__Useful Extras__**")
        str.append("**LeagueAS140** available here: <https://www.utassault.net/leagueas/?downloads>")
        #str.append("**UTA Map Pack**: <https://mega.nz/file/9VZBUCbD#tFXTamvQ5gy-40cOatrJ275ZZ5UqArdf3oCg4nytOqk>")
        str.append("**UTA Map Pack**: <http://medor.no-ip.org/index.php?dir=GameTypes/Assault/&file=UTA-MapPack-52.exe>")        
        str.append("**AssaultBonusPak.u**(*required for playing some maps, included in UTA Map Pack*): <https://mega.nz/file/NZo3jCQR#Y9m5VapDPQiEkqyxT2E15NSgMvF0Ltwx3tbaZ8HV0zg>")
        str.append("**XConsole**: <http://www.unrealize.co.uk/cgi-bin/downloader/dl.pl?id=xconsole.zip>")
        str.append("**D3D9 Renderer** (*main site is: <https://www.cwdohnal.com/utglr>*): <https://www.cwdohnal.com/utglr/utd3d9r13.zip>")
        str.append("**UT469 Patch**(*Make a copy of your UT folder before applying*): <https://github.com/OldUnreal/UnrealTournamentPatches/releases/tag/v469a>")
        await ctx.send('\n'.join(str))

    @commands.command()
    @commands.guild_only()
    async def stats(self, ctx):
        """Get a link to the pug stats page"""
        await ctx.send("UTAPUG stats: <https://www.utassault.net/pugstats>")

    @commands.command()
    @commands.guild_only()
    async def hammerbind(self, ctx):
        """Shows a hammerjump bind"""
        await ctx.send("Aliases[XX]=(Command=\"getweapon ImpactHammer | Button bFire | Fire | OnRelease Jump\",Alias=hjump)")

    @commands.command(aliases = ['bt'])
    @commands.guild_only()
    async def bunnytrack(self, ctx):
        """Shows UTA BunnyTrack server info"""
        await ctx.send("UTA BunnyTrack server: **unreal://www.utapug.net:9100**")

    @commands.command(aliases = ['ra'])
    @commands.guild_only()
    async def rocketarena(self, ctx):
        """Shows UTA RocketArena server info"""
        await ctx.send("UTA RocketArena server: **unreal://www.utapug.net:9600**")

def setup(bot):
    bot.add_cog(Info(bot))
