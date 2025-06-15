import nextcord
from nextcord.ext import commands
from nextcord import Interaction, SlashOption
from nextcord.ui import Button, View
import json
import asyncio
import traceback
import os

intents = nextcord.Intents.all()
intents.members = True
intents.guilds = True
bot = commands.Bot(command_prefix="/", intents=intents)

# Replace with your actual role IDs
ADMIN_ROLE_IDS = [1372651142835863733, 1372651142835863736, 1372651142835863734, 1372651142835863732, 1380148162387251244]
EXEC_ROLE_IDS = [1372651142835863733, 1372651142835863736, 1372651142835863734, 1372651142835863732, 1380148162387251244]
FREE_AGENT_ROLE_ID = 1372651142772953237
MAIN_GUILD_ID = 1372651142760235179  # Main guild ID

async def sync_roles_with_team_data():
    print("Syncing team roles with players...")
    guild = bot.get_guild(MAIN_GUILD_ID)
    if not guild:
        print("Main guild not found!")
        return

    try:
        with open("team_data.json", "r") as f:
            team_data = json.load(f)
    except Exception as e:
        print(f"Failed to load team data: {e}")
        return

    for team_name, team_info in team_data.items():
        role_id = team_info.get("role_id")
        if not role_id:
            print(f"No role_id for {team_name}, skipping")
            continue
            
        role = guild.get_role(role_id)
        if not role:
            print(f"Role {role_id} not found for {team_name}")
            continue

        player_ids = list(team_info.get("players", {}).keys())
        
        # Add roles to team players
        for player_id in player_ids:
            member = guild.get_member(int(player_id))
            if member and role not in member.roles:
                try:
                    await member.add_roles(role, reason="Team sync")
                    print(f"Added {role.name} to {member.display_name}")
                except Exception as e:
                    print(f"Error adding role to {member.display_name}: {e}")

    print("Role sync complete!")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    
    try:
        await bot.sync_all_application_commands()
        print("Commands synced")
    except Exception as e:
        print(f"Command sync failed: {e}")

    await sync_roles_with_team_data()

