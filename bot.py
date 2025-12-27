
import os
import json
import re
import asyncio
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

# ============================================================
# ENV / CONFIGa
# ============================================================
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID_RAW = os.getenv("OWNER_ID")

if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN in .env")
if not OWNER_ID_RAW or not OWNER_ID_RAW.isdigit():
    raise RuntimeError("Missing or invalid OWNER_ID in .env")

OWNER_ID = int(OWNER_ID_RAW)

# Hard-coded lists (cannot add new list names)
# Edit this to your desired lists + emojis
ALLOWED_LISTS: dict[str, str] = {
    "banned": "🚫",
    "limited": "1️⃣",
    "semi-limited": "2️⃣",
}

# People who can NEVER be kicked by the bot (by ID)
KICK_WHITELIST_USER_IDS = {
    250856281722716161,  # you
    515994530852503562,  # enzo
    289595726504132630,  # YP
    134410345614671872,  # Alice
    944113745527980133,  # YP2
    245381297931943936,  # edge4
    1092891407494164602, # scoldz
    115549664563953669,  # aditya
    327264297799647243,  # pookie
    431202427828568065,  # lyric
    701173877107327037,  # mbeast
    470645179905212426,  # jugg
}

# Roles that can NEVER be kicked by the bot (by role ID)
# (Leave empty if you don't want role-based whitelisting.)
KICK_WHITELIST_ROLE_IDS: set[int] = set()

POLL_DURATION_SECONDS = 600  # 10 minutes
YES_EMOJI = "✅"
NO_EMOJI = "❌"

ADD_POLL_QUESTION_TEMPLATE = "Should we add **{item}** to **{list_name}**?"
REMOVE_POLL_QUESTION_TEMPLATE = "Should we remove **{item}** from **{list_name}**?"

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "lists.json"

print("USING DATA FILE:", DATA_FILE)
print("EXISTS?:", DATA_FILE.exists())
if DATA_FILE.exists():
    print("SIZE:", DATA_FILE.stat().st_size)



# ============================================================
# BOT SETUP
# ============================================================
intents = discord.Intents.default()
intents.message_content = True  # required for prefix commands
intents.members = True  # recommended for kick/role checks

bot = commands.Bot(command_prefix="!", intents=intents)
def needs_seed() -> bool:
    if not DATA_FILE.exists():
        return True
    try:
        data = json.loads(DATA_FILE.read_text("utf-8"))
        if not isinstance(data, dict):
            return True
        # seed if all items lists are empty
        for v in data.values():
            if isinstance(v, dict) and v.get("items"):
                return False
            if isinstance(v, list) and v:
                return False
        return True
    except Exception:
        return True


if os.getenv("SEED_LISTS") == "true" and needs_seed():
    print("Seeding lists.json from SEED_LISTS mode")

    seed_data = {
        "banned": {
    "emoji": "🚫",
    "items": [
      "Aditya Lee Sin",
      "Bendel Corki",
      "Jugg Ezreal",
      "Jugg Kalista",
      "Jugg Lucian",
      "Jugg Malphite",
      "Mbeast Camille",
      "Mbeast Fiora",
      "Mbeast Riven",
      "Pak Kayle",
      "Pak Singed",
      "Pak Zaheen",
      "Shorterace Ambessa",
      "Yoshi Fiora",
      "Yoshi Kennen",
      "Yoshi Talon"
    ]
  },
  "limited": {
    "emoji": "1️⃣",
    "items": [
      "Jugg Mf",
      "Mikey Smolder",
      "Mikey Zeri",
      "Pak Taliyah",
      "Richie Pyke",
      "Richie Vel'koz"
    ]
  },
  "semi-limited": {
    "emoji": "2️⃣",
    "items": []
  }
    }

    DATA_FILE.write_text(json.dumps(seed_data, indent=2), encoding="utf-8")

# ============================================================
# STORAGE
# Structure:
# {
#   "banned": {"emoji": "🚫", "items": ["ItemA", "ItemB"]},
#   ...
# }
# ============================================================
def load_lists() -> dict[str, dict]:
    if not DATA_FILE.exists():
        return {}
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            cleaned: dict[str, dict] = {}
            for name, value in data.items():
                if not isinstance(name, str):
                    continue
                n = name.lower().strip()

                if isinstance(value, dict):
                    items = value.get("items", [])
                    emoji = value.get("emoji", ALLOWED_LISTS.get(n, "📋"))
                    if isinstance(items, list):
                        cleaned[n] = {
                            "emoji": str(emoji),
                            "items": [str(x) for x in items],
                        }
                elif isinstance(value, list):
                    # backward compatibility if it used to be list-only
                    cleaned[n] = {
                        "emoji": ALLOWED_LISTS.get(n, "📋"),
                        "items": [str(x) for x in value],
                    }
            return cleaned
    except json.JSONDecodeError:
        pass
    return {}

