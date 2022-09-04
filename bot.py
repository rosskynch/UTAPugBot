from discord.ext import commands
import discord
import json
import os
import logging
import sys
from datetime import datetime
import traceback

# Intents required to work with the discord API (updated October 2020)
intents = intents = discord.Intents().all()

description = 'Discord Assault PUG Bot'

extensions = ['cogs.admin', 'cogs.info', 'cogs.pug']

#########################################################################################
# Logging
#########################################################################################
def setupLogging(name):
    formatter = logging.Formatter(fmt='%(asctime)s %(levelname)-8s %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
    logfilename = 'log//{0}-{1}.log'.format(name,datetime.now().strftime("%Y-%m-%d"))
    os.makedirs(os.path.dirname(logfilename), exist_ok=True)
    handler = logging.FileHandler(filename=logfilename, encoding='utf-8', mode='w')
    handler.setFormatter(formatter)
    handler.setLevel(logging.DEBUG)

    screen_handler = logging.StreamHandler(stream=sys.stdout)
    screen_handler.setFormatter(formatter)
    screen_handler.setLevel(logging.INFO)
    logger = logging.getLogger(name)
    logger.addHandler(handler)
    logger.addHandler(screen_handler)
    return logger

log = setupLogging('bot')

#########################################################################################
# Bot 
#########################################################################################

help_attrs = dict(hidden=True)
bot = commands.Bot(
        command_prefix=['!','.'],
        description=description,
        pm_help=None,
        help_attrs=help_attrs,
        intents=intents)

@bot.event
async def on_ready():
    log.info('Logged in as: Username- {0} ; ID- {1}'.format(bot.user.name,str(bot.user.id)))
    
    # Load extensions after bot is logged to ensure commands which require an active connection work.
    for extension in extensions:
        try:
            await bot.load_extension(extension)
        except Exception as e:
            log.error('Failed to load extension {}\n{}: {}'.format(
                extension, type(e).__name__, e))

@bot.event
async def on_resumed():
    log.debug('Resumed...')

@bot.event
async def on_command(context):
    message = context.message
    destination = None
    if isinstance(message.channel, discord.abc.PrivateChannel):
        destination = 'Private Message'
    else:
        destination = '#{0.channel.name} ({0.guild.name})'.format(message)

    log.info('{0.created_at}: {0.author.name} in {1}: {0.content}'.format(
        message, destination))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.NoPrivateMessage):
        await ctx.send('This command cannot be used in private messages.')
    elif isinstance(error, commands.DisabledCommand):
        await ctx.send('This command is disabled and cannot be used.')
    elif isinstance(error, commands.CommandInvokeError):
        log.error('In {0.command.qualified_name}:'.format(ctx))
        traceback.print_tb(error.original.__traceback__)
        log.error('{0.__class__.__name__}: {0}'.format(error.original))

@bot.event
async def on_message(message):
    if not message.author.bot:
        await bot.process_commands(message)

@bot.event
async def on_message_edit(_, message):
    if not message.author.bot:
        await bot.process_commands(message)

def load_credentials():
    with open('credentials.json') as f:
        return json.load(f)

if __name__ == '__main__':
    if any('debug' in arg.lower() for arg in sys.argv):
        bot.command_prefix = '$'    

    credentials = load_credentials()

    bot.run(credentials['token'])
    handlers = log.handlers[:]
    for hdlr in handlers:
        hdlr.close()
        log.removeHandler(hdlr)
