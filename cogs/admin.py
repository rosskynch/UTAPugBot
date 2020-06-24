import discord
from discord.ext import commands, tasks


#########################################################################################
# Admin cog class.
#########################################################################################
class Admin(commands.Cog):
    """Admin-only commands that make the bot dynamic."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(hidden=True, invoke_without_command=True)
    @commands.is_owner()
    async def shutdown(self, ctx):
        print("Shutting down.")
        await ctx.send("Shutting down.")
        await ctx.bot.logout()

    @commands.command(hidden=True, invoke_without_command=True)
    @commands.is_owner()
    async def load(self, ctx, *, module):
        """Loads a module."""
        try:
            self.bot.load_extension(module)
        except commands.ExtensionError as e:
            await ctx.send(f'{e.__class__.__name__}: {e}')
        else:
            await ctx.send('\N{OK HAND SIGN}')

    @commands.command(hidden=True, invoke_without_command=True)
    @commands.is_owner()
    async def unload(self, ctx, *, module):
        """Unloads a module."""
        try:
            self.bot.unload_extension(module)
        except commands.ExtensionError as e:
            await ctx.send(f'{e.__class__.__name__}: {e}')
        else:
            await ctx.send('\N{OK HAND SIGN}')

    @commands.group(name='reload', hidden=True, invoke_without_command=True)
    @commands.is_owner()
    async def _reload(self, ctx, *, module):
        """Reloads a module."""
        try:
            self.bot.reload_extension(module)
        except commands.ExtensionError as e:
            await ctx.send(f'{e.__class__.__name__}: {e}')
        else:
            await ctx.send('\N{OK HAND SIGN}')

def setup(bot):
    bot.add_cog(Admin(bot))