def save_lists(data: dict[str, dict]) -> None:
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def initialize_fixed_lists(existing: dict[str, dict]) -> dict[str, dict]:
    """
    Ensures:
    - All allowed lists exist (even if empty)
    - Emojis match ALLOWED_LISTS (hard-coded)
    - Any lists not in ALLOWED_LISTS are dropped
    """
    fixed: dict[str, dict] = {}
    for name, emoji in ALLOWED_LISTS.items():
        prior = existing.get(name, {})
        items = prior.get("items", []) if isinstance(prior, dict) else []
        if not isinstance(items, list):
            items = []
        fixed[name] = {"emoji": emoji, "items": [str(x) for x in items]}
    return fixed

lists_data = initialize_fixed_lists(load_lists())
save_lists(lists_data)

# ============================================================
# HELPERS
# ============================================================
def is_owner(ctx: commands.Context) -> bool:
    return ctx.author.id == OWNER_ID

def normalize_item(text: str) -> str:
    # Capitalize first letter of every word, rest lowercase
    return " ".join(word.capitalize() for word in text.split())

def natural_sort_key(s: str):
    # "A2" < "A10" (natural numeric ordering within strings)
    parts = re.split(r"(\d+)", s.casefold())
    return [int(p) if p.isdigit() else p for p in parts]

def resort(list_name: str) -> None:
    lists_data[list_name]["items"].sort(key=natural_sort_key)

def contains_case_insensitive(items: list[str], value: str) -> bool:
    v = value.casefold()
    return any(x.casefold() == v for x in items)

def allowed_lists_string() -> str:
    return ", ".join(sorted(ALLOWED_LISTS.keys()))

def is_kick_whitelisted(member: discord.Member) -> bool:
    if member.id in KICK_WHITELIST_USER_IDS:
        return True
    if KICK_WHITELIST_ROLE_IDS and any(role.id in KICK_WHITELIST_ROLE_IDS for role in member.roles):
        return True
    return False

async def run_yes_no_poll(ctx: commands.Context, question: str) -> tuple[int, int, int]:
    """
    Creates a poll message, waits POLL_DURATION_SECONDS, thens returns (yes_votes, no_votes, invalid_votes).
    One vote per person:
      - if a user reacted to both ✅ and ❌, their vote is invalid and not counted.
    Bots are ignored.
    """
    poll_message = await ctx.send(
        f"📊 **Vote ({POLL_DURATION_SECONDS // 60} minutes)**\n{question}\n\n"
        f"React with {YES_EMOJI} for Yes or {NO_EMOJI} for No.\n"
        f"⚠️ Voting both counts as invalid."
    )

    await poll_message.add_reaction(YES_EMOJI)
    await poll_message.add_reaction(NO_EMOJI)

    await asyncio.sleep(POLL_DURATION_SECONDS)

    # Re-fetch to get final reactions (message could be deleted)
    try:
        poll_message = await ctx.channel.fetch_message(poll_message.id)
    except (discord.NotFound, discord.Forbidden):
        return 0, 0, 0

    yes_voters: set[int] = set()
    no_voters: set[int] = set()

    for reaction in poll_message.reactions:
        if str(reaction.emoji) == YES_EMOJI:
            async for u in reaction.users():
                if not u.bot:
                    yes_voters.add(u.id)
        elif str(reaction.emoji) == NO_EMOJI:
            async for u in reaction.users():
                if not u.bot:
                    no_voters.add(u.id)

    overlap = yes_voters & no_voters
    yes_voters -= overlap
    no_voters -= overlap

    return len(yes_voters), len(no_voters), len(overlap)

def resolve_removal_target(items: list[str], target: str) -> tuple[int | None, str | None]:
    """
    Returns (index, item_value) if target matches an item by:
      - number (1-based)
      - exact text (case-insensitive)
    Otherwise returns (None, None)
    """
    target = target.strip()
    if not target:
        return None, None

    if target.isdigit():
        idx = int(target) - 1
        if 0 <= idx < len(items):
            return idx, items[idx]
        return None, None

    t = target.casefold()
    for i, existing in enumerate(items):
        if existing.casefold() == t:
            return i, existing

    return None, None

