# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.

import os
import datetime
import pytz
import discord
from discord.ext import tasks, commands
from pymongo import MongoClient
import config

# TODO: Add error handling for when the !updatecp command is called with insufficient arguments
# TODO: Group commands into cogs
# TODO: Find word count update on delete workaround for Tupperbot

bot = commands.Bot(command_prefix='!')
cluster = MongoClient('mongodb+srv://bachang:{0}@cluster0.pry4u.mongodb.net/test'.format(os.environ['password']))
databases = {dbname: cluster[dbname] for dbname in config.DB_GUILD_CHANNEL_MAPPING.keys()}
cpdatas = {dbname: database['cpdata'] for (dbname, database) in databases.items()}
daily_word_counts = {dbname: database['daily_word_count'] for (dbname, database) in databases.items()}
# timezone = database['timezone']


class WordCountCPUpdater(commands.Cog):

    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.max_daily_cp = 5
        self.word_count_per_cp = 75
        self.date = datetime.datetime.now(pytz.timezone(config.TIMEZONE)).date()
        self.update_word_count_cp.start()

    @tasks.loop(minutes=1.0)
    async def update_word_count_cp(self):
        # Don't run any commands if the bot is not logged in yet
        if not self.bot.is_ready():
            return
        date_now = datetime.datetime.now(pytz.timezone(config.TIMEZONE)).date()
        if self.date < date_now:
            datestr = self.date.strftime('%d/%m/%Y')
            for dbname in config.DB_GUILD_CHANNEL_MAPPING.keys():
                guild = config.DB_GUILD_CHANNEL_MAPPING[dbname]['guild']
                cp_tracker_channel = config.DB_GUILD_CHANNEL_MAPPING[dbname]['cp_tracker_channel']
                channel = discord.utils.get(bot.get_all_channels(), guild__name=guild, name=cp_tracker_channel)
                await channel.send('__CP earned for roleplaying on {0}:__'.format(datestr))
                for post in daily_word_counts[dbname].find():
                    userid = post['_id']

                    # Check to see if user exists. Otherwise, delete user and continue
                    try:
                        user = await bot.fetch_user(userid)
                    except discord.errors.NotFound:
                        _delete_user(cpdatas[dbname], userid)
                    else:
                        word_count = post['word_count']
                        cp_gained = word_cp if ((word_cp := word_count // self.word_count_per_cp) <= self.max_daily_cp) else self.max_daily_cp

                        # Update CP
                        remaining_cp = _update_cp(cpdatas[dbname], userid, cp_gained)

                        # Reset word count
                        daily_word_counts[dbname].update_one({'_id': userid}, {'$set': {'word_count': 0}})

                        # Notify members
                        await channel.send('{0} earned {1} CP for writing {2} words. Remaining CP: {3}'.format(user.name, cp_gained, word_count, remaining_cp))
            self.date = date_now


def _update_cp(db, user_id, val):
    if db.find_one({'_id': user_id}):
        db.update_one({'_id': user_id}, {'$inc': {'cp': val}})
    else:
        post = {'_id': user_id, 'cp': val}
        db.insert_one(post)
    return db.find_one({'_id': user_id})['cp']


def _delete_user(db, user_id):
    db.delete_one({'_id': user_id})


def _get_word_count(context):
    dbname = config.GUILD_DB_MAPPING[context.guild.name]
    return res['word_count'] if (res := daily_word_counts[dbname].find_one({'_id': context.author.id})) else 0


def _get_cp(context):
    dbname = config.GUILD_DB_MAPPING[context.guild.name]
    return res['cp'] if (res := cpdatas[dbname].find_one({'_id': context.author.id})) else 0


# def get_timezone(context):
#     return res['tz'] if (res := timezone.find_one({'_id': context.author.id})) else None


# def is_valid_timezone(tz):
#     """
#     Check if the timezone string is valid
#     @param tz:
#     @return:
#     """
#     if not tz:
#         return False
#
#     timezones = [x.lower() for x in pytz.all_timezones]
#     return tz.lower() in timezones


def is_in_valid_channel(message):
    dbname = config.GUILD_DB_MAPPING[message.channel.guild.name]
    return message.channel.name in config.DB_GUILD_CHANNEL_MAPPING[dbname]['valid_channels']


def is_within_today(message):
    from_tz = pytz.utc
    to_tz = pytz.timezone(config.TIMEZONE)
    today = datetime.datetime.now(pytz.timezone(config.TIMEZONE)).date()
    message_time = message.created_at
    message_utc_time = from_tz.localize(message_time)
    message_central_time = message_utc_time.astimezone(to_tz)
    message_date = message_central_time.date()
    return today == message_date


async def update_word_count(dbname, userid, num_words):
    if daily_word_counts[dbname].find_one({'_id': userid}):
        daily_word_counts[dbname].update_one({'_id': userid}, {'$inc': {'word_count': num_words}})
    else:
        post = {'_id': userid, 'word_count': num_words}
        daily_word_counts[dbname].insert_one(post)


@bot.event
async def on_ready():
    print('{0} has connected to Discord!'.format(bot.user))


@bot.event
async def on_message(message):
    # Don't run any commands if the bot is not logged in yet
    if not bot.is_ready():
        return
    # Ignore if the message was sent by the bot itself
    if message.author.bot:
        return
    # Check if the bot is configured to be run on the server
    try:
        config.GUILD_DB_MAPPING[message.channel.guild.name]
    except KeyError:
        await message.channel.send('ERROR: This bot is not configured to be run on this server. Please contact tech support for help.')
    else:
        # Only update word count if message was sent in a valid channel
        if is_in_valid_channel(message):
            dbname = config.GUILD_DB_MAPPING[message.channel.guild.name]
            userid = message.author.id
            num_words = len(str(message.content).split())
            await update_word_count(dbname, userid, num_words)
        # Continue processing other commands
        await bot.process_commands(message)


# @bot.event
# async def on_message_delete(message):
#     # Don't run any commands if the bot is not logged in yet
#     if not bot.is_ready():
#         return
#     # Only update word count if message was deleted in a valid channel
#     if is_in_valid_channel(message):
#         # Only update word count if message was deleted within a day
#         if is_within_today(message):
#             dbname = config.GUILD_DB_MAPPING[message.channel.guild.name]
#             userid = message.author.id
#             num_words = -1 * len(str(message.content).split())
#             await update_word_count(dbname, userid, num_words)


@bot.event
async def on_message_edit(before, after):
    # Don't run any commands if the bot is not logged in yet
    if not bot.is_ready():
        return
    # Only update word count if message was edited in a valid channel
    if is_in_valid_channel(before):
        # Only update word count if message was edited within a day
        if is_within_today(before):
            dbname = config.GUILD_DB_MAPPING[before.channel.guild.name]
            userid = before.author.id
            num_words = len(str(after.content).split()) - len(str(before.content).split())
            await update_word_count(dbname, userid, num_words)


@bot.command(name='checkwords', aliases=['checkword'])
async def checkwords(context):
    word_count = _get_word_count(context)
    await context.send('{0}, so far you have typed {1} words today.'.format(context.author.mention, word_count))


@bot.command(name='checkcp', aliases=['checkCP'])
async def checkcp(context):
    cp = _get_cp(context)
    await context.send('{0}, you currently have {1} CP.'.format(context.author.mention, cp))


@bot.command(name='updatecp', aliases=['updateCP'])
async def updatecp(context, val, reason='Manual Adjustment'):
    dbname = config.GUILD_DB_MAPPING[context.guild.name]
    user_id = context.author.id
    _update_cp(cpdatas[dbname], user_id, int(val))
    remaining_cp = cpdatas[dbname].find_one({'_id': user_id})['cp']
    await context.send('''
**User**: {0}
**Reason**: {1}
**CP**: {2}
**CP Remaining**: {3}
    '''.format(context.author.mention, reason, val, remaining_cp))


# @bot.command(name='checktimezone', aliases=['checktz'])
# async def checktimezone(context):
#     tz = get_timezone(context)
#     await context.send('{0}, your timezone is currently set as {1}.'.format(context.author.mention, tz))


# @bot.command(name='settimezone', aliases=['settz'])
# async def settimezone(context, tz):
#     if not is_valid_timezone(tz):
#         await context.send(INVALID_TIMEZONE_MESSAGE)
#         return
#     else:
#         tz_offset = datetime.datetime.now(pytz.timezone(tz)).strftime('%z')
#         if timezone.find_one({'_id': context.author.id}):
#             timezone.update_one({'_id': context.author.id}, {'$set': {'tz': tz_offset}})
#         else:
#             post = {'_id': context.author.id, 'tz': tz}
#             timezone.insert_one(post)
#         await context.send('{0}, your timezone has been successfully updated to {1} ({2}).'.format(context.author.mention, tz, tz_offset))


# Press the green button in the gutter to run the script.
bot.add_cog(WordCountCPUpdater(bot))
bot.run(os.environ['token'])
