import json
import discord
from discord.ext import commands, tasks
import os
import git

DEFAULT_CONFIG_FILE = 'servers/config.json'
DEFAULT_MANAGER_ROLE = 'PugBotManager'

#########################################################################################
# Utilities.
#########################################################################################
def hasManagerRole_Check(ctx): return ctx.bot.get_cog('Admin').hasManagerRole(ctx)

#########################################################################################
# Admin cog class.
#########################################################################################
class Admin(commands.Cog):
    """Admin-only commands that make the bot dynamic."""

    def __init__(self, bot, configFile=DEFAULT_CONFIG_FILE):
        self.bot = bot
        self.managerRole = DEFAULT_MANAGER_ROLE
        self.configFile = configFile

        self.loadConfig(self.configFile)

#########################################################################################
# Utilities.
#########################################################################################
    def loadConfig(self, configFile):
        with open(configFile) as f:
            info = json.load(f)
            if info:
                if 'admin' in info and 'managerrole' in info['admin']:
                    self.managerRole = info['admin']['managerrole'] # role should be stored as the name.
                    print("Loaded manager role: {0}".format(self.managerRole))
                else:
                    print("No manager role found in config file.")
            else:
                print("Admin: Config file could not be loaded: {0}".format(configFile))
            f.close()
        return True

    # Update config (currently only maplist is being saved)
    def saveConfig(self, configFile):
        with open(configFile) as f:
            info = json.load(f)
            if 'admin' not in info:
                info['admin'] = {}
            info['admin']['managerrole'] = self.managerRole
            f.close()
        with open(configFile,'w') as f:
            json.dump(info, f, indent=4)
            f.close()
        return True

    def hasManagerRole(self, ctx):
        # Always allow if the author is a server admin:
        if ctx.message.author.guild_permissions.administrator:
            return True
        # Otherwise check roles:
        # Uses the name of the role to find it. An alternative is to use the whole role or id,
        # but this makes setting it manually in the config file a bit more of a pain.
        # Note also handle mention so if the role is set by mentioning the role, rather than
        # just by name, it will still work.        
        for i in ctx.author.roles:
            if self.managerRole == i.name or self.managerRole == i.mention:
                return True
        return False

#########################################################################################
# Commands
#########################################################################################
    @commands.command(hidden=True, invoke_without_command=True)
    @commands.is_owner()
    async def setmanagerrole(self, ctx, role):
        """Sets the role which the bot will accept admin commands from"""
        if discord.utils.get(ctx.guild.roles, name=role) or discord.utils.get(ctx.guild.roles, mention=role):
            await ctx.send("Previous role was: **{0}**. New role is: **{1}**.".format(self.managerRole, role))
            self.managerRole = role
            self.saveConfig(self.configFile)
        else:
            await ctx.send("**{0}** role is not available or not formatted properly. Role is still set to **{1}**".format(role, self.managerRole))

    @commands.command(hidden=True, invoke_without_command=True)
    @commands.is_owner()
    async def getmanagerrole(self, ctx):
        """Gets the current role which the bot will accept admin commands from"""
        await ctx.send("Current manager role is set to: **{0}**".format(self.managerRole))

    @commands.command(hidden=True, invoke_without_command=True)
    @commands.is_owner()
    async def shutdown(self, ctx):
        ctx.bot.get_cog('PUG').savePugConfig(ctx.bot.get_cog('PUG').configFile)
        print("Shutting down.")
        await ctx.send("Shutting down.")
        await ctx.bot.close()

    @commands.command(hidden=True, invoke_without_command=True)
    @commands.is_owner()
    async def load(self, ctx, *, module):
        """Loads a module."""
        try:
            await self.bot.load_extension(module)
        except commands.ExtensionError as e:
            await ctx.send(f'{e.__class__.__name__}: {e}')
        else:
            await ctx.send('\N{OK HAND SIGN}')

    @commands.command(hidden=True, invoke_without_command=True)
    @commands.is_owner()
    async def unload(self, ctx, *, module):
        """Unloads a module."""
        try:
            await self.bot.unload_extension(module)
        except commands.ExtensionError as e:
            await ctx.send(f'{e.__class__.__name__}: {e}')
        else:
            await ctx.send('\N{OK HAND SIGN}')

    @commands.group(name='reload', hidden=True, invoke_without_command=True)
    @commands.is_owner()
    async def _reload(self, ctx, *, module):
        """Reloads a module."""
        try:
            if str.lower(module) == 'cogs.pug':
                # Save the config before reloading.
                ctx.bot.get_cog('PUG').savePugConfig(ctx.bot.get_cog('PUG').configFile)
            await self.bot.reload_extension(module)
        except commands.ExtensionError as e:
            await ctx.send(f'{e.__class__.__name__}: {e}')
        else:
            await ctx.send('\N{OK HAND SIGN}')

    @commands.group(hidden=True, invoke_without_command=True)
    @commands.is_owner()
    async def gitpull(self, ctx):
        """Pulls from the repo, if possible."""
        print("Attempting pull from repo")
        try:
            g = git.cmd.Git()
            msg = g.pull()
            await ctx.send(msg)
        except git.exc.GitError as e:
            await ctx.send('Error, check your private messages.')
            try:
                await ctx.message.author.send('Failed: {}'.format(e))
            except:
                await ctx.send('Failed to send PM, are your PMs enabled for this server?')

async def setup(bot):
    await bot.add_cog(Admin(bot, DEFAULT_CONFIG_FILE))