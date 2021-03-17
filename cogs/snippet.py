import logging

import asyncpg
import discord

from discord.ext import commands

from classes.embed import Embed, ErrorEmbed
from utils import checks

log = logging.getLogger(__name__)


class Snippet(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @checks.is_modmail_channel()
    @checks.in_database()
    @checks.is_premium()
    @checks.is_mod()
    @commands.guild_only()
    @commands.command(description="Use a snippet.", aliases=["s"], usage="snippet <name>")
    async def snippet(self, ctx, *, name: str):
        async with self.bot.pool.acquire() as conn:
            res = await conn.fetchrow(
                "SELECT content FROM snippet WHERE name=$1 AND guild=$2", name.lower(), ctx.guild.id
            )

        if not res:
            await ctx.send(embed=ErrorEmbed(description="The snippet was not found."))
            return

        await self.bot.cogs["ModMailEvents"].send_mail_mod(ctx.message, ctx.prefix, False, res[0], True)

    @checks.is_modmail_channel()
    @checks.in_database()
    @checks.is_premium()
    @checks.is_mod()
    @commands.guild_only()
    @commands.command(description="Use a snippet anonymously.", aliases=["as"], usage="asnippet <name>")
    async def asnippet(self, ctx, *, name: str):
        async with self.bot.pool.acquire() as conn:
            res = await conn.fetchrow(
                "SELECT content FROM snippet WHERE name=$1 AND guild=$2", name.lower(), ctx.guild.id
            )

        if not res:
            await ctx.send(embed=ErrorEmbed(description="The snippet was not found."))
            return

        await self.bot.cogs["ModMailEvents"].send_mail_mod(ctx.message, ctx.prefix, True, res[0], True)

    @checks.in_database()
    @checks.is_premium()
    @checks.is_mod()
    @commands.guild_only()
    @commands.command(
        description="Add a snippet. Tags `{username}`, `{usertag}`, `{userid}` and `{usermention}` can be used.",
        usage="snippetadd <name> <content>",
    )
    async def snippetadd(self, ctx, name: str, *, content: str):
        if len(name) > 100:
            await ctx.send(embed=ErrorEmbed(description="The snippet name cannot exceed 100 characters."))
            return

        if len(content) > 1000:
            await ctx.send(embed=ErrorEmbed(description="The snippet content cannot exceed 1000 characters."))
            return

        async with self.bot.pool.acquire() as conn:
            try:
                await conn.execute("INSERT INTO snippet VALUES ($1, $2, $3)", ctx.guild.id, name.lower(), content)
            except asyncpg.UniqueViolationError:
                await ctx.send(embed=ErrorEmbed(description="A snippet with that name already exists."))
                return

        await ctx.send(embed=Embed(description="The snippet was added successfully."))

    @checks.in_database()
    @checks.is_premium()
    @checks.is_mod()
    @commands.guild_only()
    @commands.command(description="Remove a snippet.", usage="snippetremove <name>")
    async def snippetremove(self, ctx, *, name: str):
        async with self.bot.pool.acquire() as conn:
            res = await conn.execute("DELETE FROM snippet WHERE name=$1 AND guild=$2", name, ctx.guild.id)

        if res == "DELETE 0":
            await ctx.send(embed=ErrorEmbed(description="A snippet with that name was not found."))
            return

        await ctx.send(embed=Embed(description="The snippet was removed successfully."))

    @checks.in_database()
    @checks.is_premium()
    @checks.is_mod()
    @commands.guild_only()
    @commands.command(description="Remove all the snippets.", usage="snippetclear")
    async def snippetclear(self, ctx):
        async with self.bot.pool.acquire() as conn:
            await conn.execute("DELETE FROM snippet WHERE guild=$1", ctx.guild.id)

        await ctx.send(embed=Embed(description="All snippets were removed successfully."))

    @checks.in_database()
    @checks.is_premium()
    @checks.is_mod()
    @checks.bot_has_permissions(add_reactions=True)
    @commands.guild_only()
    @commands.command(
        description="View all the snippets or a specific one if specified.",
        aliases=["viewsnippets", "snippetlist"],
        usage="viewsnippet [name]",
    )
    async def viewsnippet(self, ctx, *, name: str = None):
        if name:
            async with self.bot.pool.acquire() as conn:
                res = await conn.fetchrow(
                    "SELECT name, content FROM snippet WHERE name=$1 AND guild=$2",
                    name.lower(),
                    ctx.guild.id,
                )

            if not res:
                await ctx.send(embed=ErrorEmbed(description="A snippet with that name was not found."))
                return

            embed = Embed(title="Snippet")
            embed.add_field(name="Name", value=res[0], inline=False)
            embed.add_field(name="Content", value=res[1], inline=False)
            await ctx.send(embed=embed)
            return

        async with self.bot.pool.acquire() as conn:
            res = await conn.fetch("SELECT name, content FROM snippet WHERE guild=$1", ctx.guild.id)

        if not res:
            await ctx.send(embed=Embed(description="No snippet has been added yet."))
            return

        all_pages = []
        for chunk in [res[i : i + 10] for i in range(0, len(res), 10)]:
            page = Embed(title="Snippets")

            for snippet in chunk:
                page.add_field(
                    name=snippet[0],
                    value=snippet[1][:97] + "..." if len(snippet[1]) > 100 else snippet[1],
                    inline=False,
                )

            page.set_footer(text="Use the reactions to flip pages.")
            all_pages.append(page)

        if len(all_pages) == 1:
            embed = all_pages[0]
            embed.set_footer(text=discord.Embed.Empty)
            await ctx.send(embed=embed)
            return

        await self.bot.create_reaction_menu(ctx, all_pages)


def setup(bot):
    bot.add_cog(Snippet(bot))
