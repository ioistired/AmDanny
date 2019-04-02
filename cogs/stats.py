from discord.ext import commands
from collections import Counter, defaultdict

from .utils import checks, db
from .utils.paginator import CannotPaginate

import logging
import discord
import datetime
import asyncio
import psutil
import json
import os
import re
import io
import gc

log = logging.getLogger(__name__)

_INVITE_REGEX = re.compile(r'(?:https?:\/\/)?discord(?:\.gg|\.com|app\.com\/invite)?\/[A-Za-z0-9]+')

def censor_invite(obj, *, _regex=_INVITE_REGEX):
    return _regex.sub('[censored-invite]', str(obj))

def hex_value(arg):
    return int(arg, base=16)

def object_at(addr):
    for o in gc.get_objects():
        if id(o) == addr:
            return o
    return None

class Stats(commands.Cog):
    """Bot usage statistics."""

    def __init__(self, bot):
        self.bot = bot
        self.process = psutil.Process()

        # This is a datetime list
        self._resumes = []
        # shard_id: List[datetime]
        self._identifies = defaultdict(list)

    def _clear_gateway_data(self):
        one_week_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)
        to_remove = [index for index, dt in enumerate(self._resumes) if dt < one_week_ago]
        for index in reversed(to_remove):
            del self._resumes[index]

        for shard_id, dates in self._identifies.items():
            to_remove = [index for index, dt in enumerate(dates) if dt < one_week_ago]
            for index in reversed(to_remove):
                del dates[index]

    @commands.command(hidden=True)
    async def socketstats(self, ctx):
        delta = datetime.datetime.utcnow() - self.bot.uptime
        minutes = delta.total_seconds() / 60
        total = sum(self.bot.socket_stats.values())
        cpm = total / minutes
        await ctx.send(f'{total} socket events observed ({cpm:.2f}/minute):\n{self.bot.socket_stats}')

    def get_bot_uptime(self, *, brief=False):
        now = datetime.datetime.utcnow()
        delta = now - self.bot.uptime
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)

        if not brief:
            if days:
                fmt = '{d} days, {h} hours, {m} minutes, and {s} seconds'
            else:
                fmt = '{h} hours, {m} minutes, and {s} seconds'
        else:
            fmt = '{h}h {m}m {s}s'
            if days:
                fmt = '{d}d ' + fmt

        return fmt.format(d=days, h=hours, m=minutes, s=seconds)

    @commands.command()
    async def uptime(self, ctx):
        """Tells you how long the bot has been up for."""
        await ctx.send(f'Uptime: **{self.get_bot_uptime()}**')

    @commands.command()
    async def about(self, ctx):
        """Tells you information about the bot itself."""
        cmd = r'git show -s HEAD~3..HEAD --format="[{}](https://github.com/Rapptz/RoboDanny/commit/%H) %s (%cr)"'
        if os.name == 'posix':
            cmd = cmd.format(r'\`%h\`')
        else:
            cmd = cmd.format(r'`%h`')

        try:
            revision = os.popen(cmd).read().strip()
        except OSError:
            revision = 'Could not fetch due to memory error. Sorry.'

        embed = discord.Embed(description='Latest Changes:\n' + revision)
        embed.title = 'Official Bot Server Invite'
        embed.url = 'https://discord.gg/DWEaqMy'
        embed.colour = discord.Colour.blurple()

        owner = self.bot.get_user(self.bot.owner_id)
        embed.set_author(name=str(owner), icon_url=owner.avatar_url)

        # statistics
        total_members = sum(1 for _ in self.bot.get_all_members())
        total_online = len({m.id for m in self.bot.get_all_members() if m.status is not discord.Status.offline})
        total_unique = len(self.bot.users)

        voice_channels = []
        text_channels = []
        for guild in self.bot.guilds:
            voice_channels.extend(guild.voice_channels)
            text_channels.extend(guild.text_channels)

        text = len(text_channels)
        voice = len(voice_channels)

        embed.add_field(name='Members', value=f'{total_members} total\n{total_unique} unique\n{total_online} unique online')
        embed.add_field(name='Channels', value=f'{text + voice} total\n{text} text\n{voice} voice')

        memory_usage = self.process.memory_full_info().uss / 1024**2
        cpu_usage = self.process.cpu_percent() / psutil.cpu_count()
        embed.add_field(name='Process', value=f'{memory_usage:.2f} MiB\n{cpu_usage:.2f}% CPU')


        embed.add_field(name='Guilds', value=len(self.bot.guilds))
        embed.add_field(name='Commands Run', value=sum(self.bot.command_stats.values()))
        embed.add_field(name='Uptime', value=self.get_bot_uptime(brief=True))
        embed.set_footer(text='Made with discord.py', icon_url='http://i.imgur.com/5BFecvA.png')
        await ctx.send(embed=embed)

    def censor_object(self, obj):
        if not isinstance(obj, str) and obj.id in self.bot.blacklist:
            return '[censored]'
        return censor_invite(obj)

    @commands.Cog.listener()
    async def on_socket_raw_send(self, data):
        # kind of weird way to check if we're sending
        # IDENTIFY or RESUME
        if '"op":2' not in data and '"op":6' not in data:
            return

        back_to_json = json.loads(data)
        if back_to_json['op'] == 2:
            payload = back_to_json['d']
            inner_shard = payload.get('shard', [0])
            self._identifies[inner_shard[0]].append(datetime.datetime.utcnow())
        else:
            self._resumes.append(datetime.datetime.utcnow())

        # don't want to permanently grow memory
        self._clear_gateway_data()

    @commands.command(hidden=True)
    @commands.is_owner()
    async def bothealth(self, ctx):
        """Various bot health monitoring tools."""

        # This uses a lot of private methods because there is no
        # clean way of doing this otherwise.

        HEALTHY = discord.Colour(value=0x43B581)
        UNHEALTHY = discord.Colour(value=0xF04947)
        WARNING = discord.Colour(value=0xF09E47)
        total_warnings = 0

        embed = discord.Embed(title='Bot Health Report', colour=HEALTHY)

        # Check the connection pool health.
        pool = self.bot.pool
        total_waiting = len(pool._queue._getters)
        current_generation = pool._generation

        description = [
            f'Total `Pool.acquire` Waiters: {total_waiting}',
            f'Current Pool Generation: {current_generation}',
            f'Connections In Use: {len(pool._holders) - pool._queue.qsize()}'
        ]

        questionable_connections = 0
        connection_value = []
        for index, holder in enumerate(pool._holders, start=1):
            generation = holder._generation
            in_use = holder._in_use is not None
            is_closed = holder._con is None or holder._con.is_closed()
            display = f'gen={holder._generation} in_use={in_use} closed={is_closed}'
            questionable_connections += any((in_use, generation != current_generation))
            connection_value.append(f'<Holder i={index} {display}>')

        joined_value = '\n'.join(connection_value)
        embed.add_field(name='Connections', value=f'```py\n{joined_value}\n```', inline=False)

        spam_control = self.bot.spam_control
        being_spammed = [
            str(key) for key, value in spam_control._cache.items()
            if value._tokens == 0
        ]

        description.append(f'Current Spammers: {", ".join(being_spammed) if being_spammed else "None"}')
        description.append(f'Questionable Connections: {questionable_connections}')

        total_warnings += questionable_connections
        if being_spammed:
            embed.colour = WARNING
            total_warnings += 1

        try:
            task_retriever = asyncio.Task.all_tasks
        except AttributeError:
            # future proofing for 3.9 I guess
            task_retriever = asyncio.all_tasks
        else:
            all_tasks = task_retriever(loop=self.bot.loop)

        event_tasks = [
            t for t in all_tasks
            if 'Client._run_event' in repr(t) and not t.done()
        ]

        cogs_directory = os.path.dirname(__file__)

        inner_tasks = [
            t for t in all_tasks
            if cogs_directory in repr(t)
        ]

        bad_inner_tasks = ", ".join(hex(id(t)) for t in inner_tasks if t.done() and t._exception is not None)
        total_warnings += bool(bad_inner_tasks)
        embed.add_field(name='Inner Tasks', value=f'Total: {len(inner_tasks)}\nFailed: {bad_inner_tasks or "None"}')
        embed.add_field(name='Events Waiting', value=f'Total: {len(event_tasks)}', inline=False)

        command_waiters = len(self._data_batch)
        is_locked = self._batch_lock.locked()
        description.append(f'Commands Waiting: {command_waiters}, Batch Locked: {is_locked}')

        # RESUME/IDENTIFY data
        yesterday = datetime.datetime.utcnow() - datetime.timedelta(days=1)
        total_resumes = sum(1 for dt in self._resumes if dt > yesterday)
        identifies = {
            shard_id: sum(1 for dt in dates if dt > yesterday)
            for shard_id, dates in self._identifies.items()
        }
        absolute_total_identifies = sum(identifies.values())
        resume_info_builder = [
            f'Total RESUMEs: {total_resumes}',
            f'Total IDENTIFYs: {absolute_total_identifies}'
        ]
        for shard_id, total in identifies.items():
            resume_info_builder.append(f'Shard ID {shard_id} IDENTIFYs: {total}')

        if absolute_total_identifies >= (len(self.bot.shards) * 5):
            total_warnings += 1
            embed.colour = WARNING

        embed.add_field(name='Gateway (last 24 hours)', value='\n'.join(resume_info_builder), inline=False)

        memory_usage = self.process.memory_full_info().uss / 1024**2
        cpu_usage = self.process.cpu_percent() / psutil.cpu_count()
        embed.add_field(name='Process', value=f'{memory_usage:.2f} MiB\n{cpu_usage:.2f}% CPU', inline=False)

        global_rate_limit = not self.bot.http._global_over.is_set()
        description.append(f'Global Rate Limit: {global_rate_limit}')

        if command_waiters >= 8:
            total_warnings += 1
            embed.colour = WARNING

        if global_rate_limit or total_warnings >= 9:
            embed.colour = UNHEALTHY

        embed.set_footer(text=f'{total_warnings} warning(s)')
        embed.description = '\n'.join(description)
        await ctx.send(embed=embed)

    @commands.command(hidden=True, aliases=['cancel_task'])
    @commands.is_owner()
    async def debug_task(self, ctx, memory_id: hex_value):
        """Debug a task by a memory location."""
        task = object_at(memory_id)
        if task is None or not isinstance(task, asyncio.Task):
            return await ctx.send(f'Could not find Task object at {hex(memory_id)}.')

        if ctx.invoked_with == 'cancel_task':
            task.cancel()
            return await ctx.send(f'Cancelled task object {task!r}.')

        paginator = commands.Paginator(prefix='```py')
        fp = io.StringIO()
        frames = len(task.get_stack())
        paginator.add_line(f'# Total Frames: {frames}')
        task.print_stack(file=fp)

        for line in fp.getvalue().splitlines():
            paginator.add_line(line)

        for page in paginator.pages:
            await ctx.send(page)

def setup(bot):
    bot.add_cog(Stats(bot))
