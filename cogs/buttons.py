import asyncio
from discord.ext import commands
import discord
from .utils.paginator import Pages
from lxml import etree
import random
import logging
from urllib.parse import quote as uriquote
from lru import LRU
import yarl
import io
import re
import unicodedata

log = logging.getLogger(__name__)

class UrbanDictionaryPages(Pages):
    BRACKETED = re.compile(r'(\[(.+?)\])')
    def __init__(self, ctx, data):
        super().__init__(ctx, entries=data, per_page=1)

    def get_page(self, page):
        return self.entries[page - 1]

    def cleanup_definition(self, definition, *, regex=BRACKETED):
        def repl(m):
            word = m.group(2)
            return f'[{word}](http://{word.replace(" ", "-")}.urbanup.com)'

        ret = regex.sub(repl, definition)
        if len(ret) >= 2048:
            return ret[0:2000] + ' [...]'
        return ret

    def prepare_embed(self, entry, page, *, first=False):
        if self.maximum_pages > 1:
            title = f'{entry["word"]}: {page} out of {self.maximum_pages}'
        else:
            title = entry['word']

        self.embed = e = discord.Embed(colour=0xE86222, title=title, url=entry['permalink'])
        e.set_footer(text=f'by {entry["author"]}')
        e.description = self.cleanup_definition(entry['definition'])

        try:
            up, down = entry['thumbs_up'], entry['thumbs_down']
        except KeyError:
            pass
        else:
            e.add_field(name='Votes', value=f'\N{THUMBS UP SIGN} {up} \N{THUMBS DOWN SIGN} {down}', inline=False)

        try:
            date = discord.utils.parse_time(entry['written_on'][0:-1])
        except (ValueError, KeyError):
            pass
        else:
            e.timestamp = date

class RedditMediaURL:
    VALID_PATH = re.compile(r'/r/[A-Za-z0-9_]+/comments/[A-Za-z0-9]+(?:/.+)?')

    def __init__(self, url):
        self.url = url
        self.filename = url.parts[1] + '.mp4'

    @classmethod
    async def convert(cls, ctx, argument):
        try:
            url = yarl.URL(argument)
        except Exception as e:
            raise commands.BadArgument('Not a valid URL.')

        headers = {
            'User-Agent': 'Discord:RoboDanny:v4.0 (by /u/Rapptz)'
        }
        await ctx.trigger_typing()
        if url.host == 'v.redd.it':
            # have to do a request to fetch the 'main' URL.
            async with ctx.session.get(url, headers=headers) as resp:
                url = resp.url

        is_valid_path = url.host.endswith('.reddit.com') and cls.VALID_PATH.match(url.path)
        if not is_valid_path:
            raise commands.BadArgument('Not a reddit URL.')

        # Now we go the long way
        async with ctx.session.get(url / '.json', headers=headers) as resp:
            if resp.status != 200:
                raise commands.BadArgument(f'Reddit API failed with {resp.status}.')

            data = await resp.json()
            try:
                submission = data[0]['data']['children'][0]['data']
            except (KeyError, TypeError, IndexError):
                raise commands.BadArgument('Could not fetch submission.')

            try:
                media = submission['media']['reddit_video']
            except (KeyError, TypeError):
                try:
                    # maybe it's a cross post
                    crosspost = submission['crosspost_parent_list'][0]
                    media = crosspost['media']['reddit_video']
                except (KeyError, TypeError, IndexError):
                    raise commands.BadArgument('Could not fetch media information.')

            try:
                fallback_url = yarl.URL(media['fallback_url'])
            except KeyError:
                raise commands.BadArgument('Could not fetch fall back URL.')

            return cls(fallback_url)

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

    @commands.command(usage='<url>')
    @commands.cooldown(1, 5.0, commands.BucketType.member)
    async def vreddit(self, ctx, *, reddit: RedditMediaURL):
        """Downloads a v.redd.it submission.

        Regular reddit URLs or v.redd.it URLs are supported.
        """
        async with ctx.session.get(reddit.url) as resp:
            if resp.status != 200:
                return await ctx.send('Could not download video.')

            if int(resp.headers['Content-Length']) >= ctx.guild.filesize_limit:
                return await ctx.send('Video is too big to be uploaded.')

            data = await resp.read()
            await ctx.send(file=discord.File(io.BytesIO(data), filename=reddit.filename))

    @vreddit.error
    async def on_vreddit_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(error)

    @commands.command(usage='<url>')
    @commands.cooldown(1, 5.0, commands.BucketType.member)
    async def vreddit(self, ctx, *, reddit: RedditMediaURL):
        """Downloads a v.redd.it submission.

        Regular reddit URLs or v.redd.it URLs are supported.
        """

        filesize = ctx.guild.filesize_limit if ctx.guild else 8388608
        async with ctx.session.get(reddit.url) as resp:
            if resp.status != 200:
                return await ctx.send('Could not download video.')

            if int(resp.headers['Content-Length']) >= filesize:
                return await ctx.send('Video is too big to be uploaded.')

            data = await resp.read()
            await ctx.send(file=discord.File(io.BytesIO(data), filename=reddit.filename))

    @vreddit.error
    async def on_vreddit_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(error)

    @commands.command(name='urban')
    async def _urban(self, ctx, *, word):
        """Searches urban dictionary."""

        url = 'http://api.urbandictionary.com/v0/define'
        async with ctx.session.get(url, params={'term': word}) as resp:
            if resp.status != 200:
                return await ctx.send(f'An error occurred: {resp.status} {resp.reason}')

            js = await resp.json()
            data = js.get('list', [])
            if not data:
                return await ctx.send('No results found, sorry.')

        try:
            pages = UrbanDictionaryPages(ctx, data)
            await pages.paginate()
        except Exception as e:
            await ctx.send(e)

def setup(bot):
    bot.add_cog(Buttons(bot))
