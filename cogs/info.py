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
        result.append('- GitHub: https://github.com/rosskynch/UTAPugBot')
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

def setup(bot):
    bot.add_cog(Info(bot))
