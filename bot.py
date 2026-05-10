import discord
from discord import app_commands
import asyncio
import random
import string
import json
import os
from datetime import datetime, timedelta

# ================== CONFIG ==================

TOKEN = os.environ.get("DISCORD_TOKEN")
DATA_FILE = "lazy_sources_data.json"

intents = discord.Intents.all()

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# ================== DATA ==================

data = {
    "vouch_channel_id": None,
    "welcome_channel_id": None,
    "welcome_image_url": None,
    "redeem_role_id": None
}

keys = {}
tickets = {}
ticket_counter = 1

# ================== LOAD DATA ==================

if os.path.exists(DATA_FILE):
    try:
        with open(DATA_FILE, "r") as f:
            loaded = json.load(f)

            data.update(loaded.get("settings", {}))
            keys.update(loaded.get("keys", {}))
            tickets.update(loaded.get("tickets", {}))
            ticket_counter = loaded.get("ticket_counter", 1)

    except Exception as e:
        print(f"Load Error: {e}")

# ================== SAVE ==================

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump({
            "settings": data,
            "keys": keys,
            "tickets": tickets,
            "ticket_counter": ticket_counter
        }, f, indent=4)

# ================== HELPERS ==================

def generate_key():
    return "-".join(
        ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        for _ in range(4)
    )

# ================== MAIN DASHBOARD ==================

class MainDashboard(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Purchase",
        style=discord.ButtonStyle.blurple,
        custom_id="purchase_btn"
    )
    async def purchase(self, interaction: discord.Interaction, button: discord.ui.Button):

        if str(interaction.user.id) in tickets:
            return await interaction.response.send_message(
                "You already have an open ticket.",
                ephemeral=True
            )

        global ticket_counter

        channel_name = f"ticket-{ticket_counter}"

        overwrites = {
            interaction.guild.default_role:
                discord.PermissionOverwrite(read_messages=False),

            interaction.user:
                discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True
                ),

            interaction.guild.me:
                discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True
                )
        }

        ticket_channel = await interaction.guild.create_text_channel(
            name=channel_name,
            overwrites=overwrites
        )

        tickets[str(interaction.user.id)] = ticket_channel.id
        ticket_counter += 1

        save_data()

        embed = discord.Embed(
            title="Purchase Ticket",
            description="Please wait for staff.",
            color=discord.Color.blue()
        )

        await ticket_channel.send(
            content=interaction.user.mention,
            embed=embed,
            view=TicketView()
        )

        await interaction.response.send_message(
            f"Ticket created: {ticket_channel.mention}",
            ephemeral=True
        )

    @discord.ui.button(
        label="Redeem Key",
        style=discord.ButtonStyle.green,
        custom_id="redeem_btn"
    )
    async def redeem(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RedeemModal())

# ================== TICKET VIEW ==================

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Claim",
        style=discord.ButtonStyle.green,
        custom_id="claim_ticket_btn"
    )
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "Admin only.",
                ephemeral=True
            )

        await interaction.response.send_message(
            f"Claimed by {interaction.user.mention}"
        )

    @discord.ui.button(
        label="Close",
        style=discord.ButtonStyle.red,
        custom_id="close_ticket_btn"
    )
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "Admin only.",
                ephemeral=True
            )

        await interaction.response.send_message("Closing ticket...")

        await asyncio.sleep(2)

        for uid, cid in list(tickets.items()):
            if cid == interaction.channel.id:
                del tickets[uid]
                break

        save_data()

        await interaction.channel.delete()

# ================== REDEEM MODAL ==================

class RedeemModal(discord.ui.Modal, title="Redeem Key"):

    key_input = discord.ui.TextInput(
        label="Enter Key",
        placeholder="ABCD-EFGH-IJKL-MNOP",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):

        key = self.key_input.value.strip().upper()

        if key not in keys:
            return await interaction.response.send_message(
                "Invalid key.",
                ephemeral=True
            )

        info = keys[key]

        if info.get("redeemed"):
            return await interaction.response.send_message(
                "This key has already been redeemed.",
                ephemeral=True
            )

        if info.get("expires"):

            expire_time = datetime.fromisoformat(info["expires"])

            if datetime.utcnow() > expire_time:

                del keys[key]
                save_data()

                return await interaction.response.send_message(
                    "This key expired.",
                    ephemeral=True
                )

        role = interaction.guild.get_role(info["role_id"])

        if role is None:
            return await interaction.response.send_message(
                "Role not found. Run /panel again.",
                ephemeral=True
            )

        try:
            await interaction.user.add_roles(role)

        except Exception as e:
            return await interaction.response.send_message(
                f"Failed to give role: {e}",
                ephemeral=True
            )

        keys[key]["redeemed"] = True
        keys[key]["redeemed_by"] = interaction.user.id

        save_data()

        await interaction.response.send_message(
            f"Key redeemed successfully. You received {role.mention}",
            ephemeral=True
        )

# ================== PANEL ==================

@tree.command(name="panel", description="Create dashboard")
@app_commands.default_permissions(administrator=True)
async def panel(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    role: discord.Role
):

    data["redeem_role_id"] = role.id

    save_data()

    embed = discord.Embed(
        title="Lazy Sources",
        description="Use the buttons below.",
        color=discord.Color.blue()
    )

    await channel.send(
        embed=embed,
        view=MainDashboard()
    )

    await interaction.response.send_message(
        "Panel created.",
        ephemeral=True
    )

