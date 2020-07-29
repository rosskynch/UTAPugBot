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
        str.append("**__Unreal Tournament 99__**")
        str.append("**UT clean install**(*with patch, optional updated renderers, LeagueAS140, UTAMapPack, XConsole*): <https://mega.nz/file/YJwXVKoD#bmxaFkJXnbdkPNPMA6VfAqNAjO4qyrpNAK-X0CKHjz4> (Setup Required use README)")
        str.append("**MLUT clean install**: <http://www.prounreal.org/UTMLUT-edition3d.rar>")
        str.append("**UT1337 install**(*Includes UTBonusPacks, SpecFix, Demo Manager 3.4, XConsole, XBrowser and crosshairs*): <http://www.prounreal.org/UTMLUT-edition3d.rar>")
        str.append("")
        str.append("**__Useful Extras__**")
        str.append("**UTA Map Pack**: <https://mega.nz/file/9VZBUCbD#tFXTamvQ5gy-40cOatrJ275ZZ5UqArdf3oCg4nytOqk>")
        str.append("**AssaultBonusPak.u**(*required for playing some maps, included in UTA Map Pack*): <https://mega.nz/file/NZo3jCQR#Y9m5VapDPQiEkqyxT2E15NSgMvF0Ltwx3tbaZ8HV0zg>")
        str.append("**XConsole**: <http://www.unrealize.co.uk/cgi-bin/downloader/dl.pl?id=xconsole.zip>")
        await ctx.send('\n'.join(str))

def setup(bot):
    bot.add_cog(Info(bot))