# REGISTRATION COMMANDS
@bot.slash_command(name="register", description="Register yourself as a player.")
async def register(interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    user_id = str(interaction.user.id)
    
    try:
        with open("registered_players.json", "r") as f:
            registered_players = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        registered_players = {}

    if user_id in registered_players:
        await interaction.followup.send("⚠️ Already registered!", ephemeral=True)
        return

    registered_players[user_id] = {
        "name": interaction.user.name,
        "id": user_id,
        "team": None,
        "status": "free_agent",
        "2c": False,
        "rating": "N/A"
    }

    with open("registered_players.json", "w") as f:
        json.dump(registered_players, f, indent=4)

    role = interaction.guild.get_role(FREE_AGENT_ROLE_ID)
    if role:
        try:
            await interaction.user.add_roles(role)
        except nextcord.Forbidden:
            await interaction.followup.send("✅ Registered but couldn't assign role")
            return

    await interaction.followup.send("✅ Registered successfully!")

@bot.slash_command(name="unregister", description="Unregister yourself.")
async def unregister(interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    user_id = str(interaction.user.id)
    
    try:
        with open("registered_players.json", "r") as f:
            registered_players = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        await interaction.followup.send("❌ No registered players", ephemeral=True)
        return

    if user_id not in registered_players:
        await interaction.followup.send("❌ You're not registered", ephemeral=True)
        return

    del registered_players[user_id]
    
    with open("registered_players.json", "w") as f:
        json.dump(registered_players, f, indent=4)

    role = interaction.guild.get_role(FREE_AGENT_ROLE_ID)
    if role and role in interaction.user.roles:
        try:
            await interaction.user.remove_roles(role)
        except nextcord.Forbidden:
            await interaction.followup.send("✅ Unregistered but couldn't remove role", ephemeral=True)
            return

    await interaction.followup.send("✅ Unregistered successfully", ephemeral=True)

@bot.slash_command(name="listregistered", description="List all registered players.")
async def listregistered(interaction: Interaction):
    # Defer to avoid timeout errors (ephemeral = only user sees it)
    await interaction.response.defer(ephemeral=True)

    # Permission check
    author_roles = [role.id for role in interaction.user.roles]
    if not any(rid in ADMIN_ROLE_IDS + EXEC_ROLE_IDS for rid in author_roles):
        await interaction.followup.send("🚫 Permission denied", ephemeral=True)
        return

    try:
        with open("registered_players.json", "r") as f:
            registered_players = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        await interaction.followup.send("📭 No players registered", ephemeral=True)
        return

    if not registered_players:
        await interaction.followup.send("📭 No players registered", ephemeral=True)
        return

    # Prepare message chunks (Discord has message length limits)
    chunks = []
    current_chunk = []

    for i, (pid, pdata) in enumerate(registered_players.items()):
        name = pdata.get("name", "Unknown")
        team = pdata.get("team", "None")
        current_chunk.append(f"{i+1}. **{name}** (ID: `{pid}`, Team: `{team}`)")

        if len(current_chunk) >= 10:
            chunks.append("\n".join(current_chunk))
            current_chunk = []

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    # Send all chunks
    for chunk in chunks:
        await interaction.followup.send(chunk, ephemeral=True)

# 2C COMMANDS
@bot.slash_command(name="set2c", description="Allow player to sign with 2 clubs.")
async def set2c(
    interaction: Interaction,
    member: nextcord.Member = SlashOption(description="Player to modify"),
    allow_2c: bool = SlashOption(description="Enable 2C?")
):
    await interaction.response.defer(ephemeral=True)
    author_roles = [role.id for role in interaction.user.roles]
    if not any(rid in ADMIN_ROLE_IDS + EXEC_ROLE_IDS for rid in author_roles):
        await interaction.followup.send("🚫 Permission denied", ephemeral=True)
        return

    user_id = str(member.id)
    
    try:
        with open("registered_players.json", "r") as f:
            registered_players = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        await interaction.followup.send("❌ No registered players", ephemeral=True)
        return

    if user_id not in registered_players:
        await interaction.followup.send("❌ Player not registered", ephemeral=True)
        return

    registered_players[user_id]["2c"] = allow_2c
    
    with open("registered_players.json", "w") as f:
        json.dump(registered_players, f, indent=4)

    await interaction.followup.send(
        f"✅ Updated 2C for **{member.name}** to `{allow_2c}`",
        ephemeral=True
    )

@bot.slash_command(name="list2c", description="List 2C-enabled players.")
async def list2c(interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    
    try:
        with open("registered_players.json", "r") as f:
            registered_players = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        await interaction.followup.send("❌ No registered players", ephemeral=True)
        return

    two_c_players = [
        pdata["name"] for pdata in registered_players.values() 
        if pdata.get("2c", False)
    ]
    
    if not two_c_players:
        await interaction.followup.send("🤷‍♂️ No 2C-enabled players", ephemeral=True)
        return

    embed = nextcord.Embed(
        title="🔁 2C-Enabled Players",
        description="\n".join(f"- {name}" for name in two_c_players),
        color=nextcord.Color.green()
    )
    await interaction.followup.send(embed=embed, ephemeral=True)

# PLAYER PROFILE COMMANDS
@bot.slash_command(name="assignrating", description="Assign player rating.")
async def assignrating(
    interaction: Interaction,
    member: nextcord.Member = SlashOption(description="Player to rate"),
    rating: str = SlashOption(description="Rating (e.g., 80, S, A)")
):
    await interaction.response.defer(ephemeral=True)
    user_id = str(member.id)
    
    try:
        with open("registered_players.json", "r") as f:
            registered_players = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        await interaction.followup.send("❌ No registered players", ephemeral=True)
        return

    if user_id not in registered_players:
        await interaction.followup.send("❌ Player not registered", ephemeral=True)
        return

    registered_players[user_id]["rating"] = rating.upper() if rating.isalpha() else rating
    
    with open("registered_players.json", "w") as f:
        json.dump(registered_players, f, indent=4)

    await interaction.followup.send(
        f"✅ Assigned rating **{rating}** to {member.display_name}",
        ephemeral=True
    )

@bot.slash_command(name="ratingsshow", description="Show player ratings.")
async def ratingsshow(interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    
    try:
        with open("registered_players.json", "r") as f:
            registered_players = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        await interaction.followup.send("❌ No registered players", ephemeral=True)
        return

    rated_players = [
        (pdata["name"], pdata.get("rating", "N/A"))
        for pdata in registered_players.values()
        if pdata.get("rating", "N/A") != "N/A"
    ]
    
    if not rated_players:
        await interaction.followup.send("⚠️ No players rated", ephemeral=True)
        return

    embed = nextcord.Embed(title="🎖️ Player Ratings", color=nextcord.Color.gold())
    for name, rating in rated_players:
        embed.add_field(name=name, value=rating, inline=True)
    
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.slash_command(name="getprofile", description="View player profile.")
async def getprofile(
    interaction: Interaction,
    member: nextcord.Member = SlashOption(description="Player to view")
):
    await interaction.response.defer(ephemeral=True)
    user_id = str(member.id)
    
    try:
        with open("registered_players.json", "r") as f:
            registered_players = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        await interaction.followup.send("❌ No registered players", ephemeral=True)
        return

    if user_id not in registered_players:
        await interaction.followup.send("❌ Player not registered", ephemeral=True)
        return

    player = registered_players[user_id]
    
    # Ensure all fields exist
    player.setdefault("team", None)
    player.setdefault("status", "N/A")
    player.setdefault("2c", False)
    player.setdefault("rating", "N/A")

    embed = nextcord.Embed(
        title=f"📄 {player['name']}'s Profile",
        color=nextcord.Color.blue()
    )
    embed.add_field(name="ID", value=player["id"], inline=False)
    embed.add_field(name="Status", value=player["status"], inline=True)
    embed.add_field(name="Team", value=player["team"] or "None", inline=True)
    embed.add_field(name="2C Enabled", value=str(player["2c"]), inline=True)
    embed.add_field(name="Rating", value=player["rating"], inline=True)

    await interaction.followup.send(embed=embed, ephemeral=True)

# TEAM MANAGEMENT
class SignConfirmationView(View):
    def __init__(self, player_id, team_name, chairman_id, seasons):
        super().__init__(timeout=600)
        self.player_id = str(player_id)
        self.team_name = team_name
        self.chairman_id = chairman_id
        self.seasons = seasons
        self.accepted = False

    async def on_timeout(self):
        try:
            player = self.get_player()
            if player:
                await player.send(f"⌛ Signing offer from **{self.team_name}** expired")
        except Exception:
            pass
        self.disable_all_buttons()

    def get_player(self):
        guild = bot.get_guild(MAIN_GUILD_ID)
        return guild.get_member(int(self.player_id)) if guild else None

    def disable_all_buttons(self):
        for child in self.children:
            if isinstance(child, Button):
                child.disabled = True

    @nextcord.ui.button(label="✅ Accept (No RC)", style=nextcord.ButtonStyle.green)
    async def accept_no_rc(self, button: Button, interaction: Interaction):
        await self.process_accept(interaction, False)

    @nextcord.ui.button(label="🏷️ Accept + RC", style=nextcord.ButtonStyle.green)
    async def accept_rc(self, button: Button, interaction: Interaction):
        await self.process_accept(interaction, True)

    @nextcord.ui.button(label="❌ Decline", style=nextcord.ButtonStyle.red)
    async def decline(self, button: Button, interaction: Interaction):
        self.disable_all_buttons()
        await interaction.response.edit_message(content="❌ Offer declined", view=self)
        try:
            chairman = interaction.guild.get_member(int(self.chairman_id))
            if chairman:
                await chairman.send(
                    f"❌ **{interaction.user.name}** declined offer to join **{self.team_name}**"
                )
        except Exception:
            pass
        self.stop()

    async def process_accept(self, interaction: Interaction, release_clause: bool):
        if self.accepted:
            await interaction.response.send_message("⚠️ You’ve already accepted the offer.", ephemeral=True)
            return
        self.accepted = True
        await interaction.response.defer(ephemeral=True)

        player_id = str(interaction.user.id)

        try:
            with open("team_data.json", "r") as f:
                team_data = json.load(f)
            with open("registered_players.json", "r") as f:
                reg_players = json.load(f)
        except Exception:
            await interaction.followup.send("💥 Failed to load data files.", ephemeral=True)
            return

        team = team_data.get(self.team_name)
        if not team:
            await interaction.followup.send("❌ Team not found.", ephemeral=True)
            return

        # Roster limit check
        if len(team.get("roster", [])) >= 20:
            await interaction.followup.send("❌ Team roster is full (20/20).", ephemeral=True)
            return

        # Remove from other teams
        for tname, tdata in team_data.items():
            if tname != self.team_name:
                tdata.get("players", {}).pop(player_id, None)
                tdata["roster"] = [p for p in tdata.get("roster", []) if p.get("id") != player_id]

        # Add to current team
        team.setdefault("players", {})[player_id] = {"seasons": self.seasons}
        if not any(p["id"] == player_id for p in team.get("roster", [])):
            team["roster"].append({
                "id": player_id,
                "seasons": self.seasons,
                "release_clause": release_clause
            })

        reg_players[player_id] = {
            "name": interaction.user.name,
            "id": player_id,
            "team": self.team_name,
            "status": "signed",
            "2c": reg_players.get(player_id, {}).get("2c", False),
            "rating": reg_players.get(player_id, {}).get("rating", "N/A")
        }

        try:
            with open("team_data.json", "w") as f:
                json.dump(team_data, f, indent=4)
            with open("registered_players.json", "w") as f:
                json.dump(reg_players, f, indent=4)
        except:
            await interaction.followup.send("⚠️ Failed to save updated data.", ephemeral=True)
            return

        # Notify chairman
        try:
            chairman = bot.get_guild(MAIN_GUILD_ID).get_member(int(self.chairman_id))
            if chairman:
                await chairman.send(
                    f"✅ **{interaction.user.name}** joined **{self.team_name}** "
                    f"(RC: {'Yes' if release_clause else 'No'})"
                )
        except:
            pass

        self.disable_all_buttons()
        await interaction.followup.edit_message(
            content=f"✅ You’ve joined **{self.team_name}**! (RC: {'Yes' if release_clause else 'No'})",
            view=self
        )
        self.stop()


@bot.slash_command(name="sign", description="Sign a player to your team.")
async def sign(
    interaction: Interaction,
    player: nextcord.Member = SlashOption(description="Player to sign"),
    team_name: str = SlashOption(description="Your team"),
    seasons: int = SlashOption(description="Contract seasons")
):
    await interaction.response.defer(ephemeral=True)
    chairman_id = str(interaction.user.id)
    
    try:
        with open("team_data.json", "r") as f:
            team_data = json.load(f)
    except Exception:
        await interaction.followup.send("⚠️ Failed to load team data", ephemeral=True)
        return

    team = team_data.get(team_name)
    if not team:
        await interaction.followup.send("❌ Team not found", ephemeral=True)
        return
        
    if team.get("chairman") != chairman_id:
        await interaction.followup.send("🚫 You're not this team's chairman", ephemeral=True)
        return

    try:
        view = SignConfirmationView(player.id, team_name, chairman_id, seasons)
        await player.send(
            embed=nextcord.Embed(
                title=f"⚽ Signing Offer from {team_name}",
                description=(
                    f"**{interaction.user.name}** wants to sign you to **{team_name}** "
                    f"for **{seasons} season(s)**\n\n"
                    "Choose an option:"
                ),
                color=nextcord.Color.gold()
            ),
            view=view
        )
        await interaction.followup.send(f"📨 Offer sent to {player.name}!", ephemeral=True)
    except nextcord.Forbidden:
        await interaction.followup.send("❌ Couldn't DM player", ephemeral=True)

@bot.slash_command(name="forcesign", description="Force-sign a player.")
async def forcesign(
    interaction: Interaction,
    player: nextcord.Member = SlashOption(description="Player to sign"),
    team_name: str = SlashOption(description="Team to join"),
    seasons: int = SlashOption(description="Contract seasons")
):
    # Defer immediately at the start
    await interaction.response.defer(ephemeral=True)
    
    author_roles = [role.id for role in interaction.user.roles]
    if not any(rid in ADMIN_ROLE_IDS + EXEC_ROLE_IDS for rid in author_roles):
        await interaction.followup.send("🚫 Permission denied", ephemeral=True)
        return

    try:
        with open("team_data.json", "r") as f:
            team_data = json.load(f)
    except Exception as e:
        print(f"Error loading team data: {e}")
        await interaction.followup.send("⚠️ Failed to load team data", ephemeral=True)
        return

    if team_name not in team_data:
        await interaction.followup.send("❌ Team not found", ephemeral=True)
        return

    player_id = str(player.id)
    
    # Remove from other teams
    for tname, tdata in team_data.items():
        if player_id in tdata.get("players", {}):
            del tdata["players"][player_id]
        if "roster" in tdata:
            tdata["roster"] = [p for p in tdata["roster"] if p.get("id") != player_id]
    
    # Add to new team
    team = team_data[team_name]
    if "players" not in team:
        team["players"] = {}
    team["players"][player_id] = {"seasons": seasons}
    
    if "roster" not in team:
        team["roster"] = []
    team["roster"].append({
        "id": player_id,
        "seasons": seasons,
        "release_clause": False
    })
    
    # Update player registry
    try:
        with open("registered_players.json", "r") as f:
            reg_players = json.load(f)
    except Exception:
        reg_players = {}
    
    if player_id not in reg_players:
        reg_players[player_id] = {
            "name": player.name,
            "id": player_id,
            "team": team_name,
            "status": "signed",
            "2c": False,
            "rating": "N/A"
        }
    else:
        reg_players[player_id]["team"] = team_name
        reg_players[player_id]["status"] = "signed"
    
    # Save data
    try:
        with open("team_data.json", "w") as f:
            json.dump(team_data, f, indent=4)
        with open("registered_players.json", "w") as f:
            json.dump(reg_players, f, indent=4)
    except Exception as e:
        print(f"Error saving data: {e}")
        await interaction.followup.send("⚠️ Failed to save data", ephemeral=True)
        return
    
    # Update roles with error handling
    try:
        guild = interaction.guild
        role_id = team.get("role_id")
        if role_id:
            role = guild.get_role(role_id)
            if role:
                await player.add_roles(role)
                
        free_agent_role = guild.get_role(FREE_AGENT_ROLE_ID)
        if free_agent_role and free_agent_role in player.roles:
            await player.remove_roles(free_agent_role)
    except Exception as e:
        print(f"Error updating roles: {e}")
        await interaction.followup.send(
            f"✅ {player.mention} force-signed to **{team_name}** but role update failed",
            ephemeral=True
        )
        return
        
    await interaction.followup.send(
        f"✅ {player.mention} force-signed to **{team_name}**",
        ephemeral=True
    )

@bot.slash_command(name="release", description="Release a player from your team.")
async def release(
    interaction: Interaction,
    player: nextcord.Member = SlashOption(description="Player to release"),
    team_name: str = SlashOption(description="Your team"),
    reason: str = SlashOption(description="Release reason")
):
    await interaction.response.defer(ephemeral=True)
    chairman_id = str(interaction.user.id)
    player_id = str(player.id)
    
    try:
        with open("team_data.json", "r") as f:
            team_data = json.load(f)
        with open("registered_players.json", "r") as f:
            reg_players = json.load(f)
    except Exception:
        await interaction.followup.send("💥 Failed to load data", ephemeral=True)
        return

    team = team_data.get(team_name)
    if not team:
        await interaction.followup.send("❌ Team not found", ephemeral=True)
        return
        
    if team.get("chairman") != chairman_id:
        await interaction.followup.send("🚫 You're not this team's chairman", ephemeral=True)
        return
        
    if player_id not in team.get("players", {}):
        await interaction.followup.send("❌ Player not on your team", ephemeral=True)
        return

    # Remove from team
    del team["players"][player_id]
    if "roster" in team:
        team["roster"] = [p for p in team["roster"] if p.get("id") != player_id]
    
    # Update player registry
    if player_id in reg_players:
        reg_players[player_id]["team"] = None
        reg_players[player_id]["status"] = "free_agent"
    
    # Save data
    try:
        with open("team_data.json", "w") as f:
            json.dump(team_data, f, indent=4)
        with open("registered_players.json", "w") as f:
            json.dump(reg_players, f, indent=4)
    except Exception:
        await interaction.followup.send("⚠️ Failed to save data", ephemeral=True)
        return
    
    # Update roles
    guild = interaction.guild
    role_id = team.get("role_id")
    if role_id:
        role = guild.get_role(role_id)
        if role and role in player.roles:
            await player.remove_roles(role)
            
    free_agent_role = guild.get_role(FREE_AGENT_ROLE_ID)
    if free_agent_role and free_agent_role not in player.roles:
        await player.add_roles(free_agent_role)
        
    await interaction.followup.send(f"✅ {player.name} released", ephemeral=True)
    try:
        await player.send(f"🛑 Released from **{team_name}**\n**Reason:** {reason}")
    except Exception:
        pass

@bot.slash_command(name="forcerelease", description="Force-release a player.")
async def forcerelease(
    interaction: Interaction,
    player: nextcord.Member = SlashOption(description="Player to release"),
    team_name: str = SlashOption(description="Team to release from"),
    reason: str = SlashOption(description="Release reason")
):
    await interaction.response.defer(ephemeral=True)
    author_roles = [role.id for role in interaction.user.roles]
    if not any(rid in ADMIN_ROLE_IDS + EXEC_ROLE_IDS for rid in author_roles):
        await interaction.followup.send("🚫 Permission denied", ephemeral=True)
        return

    player_id = str(player.id)
    
    try:
        with open("team_data.json", "r") as f:
            team_data = json.load(f)
        with open("registered_players.json", "r") as f:
            reg_players = json.load(f)
    except Exception:
        await interaction.followup.send("💥 Failed to load data", ephemeral=True)
        return

    team = team_data.get(team_name)
    if not team:
        await interaction.followup.send("❌ Team not found", ephemeral=True)
        return
        
    if player_id not in team.get("players", {}):
        await interaction.followup.send("❌ Player not on this team", ephemeral=True)
        return

    # Remove from team
    del team["players"][player_id]
    if "roster" in team:
        team["roster"] = [p for p in team["roster"] if p.get("id") != player_id]
    
    # Update player registry
    if player_id in reg_players:
        reg_players[player_id]["team"] = None
        reg_players[player_id]["status"] = "free_agent"
    
    # Save data
    try:
        with open("team_data.json", "w") as f:
            json.dump(team_data, f, indent=4)
        with open("registered_players.json", "w") as f:
            json.dump(reg_players, f, indent=4)
    except Exception:
        await interaction.followup.send("⚠️ Failed to save data", ephemeral=True)
        return
    
    # Update roles
    guild = interaction.guild
    role_id = team.get("role_id")
    if role_id:
        role = guild.get_role(role_id)
        if role and role in player.roles:
            await player.remove_roles(role)
            
    free_agent_role = guild.get_role(FREE_AGENT_ROLE_ID)
    if free_agent_role and free_agent_role not in player.roles:
        await player.add_roles(free_agent_role)
        
    await interaction.followup.send(f"✅ {player.mention} force-released", ephemeral=True)
    try:
        await player.send(f"🛑 Force-released from **{team_name}**\n**Reason:** {reason}")
    except Exception:
        pass

@bot.slash_command(name="releaseclauseuse", description="Use your release clause.")
async def releaseclauseuse(interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    player_id = str(interaction.user.id)
    
    try:
        with open("team_data.json", "r") as f:
            team_data = json.load(f)
        with open("registered_players.json", "r") as f:
            reg_players = json.load(f)
    except Exception:
        await interaction.followup.send("💥 Failed to load data", ephemeral=True)
        return

    for team_name, team in team_data.items():
        roster = team.get("roster", [])
        for player in roster:
            if player.get("id") == player_id and player.get("release_clause"):
                # Remove from team
                if player_id in team.get("players", {}):
                    del team["players"][player_id]
                team["roster"] = [p for p in roster if p.get("id") != player_id]
                
                # Update player registry
                if player_id in reg_players:
                    reg_players[player_id]["team"] = None
                    reg_players[player_id]["status"] = "free_agent"
                
                # Save data
                try:
                    with open("team_data.json", "w") as f:
                        json.dump(team_data, f, indent=4)
                    with open("registered_players.json", "w") as f:
                        json.dump(reg_players, f, indent=4)
                except Exception:
                    await interaction.followup.send("⚠️ Failed to save data", ephemeral=True)
                    return
                
                # Update roles
                guild = interaction.guild
                role_id = team.get("role_id")
                if role_id:
                    role = guild.get_role(role_id)
                    if role and role in interaction.user.roles:
                        await interaction.user.remove_roles(role)
                        
                free_agent_role = guild.get_role(FREE_AGENT_ROLE_ID)
                if free_agent_role and free_agent_role not in interaction.user.roles:
                    await interaction.user.add_roles(free_agent_role)
                    
                await interaction.followup.send(
                    f"✅ Used release clause from **{team_name}**",
                    ephemeral=True
                )
                return
                
    await interaction.followup.send("❌ No release clause available", ephemeral=True)

@bot.slash_command(name="updateteamroles", description="Update team roles.")
async def update_team_roles(
    interaction: Interaction,
    team_name: str = SlashOption(required=False, description="Team to update")
):
    await interaction.response.defer(ephemeral=True)
    user_id = str(interaction.user.id)
    
    try:
        with open("team_data.json", "r") as f:
            team_data = json.load(f)
    except Exception:
        await interaction.followup.send("⚠️ Failed to load team data", ephemeral=True)
        return

    # Check permissions
    author_roles = [role.id for role in interaction.user.roles]
    is_exec = any(rid in ADMIN_ROLE_IDS + EXEC_ROLE_IDS for rid in author_roles)
    
    if not is_exec:
        # Find user's team if chairman
        user_team = None
        for tname, tdata in team_data.items():
            if tdata.get("chairman") == user_id:
                user_team = tname
                break
                
        if not user_team:
            await interaction.followup.send("🚫 You're not a chairman", ephemeral=True)
            return
            
        if team_name and team_name != user_team:
            await interaction.followup.send("🚫 Can't update other teams", ephemeral=True)
            return
            
        team_name = user_team

    if not team_name or team_name not in team_data:
        await interaction.followup.send("❌ Team not found", ephemeral=True)
        return

    guild = interaction.guild
    team = team_data[team_name]
    role_id = team.get("role_id")
    if not role_id:
        await interaction.followup.send("⚠️ Team has no role", ephemeral=True)
        return
        
    role = guild.get_role(role_id)
    if not role:
        await interaction.followup.send("⚠️ Role not found", ephemeral=True)
        return

    player_ids = list(team.get("players", {}).keys())
    
    # Remove role from non-players
    for member in role.members:
        if str(member.id) not in player_ids:
            try:
                await member.remove_roles(role)
            except Exception:
                pass
                
    # Add role to players
    for pid in player_ids:
        member = guild.get_member(int(pid))
        if member and role not in member.roles:
            try:
                await member.add_roles(role)
            except Exception:
                pass
                
    await interaction.followup.send(f"✅ Updated roles for **{team_name}**", ephemeral=True)

# TEAM INFO COMMANDS
@bot.slash_command(name="teaminfo", description="Show team information.")
async def teaminfo(
    interaction: Interaction,
    team_name: str = SlashOption(description="Team name")
):
    await interaction.response.defer()
    
    try:
        with open("team_data.json", "r") as f:
            team_data = json.load(f)
    except Exception:
        await interaction.followup.send("💥 Failed to load team data")
        return

    team = team_data.get(team_name)
    if not team:
        await interaction.followup.send("❌ Team not found")
        return

    embed = nextcord.Embed(title=f"📊 {team_name} Info", color=0x1abc9c)
    embed.add_field(name="👑 Chairman", value=f"<@{team.get('chairman')}>" if team.get("chairman") else "None")
    embed.add_field(name="🧠 Assistant", value=f"<@{team.get('assistant_manager')}>" if team.get("assistant_manager") else "None")
    embed.add_field(name="🧢 Manager", value=f"<@{team.get('manager')}>" if team.get("manager") else "None")
    embed.add_field(name="👥 Players", value=str(len(team.get("players", {}))))
    
    await interaction.followup.send(embed=embed)

@bot.slash_command(name="teamrosterdisplay", description="Show team roster.")
async def teamrosterdisplay(
    interaction: Interaction,
    team_name: str = SlashOption(description="Team name")
):
    await interaction.response.defer()
    
    try:
        with open("team_data.json", "r") as f:
            team_data = json.load(f)
    except Exception:
        await interaction.followup.send("💥 Failed to load team data")
        return

    team = team_data.get(team_name)
    if not team:
        await interaction.followup.send("❌ Team not found")
        return

    roster = team.get("roster", [])
    description = ""
    for player in roster:
        pid = player.get("id", "")
        seasons = player.get("seasons", 0)
        rc = player.get("release_clause", False)
        description += f"<@{pid}> | Seasons: {seasons} | RC: {'Yes' if rc else 'No'}\n"
    
    embed = nextcord.Embed(
        title=f"📋 {team_name} Roster",
        description=description or "Empty roster",
        color=0x3498db
    )
    await interaction.followup.send(embed=embed)

# TEAM STAFF MANAGEMENT
@bot.slash_command(name="teamchairmanhire", description="Assign team chairman.")
async def teamchairmanhire(
    interaction: Interaction,
    team_name: str = SlashOption(description="Team name"),
    chairman: nextcord.Member = SlashOption(description="New chairman")
):
    await interaction.response.defer()
    author_roles = [role.id for role in interaction.user.roles]
    if not any(rid in ADMIN_ROLE_IDS + EXEC_ROLE_IDS for rid in author_roles):
        await interaction.followup.send("🚫 Permission denied")
        return

    try:
        with open("team_data.json", "r") as f:
            team_data = json.load(f)
        with open("registered_players.json", "r") as f:
            registered_players = json.load(f)
    except Exception:
        await interaction.followup.send("💥 Failed to load team or player data")
        return

    if team_name not in team_data:
        await interaction.followup.send("❌ Team not found")
        return

    # Set chairman and manager
    chairman_id = str(chairman.id)
    team_data[team_name]["chairman"] = chairman_id
    team_data[team_name]["manager"] = chairman_id

    # Register chairman as a player with infinite seasons
    if chairman_id not in registered_players:
        registered_players[chairman_id] = {
            "name": chairman.name,
            "team": team_name,
            "seasons": "inf"
        }
    else:
        registered_players[chairman_id]["team"] = team_name
        registered_players[chairman_id]["seasons"] = "inf"

    # Add roles to chairman
    chairman_role = interaction.guild.get_role(1372651142789595221)  # Chairman/Manager role
    team_role = interaction.guild.get_role(team_data[team_name]["role_id"])
    
    await chairman.add_roles(chairman_role, team_role)

    # Save changes
    with open("team_data.json", "w") as f:
        json.dump(team_data, f, indent=4)
    with open("registered_players.json", "w") as f:
        json.dump(registered_players, f, indent=4)

    await interaction.followup.send(
        f"✅ {chairman.mention} is now chairman and manager of {team_name}, signed for infinite seasons."
    )


@bot.slash_command(name="teammanagerhire", description="Assign team manager.")
async def teammanagerhire(
    interaction: Interaction,
    manager: nextcord.Member = SlashOption(description="New manager")
):
    await interaction.response.defer()
    user_id = str(interaction.user.id)
    manager_id = str(manager.id)

    try:
        with open("team_data.json", "r") as f:
            team_data = json.load(f)
        with open("registered_players.json", "r") as f:
            registered_players = json.load(f)
    except Exception:
        await interaction.followup.send("💥 Failed to load team or player data")
        return

    user_team = None
    for tname, tdata in team_data.items():
        if tdata.get("chairman") == user_id:
            user_team = tname
            break

    if not user_team:
        await interaction.followup.send("🚫 You're not a chairman")
        return

    # Check if manager is signed to this team
    player_data = registered_players.get(manager_id)
    if not player_data or player_data.get("team") != user_team:
        await interaction.followup.send(f"🚫 {manager.mention} is not signed to {user_team}")
        return

    # Assign manager
    team_data[user_team]["manager"] = manager_id

    # Add manager role
    manager_role = interaction.guild.get_role(1372651142789595221)  # Chairman/Manager role
    await manager.add_roles(manager_role)

    with open("team_data.json", "w") as f:
        json.dump(team_data, f, indent=4)

    await interaction.followup.send(f"✅ {manager.mention} is now manager of {user_team}")


@bot.slash_command(name="assistantmanagerhire", description="Assign assistant manager.")
async def assistantmanagerhire(
    interaction: Interaction,
    assistant: nextcord.Member = SlashOption(description="New assistant")
):
    await interaction.response.defer()
    user_id = str(interaction.user.id)
    assistant_id = str(assistant.id)

    try:
        with open("team_data.json", "r") as f:
            team_data = json.load(f)
        with open("registered_players.json", "r") as f:
            registered_players = json.load(f)
    except Exception:
        await interaction.followup.send("💥 Failed to load team or player data")
        return

    # Find user's team
    user_team = None
    for tname, tdata in team_data.items():
        if tdata.get("chairman") == user_id:
            user_team = tname
            break

    if not user_team:
        await interaction.followup.send("🚫 You're not a chairman")
        return

    # Check if assistant is signed to this team
    player_data = registered_players.get(assistant_id)
    if not player_data or player_data.get("team") != user_team:
        await interaction.followup.send(f"🚫 {assistant.mention} is not signed to {user_team}")
        return

    # Assign assistant manager
    team_data[user_team]["assistant_manager"] = assistant_id

    # Add assistant manager role
    assistant_role = interaction.guild.get_role(1372651142789595220)  # Assistant manager role
    await assistant.add_roles(assistant_role)

    with open("team_data.json", "w") as f:
        json.dump(team_data, f, indent=4)

    await interaction.followup.send(f"✅ {assistant.mention} is now assistant manager of {user_team}")


@bot.slash_command(name="teamchairmanunhire", description="Remove team chairman.")
async def teamchairmanunhire(
    interaction: Interaction,
    team_name: str = SlashOption(description="Team name")
):
    await interaction.response.defer()
    author_roles = [role.id for role in interaction.user.roles]
    if not any(rid in ADMIN_ROLE_IDS + EXEC_ROLE_IDS for rid in author_roles):
        await interaction.followup.send("🚫 Permission denied")
        return

    try:
        with open("team_data.json", "r") as f:
            team_data = json.load(f)
        with open("registered_players.json", "r") as f:
            registered_players = json.load(f)
    except Exception:
        await interaction.followup.send("💥 Failed to load data")
        return

    if team_name not in team_data:
        await interaction.followup.send("❌ Team not found")
        return

    if "chairman" not in team_data[team_name]:
        await interaction.followup.send("ℹ️ No chairman assigned")
        return

    chairman_id = team_data[team_name]["chairman"]
    chairman = interaction.guild.get_member(int(chairman_id))
    
    # Remove roles from chairman
    chairman_role = interaction.guild.get_role(1372651142789595221)  # Chairman/Manager role
    team_role = interaction.guild.get_role(team_data[team_name]["role_id"])
    
    if chairman:
        await chairman.remove_roles(chairman_role, team_role)

    del team_data[team_name]["chairman"]

    # Also release chairman from the team
    if chairman_id in registered_players:
        del registered_players[chairman_id]

    with open("team_data.json", "w") as f:
        json.dump(team_data, f, indent=4)
    with open("registered_players.json", "w") as f:
        json.dump(registered_players, f, indent=4)

    await interaction.followup.send(f"✅ Chairman removed from {team_name} and released as a free agent.")


@bot.slash_command(name="teammanagerunhire", description="Remove team manager.")
async def teammanagerunhire(interaction: Interaction):
    await interaction.response.defer()
    user_id = str(interaction.user.id)

    try:
        with open("team_data.json", "r") as f:
            team_data = json.load(f)
    except Exception:
        await interaction.followup.send("💥 Failed to load team data")
        return

    # Find user's team
    user_team = None
    for tname, tdata in team_data.items():
        if tdata.get("chairman") == user_id:
            user_team = tname
            break

    if not user_team:
        await interaction.followup.send("🚫 You're not a chairman")
        return

    if "manager" not in team_data[user_team]:
        await interaction.followup.send("ℹ️ No manager assigned")
        return

    manager_id = team_data[user_team]["manager"]
    manager = interaction.guild.get_member(int(manager_id))
    
    # Remove manager role
    manager_role = interaction.guild.get_role(1372651142789595221)  # Chairman/Manager role
    if manager:
        await manager.remove_roles(manager_role)

    del team_data[user_team]["manager"]

    with open("team_data.json", "w") as f:
        json.dump(team_data, f, indent=4)

    await interaction.followup.send(f"✅ Manager demoted from {user_team}, still signed to team.")


@bot.slash_command(name="assistantmanagerunhire", description="Remove assistant manager.")
async def assistantmanagerunhire(interaction: Interaction):
    await interaction.response.defer()
    user_id = str(interaction.user.id)

    try:
        with open("team_data.json", "r") as f:
            team_data = json.load(f)
    except Exception:
        await interaction.followup.send("💥 Failed to load team data")
        return

    # Find user's team
    user_team = None
    for tname, tdata in team_data.items():
        if tdata.get("chairman") == user_id:
            user_team = tname
            break

    if not user_team:
        await interaction.followup.send("🚫 You're not a chairman")
        return

    if "assistant_manager" not in team_data[user_team]:
        await interaction.followup.send("ℹ️ No assistant manager assigned")
        return

    assistant_id = team_data[user_team]["assistant_manager"]
    assistant = interaction.guild.get_member(int(assistant_id))
    
    # Remove assistant manager role
    assistant_role = interaction.guild.get_role(1372651142789595220)  # Assistant manager role
    if assistant:
        await assistant.remove_roles(assistant_role)

    del team_data[user_team]["assistant_manager"]

    with open("team_data.json", "w") as f:
        json.dump(team_data, f, indent=4)

    await interaction.followup.send(f"✅ Assistant manager demoted from {user_team}, still signed to team.")


bot.run('')