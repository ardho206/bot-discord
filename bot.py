import os
import sys
import base64
import json
import random
import string
import asyncio
import datetime
from urllib.parse import quote
import discord
from discord.ui import Button, View, Modal, TextInput
from discord import app_commands
import aiohttp
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = os.getenv("GITHUB_REPO", "DyyITT/SansMobaHub")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
FILE_PATH = os.getenv("FILE_PATH", "CHECK PREM USERNAME")
BRANCH = os.getenv("BRANCH", "main")
LOCAL_JSON = "users.json"
GUILD_ID = 1360567703709941782
ALLOWED_USERS = [938692894410297414, 1154602289097617450]

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
API_BASE = "https://api.github.com"

# ---------- JSON load ----------
def load_json(filename):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return json.load(f)
    return {}

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

LOCAL_JSON = "users.json"
KEYS_JSON = "keys.json"

users = load_json(LOCAL_JSON)
keys = load_json(KEYS_JSON)

# ---------- Embed builder ----------
def make_embed(title, desc, color=0xA64DFF):
    return discord.Embed(title=title, description=desc, color=color)

def error_embed(msg):
    return make_embed("Error", f"⚠️ {msg}", color=0xFF0000)

def success_embed(msg):
    return make_embed("Sukses", f"✅ {msg}", color=0x00FF00)

# ---------- Github helper ----------
async def fetch_file(session, repo, path, branch):
    path_enc = quote(path)
    url = f"{API_BASE}/repos/{repo}/contents/{path_enc}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    params = {"ref": branch}
    async with session.get(url, headers=headers, params=params) as r:
        if r.status != 200:
            return None, r.status, await r.text()
        return await r.json(), r.status, None

async def update_file(session, repo, path, branch, new_content, sha, message):
    path_enc = quote(path)
    url = f"{API_BASE}/repos/{repo}/contents/{path_enc}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    payload = {
        "message": message,
        "content": base64.b64encode(new_content.encode()).decode(),
        "branch": branch,
        "sha": sha
    }
    async with session.put(url, headers=headers, data=json.dumps(payload)) as r:
        return r.status, await r.text()

# ---------- Modal ----------
class UsernameModal(Modal):
    def __init__(self, key_slot=None):
        super().__init__(title="Masukkan Username + Key")
        self.key_slot = key_slot
        self.username_input = TextInput(label="Username Roblox", placeholder="Masukkan Username...")
        self.key_input = TextInput(label="Key", placeholder="Masukkan Key...") if key_slot is None else None
        self.add_item(self.username_input)
        if self.key_input:
            self.add_item(self.key_input)

    async def on_submit(self, interaction: discord.Interaction):
        username = self.username_input.value.strip()
        key = self.key_input.value.strip() if self.key_input else self.key_slot
        uid = str(interaction.user.id)

        if not username or not key:
            await interaction.response.send_message(embed=error_embed("Username atau Key kosong!"), ephemeral=True)
            return

        if key not in keys:
            await interaction.response.send_message(embed=error_embed("Key tidak valid!"), ephemeral=True)
            return

        used_list = keys[key].setdefault("used", [])
        total_slots = keys[key].get("slots", 0)

        if username in used_list:
            await interaction.response.send_message(embed=error_embed(f"Username `{username}` sudah terdaftar!"), ephemeral=True)
            return

        if len(used_list) >= total_slots:
            await interaction.response.send_message(embed=error_embed("Slot key habis!"), ephemeral=True)
            return

        async with aiohttp.ClientSession() as session:
            file_data, status, err_text = await fetch_file(session, REPO, FILE_PATH, BRANCH)
            if file_data is None:
                print("github fetch failed:", status, err_text)
                await interaction.response.send_message(embed=error_embed("Gagal ambil data dari GitHub!"), ephemeral=True)
                return

            sha = file_data["sha"]
            old_content = base64.b64decode(file_data.get("content", "")).decode() if file_data.get("content") else ""
            lines = [line.strip() for line in old_content.splitlines() if line.strip()]

            if username in lines:
                await interaction.response.send_message(embed=error_embed(f"Username `{username}` sudah ada di premium!"), ephemeral=True)
                return

            new_content = old_content + ("\n" if old_content and not old_content.endswith("\n") else "") + username
            status_update, resp_text = await update_file(session, REPO, FILE_PATH, BRANCH, new_content, sha, f"add {username}")
            if status_update not in (200, 201):
                print("github update failed:", status_update, resp_text)
                await interaction.response.send_message(embed=error_embed("Gagal update GitHub!"), ephemeral=True)
                return

        users[uid] = users.get(uid, {"usernames": [], "key": key})
        users[uid]["usernames"].append(username)
        with open(LOCAL_JSON, "w") as f:
            json.dump(users, f, indent=2)

        used_list.append(username)
        save_json(KEYS_JSON, keys)
        await interaction.response.send_message(embed=success_embed(f"Username `{username}` ditambah! Sisa slot: {total_slots - len(used_list)}"), ephemeral=True)

