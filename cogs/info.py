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
            await ctx.send('https://discord.gg/s8UJcuR')
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
    @commands.check(admin.hasManagerRole_Check)
    async def checkpermissions(self, ctx):
        """Checks user permissions are correct to use elevated commands"""
        await ctx.send('You have permissions.')

    @commands.command()
    @commands.guild_only()
    async def downloads(self, ctx):
        """Shows useful downloads"""
        str = ["Useful Downloads:"]
        str.append("Note:")
        str.append("To PUG you'll need a UT install with LeagueAS140 and UTA Maps. To run the game smoothly above 90 FPS you'll need to use the UT 469 patch (latest release is recommended).")
        str.append("To run smoothly, it's recommended you use the D3D9 or D3D11 Renderer.")
        str.append("")
        str.append("**__Unreal Tournament 99__**")
        str.append("**Pre-setup UT**(*469d from rX of the TDM community*): <https://docs.google.com/document/d/1BOl6Dq4vvS8n6C-FNSLjGfdocCqvWXcgNjiLgFkH-KQ/edit?usp=sharing>")
        str.append("")
        str.append("**__Useful Extras__**")
        str.append("**LeagueAS140** available here: <https://www.utassault.net/leagueas/?downloads>")
        str.append("**UTA Maps**(*download Maps, Textures, Sounds and Music folders and add to your UT install*): <https://github.com/Sizzl/UTA-PugServer/tree/master/ut-server>")
        str.append("**AssaultBonusPak.u**(*required for playing some maps*): <https://github.com/Sizzl/UTA-PugServer/blob/master/ut-server/System/AssaultBonusPack.u>")
        str.append("**UT469 Patches**(*Get the latest and make a copy of your UT folder before applying*): <https://github.com/OldUnreal/UnrealTournamentPatches/releases>")
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

    @commands.command(aliases = ['tdm', 'dm'])
    @commands.guild_only()
    async def deathmatch(self, ctx):
        """Shows UTA TDM server info"""
        await ctx.send("UTA TDM server: **unreal://51.195.40.255:7777**")

    @commands.command(aliases = ['ffa'])
    @commands.guild_only()
    async def freeforall(self, ctx):
        """Shows UTA FFA server info"""
        await ctx.send("UTA FFA server: **unreal://51.195.40.255:7786**")

    @commands.command(aliases = ['ra'])
    @commands.guild_only()
    async def rocketarena(self, ctx):
        """Shows UTA RocketArena server info"""
        await ctx.send("UTA RocketArena server: **unreal://www.utapug.net:9600**")

async def setup(bot):
    await bot.add_cog(Info(bot))
