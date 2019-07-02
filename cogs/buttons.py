import asyncio
from discord.ext import commands
import logging
import random
import unicodedata
from urllib.parse import quote as uriquote

import discord
from discord.ext import commands

from .utils import checks

log = logging.getLogger(__name__)

def date(argument):
    formats = (
        '%Y/%m/%d',
        '%Y-%m-%d',
    )

    for fmt in formats:
        try:
            return datetime.strptime(argument, fmt)
        except ValueError:
            continue

    raise commands.BadArgument('Cannot convert to date. Expected YYYY/MM/DD or YYYY-MM-DD.')

class Buttons(commands.Cog):
    """Buttons that make you feel."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(hidden=True)
    async def feelgood(self, ctx):
        """press"""
        await ctx.send('*pressed*')

    @commands.command(hidden=True)
    async def feelbad(self, ctx):
        """depress"""
        await ctx.send('*depressed*')

    @commands.command()
    async def love(self, ctx):
        """What is love?"""
        await ctx.send(random.choice((
            'https://www.youtube.com/watch?v=HEXWRTEbj1I',
            'https://www.youtube.com/watch?v=i0p1bmr0EmE',
            'an intense feeling of deep affection',
            'something we don\'t have'
        )))

    @commands.command(hidden=True)
    async def bored(self, ctx):
        """boredom looms"""
        await ctx.send('http://i.imgur.com/BuTKSzf.png')

    @commands.command(hidden=True)
    async def hello(self, ctx):
        """Displays my intro message."""
        await ctx.send('Hello! I\'m a robot! Danny#0007 made me.')

    @commands.command(pass_context=True)
    @checks.mod_or_permissions(manage_messages=True)
    async def nostalgia(self, ctx, date: date, *, channel: discord.TextChannel = None):
        """Pins an old message from a specific date.

        If a channel is not given, then pins from the channel the
        command was ran on.

        The format of the date must be either YYYY-MM-DD or YYYY/MM/DD.
        """
        channel = channel or ctx.channel

        message = await channel.history(after=date, limit=1).flatten()

        if len(message) == 0:
            return await ctx.send('Could not find message.')

        message = message[0]

        try:
            await message.pin()
        except discord.HTTPException:
            await ctx.send('Could not pin message.')
        else:
            await ctx.send('Pinned message.')

    @nostalgia.error
    async def nostalgia_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(error)

    @commands.command()
    async def charinfo(self, ctx, *, characters: str):
        """Shows you information about a number of characters.

        Only up to 25 characters at a time.
        """

        def to_string(c):
            ord_c = ord(c)
            try:
                name = unicodedata.name(c)
                as_code = f'\\N{{{name}}}'

                info = f'U+{ord_c:>04X}: `{as_code}`'
            except ValueError:
                name = 'Name not found.'
                as_code = f'\\U{ord_c:>06x}'

                info = f'`{as_code}`: {name}'

            return f'{info} — {c} — <http://www.fileformat.info/info/unicode/char/{ord_c:x}>'

        msg = '\n'.join(map(to_string, characters))
        if len(msg) > 2000:
            return await ctx.send('Output too long to display.')
        await ctx.send(msg)

    @commands.command(rest_is_raw=True, hidden=True)
    @commands.is_owner()
    async def echo(self, ctx, *, content):
        await ctx.send(content)

    @commands.command(hidden=True)
    async def cud(self, ctx):
        """pls no spam"""
        for i in range(3):
            await ctx.send(3 - i)
            await asyncio.sleep(1)

        await ctx.send('go')

def setup(bot):
    bot.add_cog(Buttons(bot))