class EditUsernameModal(Modal):
    def __init__(self, key, old_username):
        super().__init__(title=f"Edit Username ({old_username})")
        self.key = key
        self.old_username = old_username
        self.new_username = TextInput(label="Username Baru", placeholder="username baru...")
        self.add_item(self.new_username)

    async def on_submit(self, interaction: discord.Interaction):
        new_username = self.new_username.value.strip()
        if not new_username:
            await interaction.response.send_message(embed=error_embed("Username tidak boleh kosong!"), ephemeral=True)
            return

        key_data = keys.get(self.key)
        if not key_data:
            await interaction.response.send_message(embed=error_embed("Key tidak ditemukan!"), ephemeral=True)
            return

        used_list = key_data.get("used", [])
        if new_username in used_list:
            await interaction.response.send_message(embed=error_embed("Username sudah digunakan!"), ephemeral=True)
            return

        async with aiohttp.ClientSession() as session:
            file_data, status, err_text = await fetch_file(session, REPO, FILE_PATH, BRANCH)
            if file_data is None:
                print("github fetch failed:", status, err_text)
                await interaction.response.send_message(embed=error_embed("Gagal ambil data dari GitHub!"), ephemeral=True)
                return

            sha = file_data["sha"]
            old_content = base64.b64decode(file_data.get("content", "")).decode() if file_data.get("content") else ""
            lines = [line.strip() for line in old_content.splitlines() if line.strip()]

            if self.old_username not in lines:
                await interaction.response.send_message(embed=error_embed("Username lama tidak ditemukan di file!"), ephemeral=True)
                return

            lines[lines.index(self.old_username)] = new_username
            new_content = "\n".join(lines)
            status_update, resp_text = await update_file(session, REPO, FILE_PATH, BRANCH, new_content, sha, f"edit {self.old_username} -> {new_username}")
            if status_update not in (200, 201):
                print("github update failed:", status_update, resp_text)
                await interaction.response.send_message(embed=error_embed("Gagal update GitHub!"), ephemeral=True)
                return

        # update di keys.json
        used_list[used_list.index(self.old_username)] = new_username
        save_json(KEYS_JSON, keys)

        # update di users.json
        uid = str(interaction.user.id)
        if uid in users and self.old_username in users[uid]["usernames"]:
            users[uid]["usernames"][users[uid]["usernames"].index(self.old_username)] = new_username
            save_json(LOCAL_JSON, users)

        await interaction.response.send_message(embed=success_embed(f"Username `{self.old_username}` diubah ke `{new_username}`!\n**Mohon tunggu 1-5 menit untuk verifikasi username baru**\n**Jika sudah menunggu silahkan menggunakan script dengan username `{new_username}`**"), ephemeral=True)