# ================== GENERATE KEY ==================

@tree.command(name="generatekey", description="Generate key")
@app_commands.default_permissions(administrator=True)
async def generatekey(
    interaction: discord.Interaction,
    duration: str,
    user: discord.Member = None
):

    if data.get("redeem_role_id") is None:
        return await interaction.response.send_message(
            "Run /panel first.",
            ephemeral=True
        )

    durations = {
        "1d": 1,
        "3d": 3,
        "7d": 7,
        "14d": 14,
        "30d": 30,
        "lifetime": None
    }

    days = durations.get(duration.lower())

    if days is None and duration.lower() != "lifetime":
        return await interaction.response.send_message(
            "Invalid duration. Use: 1d, 3d, 7d, 14d, 30d, lifetime",
            ephemeral=True
        )

    key = generate_key()

    expires = (
        datetime.utcnow() + timedelta(days=days)
    ).isoformat() if days else None

    keys[key] = {
        "role_id": data["redeem_role_id"],
        "expires": expires,
        "redeemed": False
    }

    save_data()

    time_text = f"{days} day(s)" if days else "Lifetime"

    if user:

        msg = (
            f"{user.mention} you have been whitelisted.\n\n"
            f"Please redeem the following code:\n\n"
            f"`{key}`\n"
            f"Duration: {time_text}"
        )

        await interaction.response.send_message(
            msg,
            ephemeral=False
        )

    else:
        await interaction.response.send_message(
            f"Generated key:\n`{key}`",
            ephemeral=True
        )

# ================== ADMIN DM ==================

@tree.command(name="dm", description="DM a user")
@app_commands.default_permissions(administrator=True)
async def dm(
    interaction: discord.Interaction,
    user: discord.Member,
    message: str
):

    try:
        await user.send(message)

        await interaction.response.send_message(
            f"DM sent to {user.mention}",
            ephemeral=True
        )

    except Exception as e:
        await interaction.response.send_message(
            f"Failed to DM user: {e}",
            ephemeral=True
        )

# ================== ROLE ALL ==================

@tree.command(name="roleall", description="Give role to all members")
@app_commands.default_permissions(administrator=True)
async def roleall(
    interaction: discord.Interaction,
    role: discord.Role
):

    await interaction.response.defer()

    count = 0

    for member in interaction.guild.members:

        if member.bot:
            continue

        try:
            await member.add_roles(role)
            count += 1

        except:
            pass

        await asyncio.sleep(0.3)

    await interaction.followup.send(
        f"Gave {role.mention} to {count} members."
    )

# ================== WELCOMER ==================

@tree.command(name="welcomer", description="Set welcome channel")
@app_commands.default_permissions(administrator=True)
async def welcomer(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):

    data["welcome_channel_id"] = channel.id

    save_data()

    await interaction.response.send_message(
        f"Welcome channel set to {channel.mention}",
        ephemeral=True
    )

@tree.command(name="setwelcomeimage", description="Set welcome image")
@app_commands.default_permissions(administrator=True)
async def setwelcomeimage(
    interaction: discord.Interaction,
    image_url: str
):

    data["welcome_image_url"] = image_url

    save_data()

    await interaction.response.send_message(
        "Welcome image updated.",
        ephemeral=True
    )

@tree.command(name="welcomertest", description="Test welcome message")
@app_commands.default_permissions(administrator=True)
async def welcomertest(interaction: discord.Interaction):

    if not data.get("welcome_channel_id"):
        return await interaction.response.send_message(
            "Welcome channel not set.",
            ephemeral=True
        )

    channel = bot.get_channel(data["welcome_channel_id"])

    if channel is None:
        return await interaction.response.send_message(
            "Channel not found.",
            ephemeral=True
        )

    embed = discord.Embed(
        title="Welcome",
        description=f"Welcome {interaction.user.mention}!",
        color=discord.Color.blue()
    )

    if data.get("welcome_image_url"):
        embed.set_image(url=data["welcome_image_url"])

    await channel.send(embed=embed)

    await interaction.response.send_message(
        "Test sent.",
        ephemeral=True
    )

# ================== MEMBER JOIN ==================

@bot.event
async def on_member_join(member):

    if not data.get("welcome_channel_id"):
        return

    channel = bot.get_channel(data["welcome_channel_id"])

    if channel is None:
        return

    embed = discord.Embed(
        title="Welcome",
        description=f"Welcome {member.mention}!",
        color=discord.Color.blue()
    )

    if data.get("welcome_image_url"):
        embed.set_image(url=data["welcome_image_url"])

    await channel.send(embed=embed)

# ================== READY ==================

@bot.event
async def on_ready():

    await tree.sync()

    bot.add_view(MainDashboard())
    bot.add_view(TicketView())

    print(f"Logged in as {bot.user}")
    print("Commands synced")

# ================== START ==================

if TOKEN is None:
    print("Error: DISCORD_TOKEN environment variable not set.")
else:
    bot.run(TOKEN)