# ============================================================
# EVENTS
# ============================================================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")

# ============================================================
# COMMANDS: ECHO (anyone)
# ============================================================
@bot.command(name="echo", help="Echo back text. Usage: !echo hello world")
async def echo(ctx: commands.Context, *, text: str):
    await ctx.send(text)

@echo.error
async def echo_error(ctx: commands.Context, error: Exception):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: `!echo <message>`")
    else:
        raise error

# ============================================================
# COMMANDS: KICK (mods)
# ============================================================
@bot.command(name="kick", help="Kick a member. Usage: !kick @user optional reason")
@commands.has_permissions(kick_members=True)
@commands.bot_has_permissions(kick_members=True)
async def kick(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
    if member == ctx.author:
        return await ctx.send("You can’t kick yourself.")
    if bot.user and member.id == bot.user.id:
        return await ctx.send("Nice try 😄")
    if is_kick_whitelisted(member):
        return await ctx.send("🛡️ That member is whitelisted and cannot be kicked.")

    # role hierarchy checks
    if member.top_role >= ctx.author.top_role and ctx.guild and ctx.guild.owner_id != ctx.author.id:
        return await ctx.send("You can’t kick someone with an equal or higher role than you.")

    me = ctx.guild.me if ctx.guild else None
    if me and member.top_role >= me.top_role:
        return await ctx.send("I can’t kick them — move my bot role higher.")

    await member.kick(reason=f"{reason} (kicked by {ctx.author} / {ctx.author.id})")
    await ctx.send(f"👢 **Kicked** {member.mention}\nReason: {reason}")

@kick.error
async def kick_error(ctx: commands.Context, error: Exception):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: `!kick @user [reason]`")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("I couldn’t find that member.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("You don’t have permission to use `!kick`.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("I don’t have the **Kick Members** permission.")
    else:
        raise error

# ============================================================
# COMMANDS: LISTS (anyone)
# ============================================================
@bot.command(name="list", help="Show one list. Usage: !list <name>")
async def show_list(ctx: commands.Context, name: str):
    name = name.lower().strip()
    if name not in ALLOWED_LISTS:
        return await ctx.send(f"❌ Invalid list. Allowed lists: {allowed_lists_string()}")

    emoji = lists_data[name]["emoji"]
    items = lists_data[name]["items"]

    if not items:
        return await ctx.send(f"{emoji} **{normalize_item(name)}**:\n(empty)")

    output = "\n".join(f"{i+1}. {v}" for i, v in enumerate(items))
    await ctx.send(f"{emoji} **{normalize_item(name)}**:\n{output}")

@bot.command(name="banlist", help="Shows all lists (each separated).")
async def list_all(ctx: commands.Context):
    blocks = []
    for name in sorted(ALLOWED_LISTS.keys()):
        emoji = lists_data[name]["emoji"]
        items = lists_data[name]["items"]
        title = normalize_item(name)

        if not items:
            blocks.append(f"{emoji} **{title}**:\n(empty)")
        else:
            body = "\n".join(f"• {v}" for v in items)
            blocks.append(f"{emoji} **{title}**:\n{body}")

    message = "\n\n".join(blocks)

    # Discord message limit safety
    for start in range(0, len(message), 1900):
        await ctx.send(message[start:start + 1900])

@show_list.error
async def show_list_error(ctx: commands.Context, error: Exception):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Usage: `!list <name>`\nAllowed lists: {allowed_lists_string()}")
    else:
        raise error

# ============================================================
# COMMANDS: MUTATE LISTS (OWNER = instant, OTHERS = poll)
# ============================================================
@bot.command(name="add", help="Add item. Owner adds instantly; others trigger a vote. Usage: !add <list> <item>")
async def add_item(ctx: commands.Context, list_name: str, *, item: str):
    list_name = list_name.lower().strip()
    if list_name not in ALLOWED_LISTS:
        return await ctx.send(f"❌ Invalid list. Allowed lists: {allowed_lists_string()}")

    item = normalize_item(item.strip())
    if not item:
        return await ctx.send("Usage: `!add <list> <item>`")

    items = lists_data[list_name]["items"]

    # Ignore duplicates (case-insensitive)
    if contains_case_insensitive(items, item):
        resort(list_name)
        save_lists(lists_data)
        return await ctx.send(f"⚠️ Already exists in **{normalize_item(list_name)}**.")

    # If owner, add immediately
    if is_owner(ctx):
        items.append(item)
        resort(list_name)
        save_lists(lists_data)
        emoji = lists_data[list_name]["emoji"]
        return await ctx.send(f"✅ Added to {emoji} **{normalize_item(list_name)}**: {item}")

    # Non-owner: run a poll
    question = ADD_POLL_QUESTION_TEMPLATE.format(
        item=item,
        list_name=normalize_item(list_name)
    )
    yes_votes, no_votes, invalid_votes = await run_yes_no_poll(ctx, question)

    # Decision rule:
    # - Yes must win (strictly more than No)
    # - Yes must be 2 or more
    if yes_votes >= 2 and yes_votes > no_votes:
        if contains_case_insensitive(items, item):
            return await ctx.send("ℹ️ It was already added while the poll was running.")

        items.append(item)
        resort(list_name)
        save_lists(lists_data)
        emoji = lists_data[list_name]["emoji"]
        await ctx.send(
            f"🗳️ Poll ended — ✅ {yes_votes} / ❌ {no_votes} (invalid: {invalid_votes})\n"
            f"✅ Approved! Added to {emoji} **{normalize_item(list_name)}**: {item}"
        )
    else:
        await ctx.send(
            f"🗳️ Poll ended — ✅ {yes_votes} / ❌ {no_votes} (invalid: {invalid_votes})\n"
            f"❌ Not approved (needs ✅ to win AND have 2+ votes)."
        )

@add_item.error
async def add_item_error(ctx: commands.Context, error: Exception):
    if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
        await ctx.send(f"Usage: `!add <list> <item>`\nAllowed lists: {allowed_lists_string()}")
    else:
        raise error

@bot.command(name="remove", help="Remove item. Owner removes instantly; others trigger a vote. Usage: !remove <list> <number|text>")
async def remove_item(ctx: commands.Context, list_name: str, *, target: str):
    list_name = list_name.lower().strip()
    if list_name not in ALLOWED_LISTS:
        return await ctx.send(f"❌ Invalid list. Allowed lists: {allowed_lists_string()}")

    target = target.strip()
    if not target:
        return await ctx.send("Usage: `!remove <list> <number|text>`")

    items = lists_data[list_name]["items"]

    idx, resolved_item = resolve_removal_target(items, target)
    if idx is None or resolved_item is None:
        return await ctx.send("❌ Item not found (or invalid number).")

    # Owner removes immediately
    if is_owner(ctx):
        removed = items.pop(idx)
        resort(list_name)
        save_lists(lists_data)
        return await ctx.send(f"🗑️ Removed from **{normalize_item(list_name)}**: {removed}")

    # Non-owner: run a poll
    question = REMOVE_POLL_QUESTION_TEMPLATE.format(
        item=resolved_item,
        list_name=normalize_item(list_name)
    )
    yes_votes, no_votes, invalid_votes = await run_yes_no_poll(ctx, question)

    if yes_votes >= 2 and yes_votes > no_votes:
        # Re-resolve in case list changed while poll ran
        idx2, resolved_item2 = resolve_removal_target(items, resolved_item)
        if idx2 is None:
            return await ctx.send("ℹ️ It was already removed while the poll was running.")

        removed = items.pop(idx2)
        resort(list_name)
        save_lists(lists_data)
        await ctx.send(
            f"🗳️ Poll ended — ✅ {yes_votes} / ❌ {no_votes} (invalid: {invalid_votes})\n"
            f"✅ Approved! Removed from **{normalize_item(list_name)}**: {removed}"
        )
    else:
        await ctx.send(
            f"🗳️ Poll ended — ✅ {yes_votes} / ❌ {no_votes} (invalid: {invalid_votes})\n"
            f"❌ Not approved (needs ✅ to win AND have 2+ votes)."
        )

@remove_item.error
async def remove_item_error(ctx: commands.Context, error: Exception):
    if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
        await ctx.send(
            "Usage: `!remove <list> <number|text>`\n"
            f"Allowed lists: {allowed_lists_string()}\n"
            "Examples:\n"
            "- `!remove banned 2`\n"
            "- `!remove limited Blue Eyes White Dragon`"
        )
    else:
        raise error

# ============================================================
# RUN
# ============================================================
bot.run(TOKEN)
