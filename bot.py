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
    "redeem_role_id": None,
    "log_channel_id": None,
    "panel_title": "Lazy Sources",
    "panel_description": "Use the buttons below to purchase or redeem a key.",
    "panel_color": "blue",
    "welcome_title": "Welcome",
    "ticket_title": "Purchase Ticket",
    "ticket_description": "Please wait for staff. A helper will assist you shortly."
}

keys = {}
tickets = {}
ticket_counter = 1

# Color mapping
color_map = {
    "blue": discord.Color.blue(),
    "green": discord.Color.green(),
    "red": discord.Color.red(),
    "purple": discord.Color.purple(),
    "orange": discord.Color.orange(),
    "yellow": discord.Color.yellow(),
    "pink": discord.Color.magenta(),
    "default": discord.Color.blue()
}

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

async def send_log(guild, title, description, color_name="blue"):
    log_channel_id = data.get("log_channel_id")
    if log_channel_id is None:
        return
    channel = guild.get_channel(log_channel_id)
    if channel:
        color = color_map.get(color_name, discord.Color.blue())
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.utcnow())
        await channel.send(embed=embed)

def get_embed_color(color_name):
    return color_map.get(color_name, discord.Color.blue())

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
            title=data["ticket_title"],
            description=data["ticket_description"],
            color=get_embed_color(data["panel_color"])
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
        
        await send_log(interaction.guild, "🎫 Ticket Created", f"{interaction.user.mention} created ticket {ticket_channel.mention}", "orange")

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

        await send_log(interaction.guild, "🔒 Ticket Closed", f"Ticket {interaction.channel.name} was closed by {interaction.user.mention}", "red")

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
        
        # Check if key is restricted to specific users
        if info.get("allowed_users") and len(info["allowed_users"]) > 0:
            if str(interaction.user.id) not in info["allowed_users"]:
                return await interaction.response.send_message(
                    "This key is restricted to specific users only. You are not allowed to redeem it.",
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

        # Mark key as redeemed
        keys[key]["redeemed"] = True
        keys[key]["redeemed_by"] = interaction.user.id
        keys[key]["redeemed_by_name"] = str(interaction.user)
        keys[key]["redeemed_at"] = datetime.utcnow().isoformat()

        save_data()

        await interaction.response.send_message(
            f"✅ Key redeemed successfully. You received {role.mention}",
            ephemeral=True
        )
        
        # Log to logging channel with full details
        duration_text = info.get("expires", "Lifetime")
        if duration_text != "Lifetime":
            expire_dt = datetime.fromisoformat(info["expires"])
            duration_text = f"Expires: <t:{int(expire_dt.timestamp())}:R>"
        else:
            duration_text = "Lifetime (Never expires)"
        
        log_description = f"""**User:** {interaction.user.mention} (`{interaction.user.id}`)
**Key:** `{key}`
**Duration:** {duration_text}
**Role Given:** {role.mention}
**Redeemed At:** <t:{int(datetime.utcnow().timestamp())}:F>"""
        
        await send_log(interaction.guild, "🔑 Key Redeemed", log_description, "green")

# ================== SET LOGGING CHANNEL ==================

@tree.command(name="setloggingchannel", description="Set the channel where key redemptions and actions are logged")
@app_commands.default_permissions(administrator=True)
async def setloggingchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    data["log_channel_id"] = channel.id
    save_data()
    
    embed = discord.Embed(
        title="✅ Logging Channel Set",
        description=f"All key redemptions, ticket actions, and system logs will be sent to {channel.mention}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)
    
    # Send a test log
    await send_log(interaction.guild, "📋 Logging System Activated", f"Logging channel set by {interaction.user.mention}\nAll key redemptions will now be logged here.", "blue")

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
        title=data["panel_title"],
        description=data["panel_description"],
        color=get_embed_color(data["panel_color"])
    )

    await channel.send(
        embed=embed,
        view=MainDashboard()
    )

    await interaction.response.send_message(
        f"Panel created in {channel.mention}",
        ephemeral=True
    )

# ================== EDIT PANEL TEXT ==================

@tree.command(name="editpanel", description="Edit the panel embed title, description, or color")
@app_commands.default_permissions(administrator=True)
async def editpanel(
    interaction: discord.Interaction,
    title: str = None,
    description: str = None,
    color: str = None
):
    if title:
        data["panel_title"] = title
    if description:
        data["panel_description"] = description
    if color and color.lower() in color_map:
        data["panel_color"] = color.lower()
    elif color:
        return await interaction.response.send_message(f"Invalid color. Choose from: {', '.join(color_map.keys())}", ephemeral=True)
    
    save_data()
    
    embed = discord.Embed(
        title="Panel Settings Updated",
        description=f"**Title:** {data['panel_title']}\n**Description:** {data['panel_description']}\n**Color:** {data['panel_color']}",
        color=get_embed_color(data["panel_color"])
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ================== EDIT TICKET TEXT ==================

@tree.command(name="editticket", description="Edit the ticket embed title and description")
@app_commands.default_permissions(administrator=True)
async def editticket(
    interaction: discord.Interaction,
    title: str = None,
    description: str = None
):
    if title:
        data["ticket_title"] = title
    if description:
        data["ticket_description"] = description
    
    save_data()
    
    embed = discord.Embed(
        title="Ticket Settings Updated",
        description=f"**Title:** {data['ticket_title']}\n**Description:** {data['ticket_description']}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ================== GENERATE KEY ==================

@tree.command(name="generatekey", description="Generate a key (optional: restrict to specific users)")
@app_commands.default_permissions(administrator=True)
async def generatekey(
    interaction: discord.Interaction,
    duration: str,
    user1: discord.Member = None,
    user2: discord.Member = None,
    user3: discord.Member = None,
    user4: discord.Member = None,
    user5: discord.Member = None
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

    # Collect allowed users
    allowed_users = []
    for user in [user1, user2, user3, user4, user5]:
        if user:
            allowed_users.append(str(user.id))
    
    keys[key] = {
        "role_id": data["redeem_role_id"],
        "expires": expires,
        "redeemed": False,
        "allowed_users": allowed_users,
        "created_by": str(interaction.user),
        "created_at": datetime.utcnow().isoformat()
    }

    save_data()

    time_text = f"{days} day(s)" if days else "Lifetime"
    
    # Build response message
    if allowed_users:
        user_mentions = ", ".join([f"<@{uid}>" for uid in allowed_users])
        response_msg = f"Key generated: `{key}`\nDuration: {time_text}\n**Restricted to:** {user_mentions}"
        
        # Log to logging channel
        await send_log(interaction.guild, "🔑 Key Generated (Restricted)", f"**Key:** `{key}`\n**Duration:** {time_text}\n**Created by:** {interaction.user.mention}\n**Allowed Users:** {user_mentions}", "blue")
    else:
        response_msg = f"Key generated: `{key}`\nDuration: {time_text}\n**Anyone can redeem this key**"
        
        await send_log(interaction.guild, "🔑 Key Generated (Public)", f"**Key:** `{key}`\n**Duration:** {time_text}\n**Created by:** {interaction.user.mention}\n**Allowed Users:** Anyone", "blue")

    await interaction.response.send_message(response_msg, ephemeral=True)

# ================== KEY STATS ==================

@tree.command(name="keystats", description="View key usage statistics")
@app_commands.default_permissions(administrator=True)
async def keystats(interaction: discord.Interaction):
    total_keys = len(keys)
    redeemed_keys = sum(1 for k in keys.values() if k.get("redeemed", False))
    unredeemed_keys = total_keys - redeemed_keys
    
    # Calculate expired keys
    expired_keys = 0
    for k, v in keys.items():
        if v.get("expires") and not v.get("redeemed", False):
            expire_time = datetime.fromisoformat(v["expires"])
            if datetime.utcnow() > expire_time:
                expired_keys += 1
    
    embed = discord.Embed(title="📊 Key Statistics", color=discord.Color.blue(), timestamp=datetime.utcnow())
    embed.add_field(name="Total Keys Generated", value=str(total_keys), inline=True)
    embed.add_field(name="Redeemed Keys", value=str(redeemed_keys), inline=True)
    embed.add_field(name="Unredeemed Keys", value=str(unredeemed_keys), inline=True)
    embed.add_field(name="Expired Keys", value=str(expired_keys), inline=True)
    embed.add_field(name="Redeem Rate", value=f"{round((redeemed_keys/total_keys)*100, 1) if total_keys > 0 else 0}%", inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ================== MASS DM ==================

@tree.command(name="massdm", description="DM all members with a specific role")
@app_commands.default_permissions(administrator=True)
async def massdm(
    interaction: discord.Interaction,
    role: discord.Role,
    message: str
):
    await interaction.response.send_message(f"📨 Sending DMs to {role.mention} members. This may take a while...", ephemeral=True)
    
    count = 0
    failed = 0
    
    for member in interaction.guild.members:
        if role in member.roles and not member.bot:
            try:
                await member.send(message)
                count += 1
            except:
                failed += 1
            await asyncio.sleep(1)  # Rate limit protection
    
    await interaction.followup.send(f"✅ DM sent to {count} members. ❌ Failed: {failed}", ephemeral=True)
    
    await send_log(interaction.guild, "📨 Mass DM Sent", f"**Role:** {role.mention}\n**Recipients:** {count}\n**Failed:** {failed}\n**Message:** {message[:100]}...", "purple")

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
        title=data["welcome_title"],
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

@tree.command(name="editwelcome", description="Edit welcome message title")
@app_commands.default_permissions(administrator=True)
async def editwelcome(
    interaction: discord.Interaction,
    title: str = None
):
    if title:
        data["welcome_title"] = title
        save_data()
        await interaction.response.send_message(f"Welcome title updated to: {title}", ephemeral=True)

# ================== MEMBER JOIN ==================

@bot.event
async def on_member_join(member):

    if not data.get("welcome_channel_id"):
        return

    channel = bot.get_channel(data["welcome_channel_id"])

    if channel is None:
        return

    embed = discord.Embed(
        title=data["welcome_title"],
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
    print(f"Logging channel ID: {data.get('log_channel_id', 'Not set')}")

# ================== START ==================

if TOKEN is None:
    print("Error: DISCORD_TOKEN environment variable not set.")
else:
    bot.run(TOKEN)
