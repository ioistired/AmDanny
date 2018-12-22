from dataclasses import dataclass
import time
from typing import Dict, Set

import discord
from discord.ext import commands

@dataclass
class StalkedUser:
	user: discord.User
	stalkers: Set[discord.User]
	last_changed: float

	async def notify_stalkers(self, old_status: discord.Status, new_status: discord.Status):
		for stalker in self.stalkers:
			with contextlib.suppress(discord.Forbidden):
				await stalker.send(f"{self.user}'s status just changed from {old_status} to {new_status}")

class Stalking:
	# values that are "more online"/"more active" come first
	STATUS_HIERARCHY = dict(map(reversed, enumerate((discord.Status.online, discord.Status.dnd, discord.Status.idle, discord.Status.offline))))
	STATUS_CHANGED_TRESHOLD = 10

	def __init__(self, bot):
		self.bot = bot
		# map user IDs to their last status change
		self.stalked: Dict[int, StalkedUser] = {}

	async def on_ready(self):
		await self.bot.change_presence(status=discord.Status.idle)

	@commands.command()
	@commands.is_owner()
	async def stalk(self, ctx, *, user: discord.User):
		"""starts stalking a given user until the next time i reboot"""
		try:
			stalked = self.stalked[user.id]
		except KeyError:
			self.stalked[user.id] = StalkedUser(user=user, stalkers={ctx.author}, last_changed=time.monotonic())
		else:
			stalked.stalkers.add(ctx.author)

		await ctx.send(f"""✅ I will DM you when {user}'s status "increases".""")

	@commands.command()
	async def unstalk(self, ctx, *, user: discord.User):
		"""stops stalking someone"""
		self.stalked.pop(user.id, None)
		await ctx.message.add_reaction('✅')

	@stalk.error
	async def stalk_error(self, ctx, error):
		if isinstance(error, commands.UserInputError):
			return await ctx.send(error)
		if isinstance(error, commands.NotOwner):
			with contextlib.suppress(discord.Forbidden):
				await ctx.message.add_reaction(discord.PartialEmoji(animated=False, name='error', id=487322218989092889))

		raise

	async def on_member_update(self, before, after):
		try:
			stalked = self.stalked[after.id]
		except KeyError:
			return

		if (
			self.STATUS_HIERARCHY[after.status] < self.STATUS_HIERARCHY[before.status]
			and time.monotonic() - stalked.last_changed > self.STATUS_CHANGED_TRESHOLD
		):
			# the user has been "more online" for a little while
			await stalked.notify_stalkers()

		if before.status is not after.status:
			stalked.last_changed = time.monotonic()

def setup(bot):
	bot.add_cog(Stalking(bot))
