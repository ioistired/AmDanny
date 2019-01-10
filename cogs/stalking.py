import contextlib
from dataclasses import dataclass
import operator
import time
from typing import Dict, List, Set

import discord
from discord.ext import commands

class StalkedUser:
	__slots__ = {'user', 'stalkers', 'last_changed'}

	RECENT_STATUS_CHANGE_THRESHOLD = 10  # seconds

	user: discord.User
	stalkers: Set[discord.User]
	last_changed: float

	def __init__(self, user, stalkers):
		self.user = user
		self.stalkers = stalkers
		self.last_changed = 0.0

	def not_changed_recently(self):
		"""return whether the status changed more than N seconds ago"""
		return self.time_since_last_change() > self.RECENT_STATUS_CHANGE_THRESHOLD

	def time_since_last_change(self):
		"""return how many seconds elapsed since the last time a presence update was tracked"""
		return time.monotonic() - self.last_changed

# builtins.id sucks anyway
id = operator.attrgetter('id')
ERROR = discord.PartialEmoji(animated=False, name='error', id=487322218989092889)

class Stalking:
	# values that are "more online" / "more active" come first
	STATUS_HIERARCHY = dict(map(reversed, enumerate((
		discord.Status.online,
		discord.Status.dnd,
		discord.Status.idle,
		discord.Status.offline))))

	def __init__(self, bot):
		self.bot = bot
		self.stalked: Dict[int, StalkedUser] = {}
		self.lowest_mutual_guilds: dict[int, discord.Guild] = {}

		self._register_events()

	async def on_member_update(self, before, after):
		try:
			stalked = self.stalked[after.id]
		except KeyError:
			return

		# ensure we only handle presence updates once per user
		if after.guild != self.lowest_mutual_guilds[after.id]:
			return

		if (
			self.STATUS_HIERARCHY[after.status] < self.STATUS_HIERARCHY[before.status]
			and stalked.not_changed_recently()
		):
			# the user has become "more online" and stayed that way for a bit
			await self.notify_stalkers(stalked, before.status, after.status)

		if before.status is not after.status:
			stalked.last_changed = time.monotonic()

	async def notify_stalkers(self, stalked: StalkedUser, old_status: discord.Status, new_status: discord.Status):
		for stalker in stalked.stalkers:
			with contextlib.suppress(discord.Forbidden):
				await stalker.send(f"{stalked.user}'s status just changed from {old_status} to {new_status}")

	@commands.command()
	@commands.is_owner()
	async def stalk(self, ctx, *, user: discord.User):
		"""starts stalking a given user until the next time i reboot"""
		try:
			stalked = self.stalked[user.id]
		except KeyError:
			self.stalked[user.id] = StalkedUser(user=user, stalkers={ctx.author})
		else:
			stalked.stalkers.add(ctx.author)

		self.update_lowest_mutual_guild(user)

		await ctx.send(f"""✅ I will DM you when {user}'s status "increases".""", delete_after=5.0)

	@commands.command()
	async def unstalk(self, ctx, *, user: discord.User):
		"""stops stalking someone"""

		error_not_stalking = f"{ERROR} You're not stalking this user."

		try:
			stalkers = self.stalked[user.id].stalkers
		except KeyError:
			# nobody is stalking this user
			await ctx.send(error_not_stalking)
			return

		try:
			stalkers.remove(ctx.author)
		except KeyError:
			await ctx.send(error_not_stalking)
			return

		if not stalkers:
			del self.stalked[user.id]
			self.lowest_mutual_guilds.pop(user.id, None)

		await ctx.message.add_reaction('✅')

	@stalk.error
	async def stalk_error(self, ctx, error):
		if isinstance(error, commands.UserInputError):
			await ctx.send(error)
		elif isinstance(error, commands.NotOwner):
			with contextlib.suppress(discord.Forbidden):
				await ctx.message.add_reaction(ERROR)
		else:
			raise

	### Presence event deduplication

	def update_lowest_mutual_guild(self, member, _id=id):
		if member.id not in self.stalked:
			return

		self.lowest_mutual_guilds[member.id] = min(
			(guild for guild in self.bot.guilds if guild.get_member(member.id)),
			key=_id)

	async def _on_member_join_leave(self, member):
		self.update_lowest_mutual_guild(member)

	async def _on_guild_join_remove(self, guild):
		for member in guild.members:
			self.update_lowest_mutual_guild(member)

	def _register_events(self):
		for event in 'on_member_join', 'on_member_leave':
			self.bot.add_listener(self._on_member_join_leave, event)

		for event in 'on_guild_join', 'on_guild_remove':
			self.bot.add_listener(self._on_guild_join_remove, event)

def setup(bot):
	bot.add_cog(Stalking(bot))
