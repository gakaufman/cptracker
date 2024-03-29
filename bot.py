# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.

import os
import random
import difflib
import traceback
import datetime
import pytz
import discord
from discord.ext import tasks, commands
from pymongo import MongoClient
import config

# TODO: Group commands into cogs
# TODO: Find word count update on delete workaround for Tupperbot
# TODO: Update user search function

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)
cluster = MongoClient('mongodb+srv://bachang:{0}@cluster0.pry4u.mongodb.net/test'.format(os.environ['password']))
databases = {dbname: cluster[dbname] for dbname in config.DB_GUILD_CHANNEL_MAPPING.keys()}
cpdatas = {dbname: database['cpdata'] for (dbname, database) in databases.items()}
attendances = {dbname: database['attendance'] for (dbname, database) in databases.items()}
daily_word_counts = {dbname: database['daily_word_count'] for (dbname, database) in databases.items()}
# timezone = database['timezone']


class WordCountCPUpdater(commands.Cog):
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.max_daily_cp = 5
        self.word_count_per_cp = 75
        self.date = datetime.datetime.now(pytz.timezone(config.TIMEZONE)).date()
        self.month = self.date.month
        self.update_word_count_cp.start()
        self.reset_attendance_count.start()

    @tasks.loop(minutes=1.0)
    async def update_word_count_cp(self):
        # Don't run any commands if the bot is not logged in yet
        if not self.bot.is_ready():
            return
        date_now = datetime.datetime.now(pytz.timezone(config.TIMEZONE)).date()
        if self.date < date_now:
            datestr = self.date.strftime('%d/%m/%Y')
            for dbname in config.DB_GUILD_CHANNEL_MAPPING.keys():
                notification_list = []
                guild = config.DB_GUILD_CHANNEL_MAPPING[dbname]['guild']
                cp_tracker_channel = config.DB_GUILD_CHANNEL_MAPPING[dbname]['cp_tracker_channel']
                channel = discord.utils.get(bot.get_all_channels(), guild__name=guild, name=cp_tracker_channel)
                await channel.send('__CP earned for roleplaying on {0}:__'.format(datestr))
                for post in daily_word_counts[dbname].find():
                    userid = post['_id']

                    # Check to see if user is still part of the server. Otherwise, delete user and continue
                    guild = channel.guild
                    if guild.get_member(userid) is None:
                        _delete_user(daily_word_counts[dbname], userid)
                        _delete_user(cpdatas[dbname], userid)
                        continue

                    # Check to see if user exists. Otherwise, delete user and continue
                    try:
                        user = await bot.fetch_user(userid)
                    except discord.errors.NotFound:
                        _delete_user(daily_word_counts[dbname], userid)
                        _delete_user(cpdatas[dbname], userid)
                    else:
                        word_count = post['word_count']
                        cp_gained = word_cp if ((word_cp := word_count // self.word_count_per_cp) <= self.max_daily_cp) else self.max_daily_cp

                        # Update CP
                        remaining_cp = _update_cp(cpdatas[dbname], userid, cp_gained)

                        # Reset word count
                        daily_word_counts[dbname].update_one({'_id': userid}, {'$set': {'word_count': 0}})

                        # Add member notification message to list
                        notification = '{0} earned {1} CP for writing {2} words. Remaining CP: {3}'.format(user.name, cp_gained, word_count, remaining_cp)
                        notification_list.append((word_count, notification))
                # Notify members
                notification_list.sort(key=lambda tup: tup[0], reverse=True)
                notification_list = [notification for word_count, notification in notification_list]
                # Splits the list into a list of sublists of size 20
                notification_lists = [notification_list[i:i + 20] for i in range(0, len(notification_list), 20)]
                for l in notification_lists:
                    await channel.send('\n'.join(l))
            self.date = date_now

    @tasks.loop(hours=1.0)
    async def reset_attendance_count(self):
        # Don't run any commands if the bot is not logged in yet
        if not self.bot.is_ready():
            return
        date_now = datetime.datetime.now(pytz.timezone(config.TIMEZONE)).date()
        if date_now.month % 3 == 1 and (self.month < date_now.month or (self.month == 12 and date_now.month == 1)):
            for dbname in config.DB_GUILD_CHANNEL_MAPPING.keys():
                guild = config.DB_GUILD_CHANNEL_MAPPING[dbname]['guild']
                bot_channel = config.DB_GUILD_CHANNEL_MAPPING[dbname]['bot-channel']
                channel = discord.utils.get(bot.get_all_channels(), guild__name=guild, name=bot_channel)
                for post in attendances[dbname].find():
                    userid = post['_id']

                    # Check to see if user is still part of the server. Otherwise, delete user and continue
                    guild = channel.guild
                    if guild.get_member(userid) is None:
                        _delete_user(attendances[dbname], userid)
                        continue

                    # Check to see if user exists. Otherwise, delete user and continue
                    try:
                        user = await bot.fetch_user(userid)
                    except discord.errors.NotFound:
                        _delete_user(attendances[dbname], userid)
                    else:
                        # Reset attendance count
                        attendances[dbname].update_one({'_id': userid}, {'$set': {'attendance_count': 0}})
                await channel.send('Attendance counts have been reset!')
            self.month = date_now.month


def _update_cp(db, user_id, val):
    if db.find_one({'_id': user_id}):
        db.update_one({'_id': user_id}, {'$inc': {'cp': val}})
    else:
        post = {'_id': user_id, 'cp': val}
        db.insert_one(post)
    return db.find_one({'_id': user_id})['cp']


def _update_attendance(db, user_id, val):
    if db.find_one({'_id': user_id}):
        db.update_one({'_id': user_id}, {'$inc': {'attendance_count': val}})
    else:
        post = {'_id': user_id, 'attendance_count': val}
        db.insert_one(post)
    return db.find_one({'_id': user_id})['attendance_count']


def _delete_user(db, user_id):
    db.delete_one({'_id': user_id})


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


async def alastor_easter(message):
    if message.author.id == 266758722045345811: # Ronnie's ID
        if message.guild.name == 'Last Hope Campaign!':
            if 'disintegrate' in message.content.lower():
                rand = random.randint(1, 2)
                if rand == 2:
                    damage = sum([random.randint(1, 6) for i in range(10)]) + 40
                    await message.channel.send("{0} used Disintegrate! It dealt {1} force damage!".format(message.author.mention, damage))


async def lewis_easter(message):
    if message.author.id == 475349160892301322: # Lewis' ID
        if 'love' in message.content.lower():
            rand = random.randint(1, 3)
            if rand == 3:
                await message.channel.send("Everybody, have your daily dose of Lew's Love! Courtesy of {0}.".format(message.author.mention))


def is_in_valid_channel(message):
    dbname = config.GUILD_DB_MAPPING[message.channel.guild.name]
    valid_channel_category_ids = config.DB_GUILD_CHANNEL_MAPPING[dbname]['valid_channel_category_ids']
    valid_channel_ids = config.DB_GUILD_CHANNEL_MAPPING[dbname]['valid_channel_ids']
    return message.channel.category_id in valid_channel_category_ids or message.channel.id in valid_channel_ids


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


@bot.before_invoke
async def check_is_in_valid_server(context):
    # Check if the bot is configured to be run on the server before running any commands
    try:
        config.GUILD_DB_MAPPING[context.guild.name]
    except KeyError:
        await context.send('ERROR: This bot is not configured to be run on this server. Please contact tech support for help.')


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
    # Only run easter eggs in non-RP channels
    if not is_in_valid_channel(message):
        await alastor_easter(message)
    # Only update word count if message was sent in a valid channel
    try:
        if is_in_valid_channel(message):
            dbname = config.GUILD_DB_MAPPING[message.channel.guild.name]
            userid = message.author.id
            num_words = len(str(message.content).split())
            await update_word_count(dbname, userid, num_words)
    except KeyError:
        # Print exception traceback to stderr but continue execution
        traceback.print_exc()
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
    dbname = config.GUILD_DB_MAPPING[context.guild.name]
    word_count = res['word_count'] if (res := daily_word_counts[dbname].find_one({'_id': context.author.id})) else 0
    await context.send('{0}, so far you have typed {1} words today.'.format(context.author.mention, word_count))


@bot.command(name='checkcp', aliases=['checkCP'])
async def checkcp(context):
    dbname = config.GUILD_DB_MAPPING[context.guild.name]
    cp = res['cp'] if (res := cpdatas[dbname].find_one({'_id': context.author.id})) else 0
    await context.send('{0}, you currently have {1} CP.'.format(context.author.mention, cp))


@bot.command(name='checkattendance', aliases=['checkattend'])
async def checkattendance(context):
    dbname = config.GUILD_DB_MAPPING[context.guild.name]
    attendance_count = res['attendance_count'] if (res := attendances[dbname].find_one({'_id': context.author.id})) else 0
    await context.send('{0}, your attendance count is currently at {1}.'.format(context.author.mention, attendance_count))


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


@updatecp.error
async def update_error(context, error):
    if isinstance(error, discord.ext.commands.errors.MissingRequiredArgument):
        await context.send('ERROR: The update function requires the CP value argument. For example: `!updatecp 5 "Completing A Mission"`')
    else:
        traceback.print_exc()


def get_nearest_user(context, usernames):
    all_names = {}
    nearest_users = []
    invalid_usernames = []
    for member in context.guild.members:
        if not member.bot:
            if member.nick:
                all_names[member.nick] = member
            else:
                all_names[member.name] = member
    usernames = usernames.split(',')
    for username in usernames:
        nearest_username = difflib.get_close_matches(username, all_names.keys(), 1, 0.4)
        if nearest_username:
            nearest_users.append(all_names[nearest_username[0]])
        else:
            invalid_usernames.append(username)
    return nearest_users, invalid_usernames


@bot.command(name='givecp', aliases=['giveCP'])
@commands.has_any_role(*config.COMMAND_PERMISSION_ROLES)
async def givecp(context, username, val, reason='Manual Adjustment'):
    dbname = config.GUILD_DB_MAPPING[context.guild.name]
    nearest_users, invalid_usernames = get_nearest_user(context, username)
    if invalid_usernames:
        await context.send("Can't find a valid user matching the following inputs: {0}".format(','.join(invalid_usernames)))
    for user in nearest_users:
        user_id = user.id
        _update_cp(cpdatas[dbname], user_id, int(val))
        remaining_cp = cpdatas[dbname].find_one({'_id': user_id})['cp']
        messages = [
            '{0} parcels out {1} CP to {2} for {3}',
            '{0} forks over {1} CP to {2} for {3}',
            '{0} dishes out {1} CP to {2} for {3}',
            '{0} presents {1} CP to {2} for {3}',
            '{0} administers {1} CP to {2} for {3}',
            '{0} tips {1} CP to {2} for {3}',
            '{0} bequeaths {1} CP to {2} for {3}',
            '{0}...you know..."gives"  ( ͡° ͜ʖ ͡°) {1} CP to {2} for {3}',
        ]
        rand = random.randint(1, 8)
        message = messages[rand-1] + '\n**CP Remaining**: {4}'
        await context.send(message.format(context.author.mention, val, user.mention, reason, remaining_cp))


@givecp.error
async def givecp_error(context, error):
    if isinstance(error, discord.ext.commands.errors.MissingRequiredArgument):
        await context.send('ERROR: The givecp function requires at least 2 arguments, CP value and username. For example: `!givecp "DM Creo" 5 "Being an awesome DM"`')
    elif isinstance(error, discord.ext.commands.errors.MissingAnyRole):
        await context.send('You do not have permission to run this command.')
    else:
        traceback.print_exc()


@bot.command(name='attendance', aliases=['attend'])
@commands.has_any_role(*config.COMMAND_PERMISSION_ROLES)
async def attendance(context, username, val=1.0):
    dbname = config.GUILD_DB_MAPPING[context.guild.name]
    nearest_users, invalid_usernames = get_nearest_user(context, username)
    user = nearest_users[0]
    if invalid_usernames:
        await context.send("Can't find a valid user matching the following inputs: {0}".format(','.join(invalid_usernames)))
    user_id = user.id
    _update_attendance(attendances[dbname], user_id, val)
    remaining_attendance = attendances[dbname].find_one({'_id': user_id})['attendance_count']
    message = '{0} attended a session! Their attendance count is now at {1}.'
    await context.send(message.format(user.mention, remaining_attendance))


@attendance.error
async def attendance_error(context, error):
    if isinstance(error, discord.ext.commands.errors.MissingAnyRole):
        await context.send('You do not have permission to run this command.')
    else:
        traceback.print_exc()


@bot.command(name='attendancelist', aliases=['attendlist'])
@commands.has_any_role(*config.COMMAND_PERMISSION_ROLES)
async def attendancelist(context):
    dbname = config.GUILD_DB_MAPPING[context.guild.name]

    attendance_list = []
    guild = config.DB_GUILD_CHANNEL_MAPPING[dbname]['guild']
    bot_channel = config.DB_GUILD_CHANNEL_MAPPING[dbname]['bot-channel']
    channel = discord.utils.get(bot.get_all_channels(), guild__name=guild, name=bot_channel)
    for post in attendances[dbname].find():
        userid = post['_id']

        # Check to see if user exists. Otherwise, delete user and continue
        try:
            user = await bot.fetch_user(userid)
        except discord.errors.NotFound:
            _delete_user(attendances[dbname], userid)
        else:
            attendance_count = post['attendance_count']

            # Add member notification message to list
            attendance_message = '{0}: {1}'.format(user.name, attendance_count)
            attendance_list.append((attendance_count, attendance_message))
    # Notify members
    await channel.send('__Attendance Count List__')
    attendance_list.sort(key=lambda tup: tup[0])
    attendance_list = [attendance_message for attendance_count, attendance_message in attendance_list]
    attendance_lists = [attendance_list[i:i + 20] for i in range(0, len(attendance_list), 20)] # Splits the list into a list of sublists of size 20
    for l in attendance_lists:
        await channel.send('\n'.join(l))


@attendancelist.error
async def attendancelist_error(context, error):
    if isinstance(error, discord.ext.commands.errors.MissingAnyRole):
        await context.send('You do not have permission to run this command.')
    else:
        traceback.print_exc()


def dtresults(dt, result, skill_total):
    if skill_total < 10 and dt in config.SW5E_FAILURE_DOWNTIME.keys():
        return config.SW5E_FAILURE_DOWNTIME[dt]
    result_string = config.SW5E_DOWNTIME[dt]
    if result <= 40:
        result_string = result_string['40-']
    elif 41 <= result <= 70:
        result_string = result_string['41-70']
    elif 71 <= result <= 100:
        result_string = result_string['71-100']
    elif 101 <= result <= 110:
        result_string = result_string['101-110']
    else:
        result_string = result_string['111+']
    return result_string


@bot.command(name='dtroll')
async def dtroll(context, dt, skill, adv=None):
    skill = int(skill)
    skillstr = 'Skill ({skill})'.format(skill=abs(skill))
    d100 = random.randrange(1, 101)
    result_check = '1d100 ({d100})'.format(d100=d100)
    if int(skill) >= 0:
        message = """
            {author}\n
            **Resolution**: Rolling {{skill_check}} + {skill} = {{skill_total}} : Modifier = {{mod}}\n
            **Result**: Rolling {result_check} + {{modstr}} = {{result}}\n
            {{result_string}}
        """.format(author=context.author.mention, skill=skillstr, result_check=result_check)
    else:
        message = """
            {author}\n
            **Resolution**: Rolling {{skill_check}} - {skill} = {{skill_total}} : Modifier = {{mod}}\n
            **Result**: Rolling {result_check} + {{modstr}} = {{result}}\n
            {{result_string}}
        """.format(author=context.author.mention, skill=skillstr, result_check=result_check)
    r1 = random.randrange(1, 21)
    r2 = random.randrange(1, 21)
    if adv != 'adv' and adv != 'dis':
        d20 = r1
        skill_check = '1d20 ({d20})'.format(d20=d20)
    else:
        if adv == 'adv':
            d20 = max(r1, r2)
            skill_check = '2d20kh1 ({r1}, {r2})'
        else:
            d20 = min(r1, r2)
            skill_check = '2d20kl1 ({r1}, {r2})'
        if d20 == r1:
            r2 = '~~' + str(r2) + '~~'
        else:
            r1 = '~~' + str(r1) + '~~'
        skill_check = skill_check.format(r1=r1, r2=r2)
    skill_total = d20 + skill
    mod = min(max(((skill_total // 5) - 1) * 5, 0), 25)
    modstr = 'Modifier ({mod})'.format(mod=mod)
    result = d100 + mod
    result_string = dtresults(dt, result, skill_total)
    message = message.format(skill_check=skill_check, skill_total=skill_total, mod=mod, modstr=modstr, result=result, result_string=result_string)
    await context.send(message)


@dtroll.error
async def dtroll_error(context, error):
    if isinstance(error, discord.ext.commands.errors.MissingRequiredArgument):
        await context.send('ERROR: The dtroll function requires at least 2 arguments, downtime activity and roll modifier.')
    else:
        traceback.print_exc()


@bot.command(name='checkmyass')
async def checkmyass(context):
    rand = random.randint(1,13)
    num_responses = 4
    if rand == 13:
        message = '{0}, you thinn like a washboard. Does it hurt when you sit?'
    else:
        if rand % num_responses == 0:
            message = 'Damn {0}, you ***乇乂丅尺卂 丅卄工匚匚***'
        elif rand % num_responses == 1:
            message = 'Damn {0}, you ***ᗪㄩ爪爪ㄚ ㄒ卄丨匚匚***'
        elif rand % num_responses == 2:
            message = 'Damn {0}, you got a damn fine dumptruck!'
        else:
            message = 'Damn shawty, you got a shelf!'
    await context.send(message.format(context.author.mention))


@bot.command(name='checkmyschlong')
async def checkmyschlong(context):
    rand = random.randint(1,13)
    num_responses = 5
    if rand == 13:
        message = "You sure you have one {0}? I can't find it :face_with_monocle:"
    else:
        if rand % num_responses == 0:
            message = "Damn {0}, you're a tripod!"
        elif rand % num_responses == 1:
            message = 'Damn {0}, your schlong can fill a Sarlacc pit!'
        elif rand % num_responses == 2:
            message = 'Damn {0}, you got a huge ass schlong-a-long-a-ding-dong!'
        elif rand % num_responses == 3:
            message = 'Damn {0}, you got a third leg!'
        else:
            message = 'Damn {0}, you gotta put that monster away at the dinner table!'
    await context.send(message.format(context.author.mention))


@bot.command(name='destroyamotherfucker')
async def destroyamotherfucker(context):
    if context.message.author.id == 266758722045345811:  # Ronnie's ID
        await context.send('{0} just ***DESTROYED*** <@!305338506253959168>, setting his CP to -1000 permanently!'.format(context.author.mention))
    else:
        await context.send('Sorry, but you do not have the power to destroy a motherfucker.')


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
