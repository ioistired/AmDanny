import logging
import random
import unicodedata
from urllib.parse import quote as uriquote

import discord
from discord.ext import commands

log = logging.getLogger(__name__)

class Buttons:
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

    @commands.command()
    async def charinfo(self, ctx, *, characters: str):
        """Shows you information about a number of characters.

        Only up to 25 characters at a time.
        """

        def to_string(c):
            digit = f'{ord(c):x}'
            try:
                name = unicodedata.name(c)
                code_version = f'\\N{{{name}}}'

                info = f'U+{digit:>04}: `{code_version}`'
            except ValueError:
                name = 'Name not found.'
                code_version = f'\\U{digit:>06}'

                info = f'`{code_version}`: {name}'

            return f'{info} — {c} — <http://www.fileformat.info/info/unicode/char/{digit}>'

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
