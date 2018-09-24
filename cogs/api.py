from discord.ext import commands
from .utils import fuzzy
import asyncio
import discord
import re
import lxml.etree as etree

DISCORD_PY_GUILD_ID = 336642139381301249
ROBODANNY_ID = 80528701850124288

class API:
    """Discord API exclusive things."""

    def __init__(self, bot):
        self.bot = bot
        self.issue = re.compile(r'##(?P<number>[0-9]+)')

    async def on_message(self, message):
        if not message.guild or message.guild.id != DISCORD_PY_GUILD_ID:
            return

        # this bot is only a backup for when R. Danny is offline
        robodanny = message.guild.get_member(ROBODANNY_ID)
        if robodanny and robodanny.status is not discord.Status.offline:
            return

        m = self.issue.search(message.content)
        if m is not None:
            url = 'https://github.com/Rapptz/discord.py/issues/'
            await message.channel.send(url + m.group('number'))

    async def build_rtfm_lookup_table(self):
        cache = {}

        page_types = {
            'rewrite': (
                'https://discordpy.readthedocs.org/en/rewrite/api.html',
                'https://discordpy.readthedocs.org/en/rewrite/ext/commands/api.html'
            ),
            'latest': (
                'https://discordpy.readthedocs.org/en/latest/api.html',
            )
        }

        for key, pages in page_types.items():
            sub = cache[key] = {}
            for page in pages:
                async with self.bot.session.get(page) as resp:
                    if resp.status != 200:
                        raise RuntimeError('Cannot build rtfm lookup table, try again later.')

                    text = await resp.text(encoding='utf-8')
                    root = etree.fromstring(text, etree.HTMLParser())
                    nodes = root.findall(".//dt/a[@class='headerlink']")

                    for node in nodes:
                        href = node.get('href', '')
                        as_key = href.replace('#discord.', '').replace('ext.commands.', '')
                        sub[as_key] = page + href

        self._rtfm_cache = cache

    async def do_rtfm(self, ctx, key, obj):
        base_url = f'https://discordpy.readthedocs.org/en/{key}/'

        if obj is None:
            await ctx.send(base_url)
            return

        if not hasattr(self, '_rtfm_cache'):
            await ctx.trigger_typing()
            await self.build_rtfm_lookup_table()

        # identifiers don't have spaces
        obj = obj.replace(' ', '_')

        if key == 'rewrite':
            pit_of_success_helpers = {
                'vc': 'VoiceClient',
                'msg': 'Message',
                'color': 'Colour',
                'perm': 'Permissions',
                'channel': 'TextChannel',
                'chan': 'TextChannel',
            }

            # point the abc.Messageable types properly:
            q = obj.lower()
            for name in dir(discord.abc.Messageable):
                if name[0] == '_':
                    continue
                if q == name:
                    obj = f'abc.Messageable.{name}'
                    break

            def replace(o):
                return pit_of_success_helpers.get(o.group(0), '')

            pattern = re.compile('|'.join(fr'\b{k}\b' for k in pit_of_success_helpers.keys()))
            obj = pattern.sub(replace, obj)

        cache = list(self._rtfm_cache[key].items())
        def transform(tup):
            return tup[0]

        matches = fuzzy.finder(obj, cache, key=lambda t: t[0], lazy=False)[:5]

        e = discord.Embed(colour=discord.Colour.blurple())
        if len(matches) == 0:
            return await ctx.send('Could not find anything. Sorry.')

        e.description = '\n'.join(f'[{key}]({url})' for key, url in matches)
        await ctx.send(embed=e)

    @commands.group(aliases=['rtfd'], invoke_without_command=True)
    async def rtfm(self, ctx, *, obj: str = None):
        """Gives you a documentation link for a discord.py entity.

        Events, objects, and functions are all supported through a
        a cruddy fuzzy algorithm.
        """
        await self.do_rtfm(ctx, 'latest', obj)

    @rtfm.command(name='rewrite')
    async def rtfm_rewrite(self, ctx, *, obj: str = None):
        """Gives you a documentation link for a rewrite discord.py entity."""
        await self.do_rtfm(ctx, 'rewrite', obj)

    async def refresh_faq_cache(self):
        self._faq_cache = {}
        base_urls = {
            'rewrite': 'https://discordpy.readthedocs.io/en/rewrite/faq.html',
            'latest': 'https://discordpy.readthedocs.io/en/latest/faq.html',
        }

        for branch, base_url in base_urls.items():
            self._faq_cache[branch] = faq_entries = {}
            async with self.bot.session.get(base_url) as resp:
                text = await resp.text(encoding='utf-8')

                root = etree.fromstring(text, etree.HTMLParser())
                nodes = root.findall(".//div[@id='questions']/ul[@class='simple']//ul/li//a")
                for node in nodes:
                    faq_entries[''.join(node.itertext()).strip()] = base_url + node.get('href').strip()

    async def do_faq(self, ctx, branch, query):
        if not hasattr(self, 'faq_entries'):
            await self.refresh_faq_cache()

        if query is None:
            return await ctx.send(f'https://discordpy.readthedocs.io/en/{branch}/faq.html')

        matches = fuzzy.extract_matches(query, self._faq_cache[branch], scorer=fuzzy.partial_ratio, score_cutoff=40)
        if len(matches) == 0:
            return await ctx.send('Nothing found…')

        fmt = '\n'.join(f'**{key}**\n{value}' for key, _, value in matches)
        await ctx.send(fmt)

    @commands.group(invoke_without_command=True)
    async def faq(self, ctx, *, query=None):
        """Shows an FAQ entry from the discord.py documentation"""
        await self.do_faq(ctx, 'latest', query)

    @faq.command(name='rewrite')
    async def faq_rewrite(self, ctx, *, query=None):
        await self.do_faq(ctx, 'rewrite', query)

def setup(bot):
    bot.add_cog(API(bot))
