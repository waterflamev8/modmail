import asyncio
import datetime
import logging

import discord
import orjson

from discord.ext import commands

log = logging.getLogger(__name__)


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot_misc_updater = bot.loop.create_task(self.bot_misc_updater())

    async def bot_misc_updater(self):
        while True:
            async with self.bot.pool.acquire() as conn:
                data = await conn.fetch("SELECT guild, prefix FROM data")
                bans = await conn.fetch("SELECT identifier, category FROM ban")
                premium = await conn.fetch("SELECT identifier, expiry FROM premium WHERE expiry IS NOT NULL")
            for row in data:
                self.bot.all_prefix[row[0]] = row[1]
            self.bot.banned_users = [row[0] for row in bans if row[1] == 0]
            self.bot.banned_guilds = [row[0] for row in bans if row[1] == 1]
            if self.bot.cluster == 1:
                for row in premium:
                    if row[1] < int(datetime.datetime.utcnow().timestamp() * 1000):
                        await self.bot.tools.wipe_premium(self.bot, row[0])
            await asyncio.sleep(60)

    @commands.Cog.listener()
    async def on_ready(self):
        bot = await self.bot.user()
        self.bot.avatar_url = bot.avatar_url
        self.bot.id = bot.id
        self.bot.mention = bot.mention
        self.bot.name = bot.name
        log.info(f"{bot} is online!")
        log.info("--------")

    @commands.Cog.listener()
    async def on_socket_response(self, message):
        if message["t"] == "PRESENCE_UPDATE":
            await self.bot.state.sadd(f"user:{message['d']['user']['id']}", message["d"]["guild_id"])
            await self.bot.state.sadd("user_keys", f"user:{message['d']['user']['id']}")
        elif message["t"] == "GUILD_MEMBER_ADD":
            if int(message["d"]["user"]["id"]) == self.bot.id:
                await self.bot.state.set(f"member:{message['d']['guild_id']}:{self.bot.id}", message["d"])
            await self.bot.state.sadd(f"user:{message['d']['user']['id']}", message["d"]["guild_id"])
            await self.bot.state.sadd("user_keys", f"user:{message['d']['user']['id']}")
        elif message["t"] == "GUILD_MEMBER_REMOVE":
            if int(message["d"]["user"]["id"]) == self.bot.id:
                await self.bot.state.delete(
                    f"member:{message['d']['guild_id']}:{self.bot.id}",
                )
            await self.bot.state.srem(f"user:{message['d']['user']['id']}", message["d"]["guild_id"])
            await self.bot.state.srem(f"user_keys", f"user:{message['d']['user']['id']}")
        elif message["t"] == "GUILD_MEMBER_UPDATE":
            if int(message["d"]["user"]["id"]) == self.bot.id:
                member = await self.bot.state.get(f"member:{message['d']['guild_id']}:{self.bot.id}")
                if member:
                    member["roles"] = message["d"]["roles"]
                    await self.bot.state.set(f"member:{message['d']['guild_id']}:{self.bot.id}", member)
            await self.bot.state.sadd(f"user:{message['d']['user']['id']}", message["d"]["guild_id"])
            await self.bot.state.sadd("user_keys", f"user:{message['d']['user']['id']}")
        elif message["t"] == "GUILD_CREATE":
            for member in message["d"]["members"]:
                if int(member["user"]["id"]) == self.bot.id:
                    await self.bot.state.set(f"member:{message['d']['id']}:{self.bot.id}", member)
                await self.bot.state.sadd(f"user:{member['user']['id']}", message["d"]["id"])
                await self.bot.state.sadd("user_keys", f"user:{message['user']['id']}")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, member):
        if reaction.emoji not in ["⏮️", "◀️", "⏹️", "▶️", "⏭️"]:
            return
        if member.bot:
            return
        menus = await self.bot._connection._get("reaction_menus") or []
        for (index, menu) in enumerate(menus):
            channel = menu["channel"]
            message = menu["message"]
            if reaction.message.channel.id != channel or reaction.message.id != message:
                continue
            page = menu["page"]
            all_pages = menu["all_pages"]
            if reaction.emoji == "⏮️":
                page = 0
            elif reaction.emoji == "◀️" and page > 0:
                page -= 1
            elif reaction.emoji == "⏹️":
                await self.bot.http.clear_reactions(reaction.message.channel.id, reaction.message.id)
                return
            elif reaction.emoji == "▶️" and page < len(all_pages) - 1:
                page += 1
            elif reaction.emoji == "⏭️":
                page = len(all_pages) - 1
            await self.bot.http.edit_message(channel, message, embed=all_pages[page])
            await self.bot.http.remove_reaction(
                reaction.message.channel.id, reaction.message.id, reaction.emoji, member.id
            )
            menu["page"] = page
            menus[index] = menu
            await self.bot._connection.redis.set("reaction_menus", orjson.dumps(menus).decode("utf-8"))
            break

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.id:
            return
        if payload.member:
            return
        if payload.emoji.name not in ["⏮️", "◀️", "⏹️", "▶️", "⏭️"]:
            return
        menus = await self.bot._connection._get("reaction_menus") or []
        for (index, menu) in enumerate(menus):
            channel = menu["channel"]
            message = menu["message"]
            if payload.channel_id != channel or payload.message_id != message:
                continue
            page = menu["page"]
            all_pages = menu["all_pages"]
            if payload.emoji.name == "⏮️":
                page = 0
            elif payload.emoji.name == "◀️" and page > 0:
                page -= 1
            elif payload.emoji.name == "⏹️":
                for emoji in ["⏮️", "◀️", "⏹️", "▶️", "⏭️"]:
                    await self.bot.http.remove_own_reaction(payload.channel_id, payload.message_id, emoji)
                return
            elif payload.emoji.name == "▶️" and page < len(all_pages) - 1:
                page += 1
            elif payload.emoji.name == "⏭️":
                page = len(all_pages) - 1
            await self.bot.http.edit_message(channel, message, embed=all_pages[page])
            menu["page"] = page
            menus[index] = menu
            await self.bot._connection.redis.set("reaction_menus", orjson.dumps(menus).decode("utf-8"))
            break

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        ctx = await self.bot.get_context(message)
        if not ctx.command:
            return
        # self.bot.prom.commands.inc({"name": ctx.command.name})
        if message.guild:
            if message.guild.id in self.bot.banned_guilds:
                await message.guild.leave()
                return
            permissions = await message.channel.permissions_for(await ctx.guild.me())
            if permissions.send_messages is False:
                return
            elif permissions.embed_links is False:
                await message.channel.send("The Embed Links permission is needed for basic commands to work.")
                return
        if message.author.id in self.bot.banned_users:
            await ctx.send(
                embed=discord.Embed(description="You are banned from the bot.", colour=self.bot.error_colour)
            )
            return
        if ctx.command.cog_name in ["Owner", "Admin"] and (
            ctx.author.id in self.bot.config.admins or ctx.author.id in self.bot.config.owners
        ):
            embed = discord.Embed(
                title=ctx.command.name.title(),
                description=ctx.message.content,
                colour=self.bot.primary_colour,
                timestamp=datetime.datetime.utcnow(),
            )
            embed.set_author(name=f"{ctx.author} ({ctx.author.id})", icon_url=ctx.author.avatar_url)
            if self.bot.config.admin_channel:
                await self.bot.http.send_message(self.bot.config.admin_channel, None, embed=embed.to_dict())
        if ctx.prefix == f"<@{self.bot.id}> " or ctx.prefix == f"<@!{self.bot.id}> ":
            ctx.prefix = self.bot.tools.get_guild_prefix(self.bot, message.guild)
        await self.bot.invoke(ctx)

    @commands.Cog.listener()
    async def on_raw_message(self, message):
        if message.author.bot:
            return
        ctx = await self.bot.get_context(message)
        if not ctx.command:
            return
        # self.bot.prom.commands.inc({"name": ctx.command.name})
        if message.author.id in self.bot.banned_users:
            await ctx.send(
                embed=discord.Embed(description="You are banned from the bot.", colour=self.bot.error_colour)
            )
            return
        if ctx.command.cog_name in ["Owner", "Admin"] and (
            ctx.author.id in self.bot.config.admins or ctx.author.id in self.bot.config.owners
        ):
            embed = discord.Embed(
                title=ctx.command.name.title(),
                description=ctx.message.content,
                colour=self.bot.primary_colour,
                timestamp=datetime.datetime.utcnow(),
            )
            embed.set_author(name=f"{ctx.author} ({ctx.author.id})", icon_url=ctx.author.avatar_url)
            if self.bot.config.admin_channel:
                await self.bot.http.send_message(self.bot.config.admin_channel, None, embed=embed.to_dict())
        if ctx.prefix == f"<@{self.bot.id}> " or ctx.prefix == f"<@!{self.bot.id}> ":
            ctx.prefix = self.bot.tools.get_guild_prefix(self.bot, message.guild)
        await self.bot.invoke(ctx)

    # @commands.Cog.listener()
    # async def on_member_join(self, member):
    #
    #
    # @commands.Cog.listener()
    # async def on_member_remove(self, member):
    #     if member.id == self.bot.id:
    #         await self.bot._redis.delete(f"member:{member.guild.id}:{(await self.bot.user().id)}")
    #     await self.bot._redis.srem(f"user:{member.id}", member.guild.id)
    #     await self.bot._redis.sadd("user_keys", f"user:{member.id}")


def setup(bot):
    bot.add_cog(Events(bot))