# ---------- Manage ----------
async def manage_callback(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    if uid not in users:
        await interaction.response.send_message(embed=error_embed("Kamu belum menambahkan username premium!"), ephemeral=True)
        return

    key = users[uid]["key"]
    used_list = keys[key].get("used", [])
    total_slots = keys[key].get("slots", 0)
    remaining_slots = total_slots - len(used_list)
    user_lines = "\n".join(f"{i+1}. {u}" for i, u in enumerate(used_list)) or " - "

    embed_manage = make_embed(
        "Manage Akun Premium",
        f"✅ Username Roblox:\n{user_lines}\n\n🔑 Key: `{key}`\n⭐ Sisa slot: {remaining_slots}\n\nPilih username buat diedit:"
    )

    options = [discord.SelectOption(label=u, description=f"Edit username {u}") for u in used_list]
    select = discord.ui.Select(placeholder="Pilih username", options=options, min_values=1, max_values=1)
    view = View(timeout=None)

    async def select_callback(inter: discord.Interaction):
        selected = inter.data["values"][0]
        await inter.response.send_modal(EditUsernameModal(key, selected))

    select.callback = select_callback
    view.add_item(select)

    await interaction.response.send_message(embed=embed_manage, view=view, ephemeral=True)

# ---------- Slash Commands ----------
@tree.command(name="generate-key", description="Generate key premium", guild=discord.Object(id=GUILD_ID))
async def generate_key(interaction: discord.Interaction, slots: int):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message(embed=error_embed("Kamu tidak punya akses!"), ephemeral=True)
        print(f"Unauthorized key generation attempt by @{interaction.user.id}")
        return

    key = f"SansPrem_{''.join(random.choices(string.ascii_letters + string.digits, k=20))}"
    keys[key] = {"slots": slots, "used": []}
    save_json(KEYS_JSON, keys)

    embed_key = discord.Embed(title="Key Generated", color=0xA64DFF)
    embed_key.add_field(name="Key: ", value=f"{key}", inline=False)
    embed_key.add_field(name="Slots: ", value=f"{slots}", inline=False)
    embed_key.add_field(name="Admin: ", value=f"<@{interaction.user.id}>", inline=False)
    embed_key.add_field(name="Click to copy the key", value=f"```{key}```", inline=False)
    await interaction.response.send_message(embed=embed_key, ephemeral=True)
    print(f"Generated key: {key} by user @{interaction.user.id}")

# ---------- Message UI ----------
async def message_bot(channel):
    view = View(timeout=None)
    button_account = Button(label="Account Info", style=discord.ButtonStyle.secondary, emoji="ℹ️")
    button_premium = Button(label="Premium Info", style=discord.ButtonStyle.primary, emoji="⭐")
    button_manage = Button(label="Manage Accounts", style=discord.ButtonStyle.danger, emoji="🛠️")

    async def account_callback(interaction):
        uid = str(interaction.user.id)
        if uid not in users:
            await interaction.response.send_modal(UsernameModal())
            return

        data_user = users[uid]
        key = data_user["key"]
        key_data = keys.get(key, {"slots": 0, "used": []})
        used_list = key_data["used"]
        total_slots = key_data["slots"]
        remaining_slots = total_slots - len(used_list)
        user_lines = "\n".join(f"{i+1}. {u}" for i, u in enumerate(used_list)) or " - "

        embed = make_embed(
            "Info Akun Premium",
            f"✅ Username Roblox:\n{user_lines}\n\n🔑 Key: `{key}`\n⭐ Sisa slot: {remaining_slots}"
        )
        view2 = View()
        if remaining_slots > 0:
            add_btn = Button(label="Add Account", style=discord.ButtonStyle.success, emoji="➕")
            add_btn.callback = lambda inter: inter.response.send_modal(UsernameModal(key_slot=key))
            view2.add_item(add_btn)

        await interaction.response.send_message(embed=embed, ephemeral=True, view=view2)

    async def premium_callback(interaction):
        embed = make_embed(
            "Info Premium SansMoba",
            "⭐ Instant fish X5\n🕘 Script tanpa limit\n🔗 Webhook discord\n🎁 Dan masih banyak lagi!"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    button_account.callback = account_callback
    button_premium.callback = premium_callback
    button_manage.callback = manage_callback

    view.add_item(button_account)
    view.add_item(button_premium)
    view.add_item(button_manage)

    embed_main = make_embed(
        "SansMoba Premium",
        "• Klik **Account Info** buat tambah username premium\n• Klik **Premium Info** buat liat fitur\n• Klik **Manage Accounts** buat edit username"
    )
    embed_main.set_footer(text="Pastikan username roblox benar (format: @username)")
    await channel.send(embed=embed_main, view=view)

# ---------- on_ready ----------
@client.event
async def on_ready():
    print(f"Bot ready for {client.user}")
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print("Commands synced")
    channel = client.get_channel(CHANNEL_ID)
    if channel:
        client.loop.create_task(message_bot(channel))

if __name__ == "__main__":
    if not DISCORD_TOKEN or not GITHUB_TOKEN:
        print("Missing DISCORD_TOKEN or GITHUB_TOKEN")
        sys.exit(1)
    client.run(DISCORD_TOKEN)
