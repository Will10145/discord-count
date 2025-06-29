import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import os
import sqlite3
import aiosqlite
from typing import Optional

load_dotenv()

TOKEN = os.getenv('TOKEN')
DB_PATH = os.getenv('DB_PATH', 'counting_bot.db')

# Create bot with intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

class AppCommandHelper:
    """Helper class to easily add app commands to the bot"""
    
    def __init__(self, bot):
        self.bot = bot
    
    def add_simple_command(self, name: str, description: str, callback):
        """
        Add a simple slash command with no parameters
        
        Args:
            name: Command name
            description: Command description
            callback: Function to call when command is used
        """
        @app_commands.command(name=name, description=description)
        async def command_wrapper(interaction: discord.Interaction):
            await callback(interaction)
        
        self.bot.tree.add_command(command_wrapper)
        return command_wrapper
    
    def add_command_with_string(self, name: str, description: str, param_name: str, param_description: str, callback):
        """
        Add a slash command with one string parameter
        
        Args:
            name: Command name
            description: Command description
            param_name: Parameter name
            param_description: Parameter description
            callback: Function to call when command is used (takes interaction and string param)
        """
        # Create a properly typed wrapper function
        async def command_wrapper(interaction: discord.Interaction, text_param: str):
            await callback(interaction, text_param)
        
        # Set the parameter name and description
        command_wrapper.__name__ = f"{name}_command"
        command_wrapper = app_commands.command(name=name, description=description)(command_wrapper)
        command_wrapper = app_commands.describe(text_param=param_description)(command_wrapper)
        
        self.bot.tree.add_command(command_wrapper)
        return command_wrapper
    
    def add_command_with_user(self, name: str, description: str, param_name: str, param_description: str, callback):
        """
        Add a slash command with one user parameter
        
        Args:
            name: Command name
            description: Command description
            param_name: Parameter name
            param_description: Parameter description
            callback: Function to call when command is used (takes interaction and user param)
        """
        # Create a properly typed wrapper function
        async def command_wrapper(interaction: discord.Interaction, user_param: discord.Member):
            await callback(interaction, user_param)
        
        # Set the parameter name and description
        command_wrapper.__name__ = f"{name}_command"
        command_wrapper = app_commands.command(name=name, description=description)(command_wrapper)
        command_wrapper = app_commands.describe(user_param=param_description)(command_wrapper)
        
        self.bot.tree.add_command(command_wrapper)
        return command_wrapper
    
    def add_command_with_channel(self, name: str, description: str, param_name: str, param_description: str, callback):
        """
        Add a slash command with one channel parameter
        
        Args:
            name: Command name
            description: Command description
            param_name: Parameter name
            param_description: Parameter description
            callback: Function to call when command is used (takes interaction and channel param)
        """
        # Create a properly typed wrapper function
        async def command_wrapper(interaction: discord.Interaction, channel_param: discord.TextChannel):
            await callback(interaction, channel_param)
        
        # Set the parameter name and description
        command_wrapper.__name__ = f"{name}_command"
        command_wrapper = app_commands.command(name=name, description=description)(command_wrapper)
        command_wrapper = app_commands.describe(channel_param=param_description)(command_wrapper)
        
        self.bot.tree.add_command(command_wrapper)
        return command_wrapper
    
    def add_admin_command_with_channel(self, name: str, description: str, param_name: str, param_description: str, callback):
        """
        Add a slash command with one channel parameter (admin only)
        
        Args:
            name: Command name
            description: Command description
            param_name: Parameter name
            param_description: Parameter description
            callback: Function to call when command is used (takes interaction and channel param)
        """
        # Create a properly typed wrapper function
        async def command_wrapper(interaction: discord.Interaction, channel_param: discord.TextChannel):
            # Check if user has administrator permissions
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("❌ You need administrator permissions to use this command!", ephemeral=True)
                return
            await callback(interaction, channel_param)
        
        # Set the parameter name and description
        command_wrapper.__name__ = f"{name}_command"
        command_wrapper = app_commands.command(name=name, description=description)(command_wrapper)
        command_wrapper = app_commands.describe(channel_param=param_description)(command_wrapper)
        
        self.bot.tree.add_command(command_wrapper)
        return command_wrapper

# Initialize the helper
command_helper = AppCommandHelper(bot)

# Global variable to store count channel info
count_channels = {}  # Format: {guild_id: {"channel_id": int, "webhook": webhook_object}}

# Global variable to store server-specific count numbers
server_counts = {}  # Format: {guild_id: current_number}

# Global variable to store the last user who counted in each server
last_counter = {}  # Format: {guild_id: user_id}

# Database functions
async def init_database():
    """Initialize the SQLite database and create tables if they don't exist"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Create counting_channels table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS counting_channels (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    webhook_url TEXT NOT NULL,
                    current_count INTEGER DEFAULT 0,
                    last_counter_id INTEGER DEFAULT NULL
                )
            ''')
            
            # Create counting_history table (optional for statistics)
            await db.execute('''
                CREATE TABLE IF NOT EXISTS counting_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    count_number INTEGER NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (guild_id) REFERENCES counting_channels (guild_id)
                )
            ''')
            
            await db.commit()
            print("📊 Database initialized successfully")
    except Exception as e:
        print(f"❌ Database initialization error: {e}")

async def save_counting_channel(guild_id: int, channel_id: int, webhook_url: str):
    """Save counting channel configuration to database"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('''
                INSERT OR REPLACE INTO counting_channels 
                (guild_id, channel_id, webhook_url, current_count, last_counter_id)
                VALUES (?, ?, ?, 0, NULL)
            ''', (guild_id, channel_id, webhook_url))
            await db.commit()
            print(f"💾 Saved counting channel for guild {guild_id}")
    except Exception as e:
        print(f"❌ Error saving counting channel: {e}")

async def load_counting_data():
    """Load all counting data from database into memory"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute('SELECT * FROM counting_channels')
            rows = await cursor.fetchall()
            
            for row in rows:
                guild_id, channel_id, webhook_url, current_count, last_counter_id = row
                
                # Recreate webhook object from URL
                try:
                    webhook = discord.Webhook.from_url(webhook_url, session=bot.http._HTTPClient__session)
                    count_channels[guild_id] = {
                        "channel_id": channel_id,
                        "webhook": webhook
                    }
                    server_counts[guild_id] = current_count
                    if last_counter_id:
                        last_counter[guild_id] = last_counter_id
                    
                    print(f"📥 Loaded counting data for guild {guild_id} (count: {current_count})")
                except Exception as webhook_error:
                    print(f"❌ Error recreating webhook for guild {guild_id}: {webhook_error}")
                    
    except Exception as e:
        print(f"❌ Error loading counting data: {e}")

async def update_count_in_db(guild_id: int, count: int, user_id: int = None):
    """Update the current count and last counter in database"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('''
                UPDATE counting_channels 
                SET current_count = ?, last_counter_id = ?
                WHERE guild_id = ?
            ''', (count, user_id, guild_id))
            
            # Also save to history
            if user_id:
                await db.execute('''
                    INSERT INTO counting_history (guild_id, user_id, count_number)
                    VALUES (?, ?, ?)
                ''', (guild_id, user_id, count))
            
            await db.commit()
    except Exception as e:
        print(f"❌ Error updating count in database: {e}")

async def delete_counting_channel_from_db(guild_id: int):
    """Delete counting channel configuration from database"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('DELETE FROM counting_channels WHERE guild_id = ?', (guild_id,))
            await db.commit()
            print(f"🗑️ Deleted counting channel data for guild {guild_id}")
    except Exception as e:
        print(f"❌ Error deleting counting channel: {e}")

@bot.event
async def setup_hook():
    """Called when the bot is starting up - perfect for async initialization"""
    print("🔧 Setting up bot...")
    
    # Initialize database
    await init_database()
    
    # Load existing counting data from database
    await load_counting_data()
    
    print("✅ Bot setup complete!")

@bot.event
async def setup_hook():
    """This function is called when the bot is starting up"""
    print("🔧 Setting up bot...")
    
    # Initialize database
    await init_database()
    
    # Load existing counting data from database
    await load_counting_data()
    
    print("✅ Bot setup complete!")

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is in {len(bot.guilds)} guilds')
    
    # Set bot status to Do Not Disturb and activity to "Playing Counting"
    activity = discord.Game(name="Counting")
    await bot.change_presence(status=discord.Status.dnd, activity=activity)
    print(f'📱 Status set to Do Not Disturb - Playing Counting')
    
    # Sync commands globally (this might take up to an hour to appear)
    # For faster testing, you can sync to a specific guild instead
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} command(s)')
    except Exception as e:
        print(f'Failed to sync commands: {e}')

# Example usage of the helper functions:

# Simple command with no parameters
async def ping(interaction):
    await interaction.response.send_message("Pong 🏓", ephemeral=True)

command_helper.add_simple_command("ping", "Test whether the bot is online!", ping)

# Add bot to server command
async def add_command(interaction):
    embed = discord.Embed(
        title="🤖 Add Counting Bot to Your Server",
        description="Click the link below to invite the bot to your server!",
        color=0x00ff00
    )
    
    # You'll need to replace this with your actual bot's client ID
    bot_id = bot.user.id if bot.user else "YOUR_BOT_ID_HERE"
    permissions = "274877975552"  # Manage Messages, Manage Webhooks, Send Messages, Add Reactions, Pin Messages
    
    invite_url = f"https://discord.com/oauth2/authorize?client_id={bot_id}&permissions={permissions}&integration_type=0&scope=bot+applications.commands"
    
    embed.add_field(
        name="Invite Link",
        value=f"[Click here to add the bot]({invite_url})",
        inline=False
    )
    
    embed.add_field(
        name="Required Permissions",
        value="• Send Messages\n• Manage Messages\n• Manage Webhooks\n• Add Reactions\n• Pin Messages",
        inline=False
    )
    
    embed.set_footer(text="The bot needs these permissions to function properly!")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

command_helper.add_simple_command("add", "Get the bot invite link to add it to your server", add_command)






# Admin command to set count channel with webhook
async def set_count_channel_command(interaction, channel):
    try:
        # Check if bot has permission to manage webhooks in the channel
        bot_member = interaction.guild.get_member(bot.user.id)
        if not channel.permissions_for(bot_member).manage_webhooks:
            await interaction.response.send_message(
                f"❌ I don't have permission to manage webhooks in {channel.mention}!\n"
                "Please give me 'Manage Webhooks' permission in that channel.",
                ephemeral=True
            )
            return

        # Create webhook for the count channel
        webhook_name = f"Counting bot"
        
        # Check if webhook already exists
        existing_webhooks = await channel.webhooks()
        count_webhook = None
        
        for webhook in existing_webhooks:
            if webhook.name == webhook_name and webhook.user == bot.user:
                count_webhook = webhook
                break
        
        # Create new webhook if none exists
        if not count_webhook:
            count_webhook = await channel.create_webhook(
                name=webhook_name,
                avatar=await bot.user.avatar.read() if bot.user.avatar else None,
                reason=f"Count channel webhook created by {interaction.user}"
            )
        
        # Store the count channel and webhook info
        count_channels[interaction.guild.id] = {
            "channel_id": channel.id,
            "webhook": count_webhook
        }
        
        # Initialize server count to 0 if not already set
        if interaction.guild.id not in server_counts:
            server_counts[interaction.guild.id] = 0
            
        # Reset last counter when setting up new channel
        if interaction.guild.id in last_counter:
            del last_counter[interaction.guild.id]
        
        # Save to database
        await save_counting_channel(interaction.guild.id, channel.id, count_webhook.url)
        
        embed = discord.Embed(
            title="✅ Count Channel Set Successfully!",
            description=f"Count channel has been set to {channel.mention}",
            color=0x00ff00
        )
        embed.add_field(name="Channel", value=channel.mention, inline=True)
        embed.add_field(name="Webhook", value=f"✅ Created webhook: `{webhook_name}`", inline=True)
        embed.add_field(name="Webhook ID", value=count_webhook.id, inline=False)
        embed.set_footer(text=f"Set by {interaction.user.display_name}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Send a welcome message through the webhook and pin it
        welcome_message = await count_webhook.send(
            content="🔢 **Welcome to the counting channel!** 🔢\n\nStart counting from **1** and keep going! Each message must be the next number in sequence.\n\n✅ **Rules:**\n• Only numbers allowed\n• Must count in order (1, 2, 3...)\n• Wrong numbers will be deleted\n• Same user can't count twice in a row\n\nLet's count together! 🚀",
            username='Counting Bot',
            avatar_url=bot.user.avatar.url if bot.user.avatar else None,
            wait=True
        )
        
        # Pin the welcome message
        try:
            await welcome_message.pin()
            print(f"📌 Pinned welcome message in {channel.name}")
        except discord.Forbidden:
            print(f"❌ Failed to pin message - missing permissions in {channel.name}")
        except Exception as e:
            print(f"❌ Error pinning message: {e}")
        
        # Save to database
        await save_counting_channel(interaction.guild.id, channel.id, count_webhook.url)
        
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I don't have permission to create webhooks in this server!",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"❌ An error occurred while setting up the count channel: {str(e)}",
            ephemeral=True
        )

command_helper.add_admin_command_with_channel(
    "setcountchannel", 
    "Set a channel for counting (Admin only)", 
    "channel", 
    "The channel to use for counting", 
    set_count_channel_command
)

# Command to check current count channel status
async def count_status_command(interaction):
    if interaction.guild.id not in count_channels:
        await interaction.response.send_message(
            "❌ No counting channel has been set for this server.\nUse `/setcountchannel` to set one up!",
            ephemeral=True
        )
        return
    
    count_data = count_channels[interaction.guild.id]
    channel = bot.get_channel(count_data["channel_id"])
    
    if not channel:
        await interaction.response.send_message(
            "❌ The counting channel seems to have been deleted.\nUse `/setcountchannel` to set a new one!",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title="📊 Count Channel Status",
        description="Current counting channel configuration",
        color=0x0099ff
    )
    embed.add_field(name="Channel", value=channel.mention, inline=True)
    embed.add_field(name="Status", value="✅ Active", inline=True)
    embed.add_field(name="Auto-Delete", value="✅ Enabled", inline=True)
    embed.add_field(name="Current Number", value=f"**{server_counts.get(interaction.guild.id, 0)}**", inline=True)
    embed.add_field(name="Webhook ID", value=count_data["webhook"].id, inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

command_helper.add_simple_command("countstatus", "Check the current counting channel status", count_status_command)

@bot.event
async def on_message(message):
    # Ignore bot messages
    if message.author.bot:
        return
    
    # Check if message is in a counting channel
    if message.guild and message.guild.id in count_channels:
        count_channel_data = count_channels[message.guild.id]
        
        # If message is in the counting channel, validate the count
        if message.channel.id == count_channel_data["channel_id"]:
            current_count = server_counts.get(message.guild.id, 0)
            expected_number = current_count + 1
            last_user = last_counter.get(message.guild.id)
            
            try:
                # Try to parse the message as a number
                user_number = int(message.content.strip())
                
                # Check if it's the correct next number
                if user_number == expected_number:
                    # Check if the same user is trying to count again
                    if last_user == message.author.id and current_count > 0:
                        # Same user trying to count twice in a row - delete message
                        await message.delete()
                        print(f"❌ Same user counting twice: {message.author} tried {user_number}")
                        return
                    
                    # Add tick reaction before deleting
                    try:
                        await message.add_reaction("✅")
                    except:
                        pass  # Ignore reaction errors
                    
                    # Correct number! Update the count and send through webhook
                    server_counts[message.guild.id] = user_number
                    last_counter[message.guild.id] = message.author.id
                    
                    # Save to database
                    await update_count_in_db(message.guild.id, user_number, message.author.id)
                    
                    # Delete the original message
                    await message.delete()
                    
                    # Send the count through the webhook
                    webhook = count_channel_data["webhook"]
                    await webhook.send(
                        content=f"**{user_number}**",
                        username=message.author.display_name,
                        avatar_url=message.author.avatar.url if message.author.avatar else message.author.default_avatar.url
                    )
                    
                    # Update the count in database
                    await update_count_in_db(message.guild.id, user_number, message.author.id)
                    
                    print(f"✅ Correct count from {message.author}: {user_number}")
                else:
                    # Wrong number! Delete the message
                    await message.delete()
                    print(f"❌ Wrong count from {message.author}: {user_number} (expected {expected_number})")
                    
            except ValueError:
                # Not a number! Delete the message
                await message.delete()
                print(f"❌ Non-number message from {message.author}: {message.content}")
                
            except discord.Forbidden:
                print(f"Failed to delete message in counting channel - missing permissions")
            except discord.NotFound:
                print(f"Message was already deleted")
            except Exception as e:
                print(f"Error processing counting message: {e}")
    
    # Process commands (important for prefix commands if you add any)
    await bot.process_commands(message)

# Admin command to set the current count number
async def set_count_command(interaction, number):
    # Check if user has administrator permissions
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to use this command!", ephemeral=True)
        return
    
    if interaction.guild.id not in count_channels:
        await interaction.response.send_message(
            "❌ No counting channel has been set for this server.\nUse `/setcountchannel` to set one up first!",
            ephemeral=True
        )
        return
    
    # Validate number
    try:
        count_number = int(number)
        if count_number < 0:
            await interaction.response.send_message("❌ Count number must be 0 or greater!", ephemeral=True)
            return
    except ValueError:
        await interaction.response.send_message("❌ Please provide a valid number!", ephemeral=True)
        return
    
    # Set the server count
    server_counts[interaction.guild.id] = count_number
    
    # Reset the last counter when manually setting count
    if interaction.guild.id in last_counter:
        del last_counter[interaction.guild.id]
    
    # Save to database
    await update_count_in_db(interaction.guild.id, count_number, None)
    
    embed = discord.Embed(
        title="✅ Count Number Updated!",
        description=f"The current count has been set to **{count_number}**",
        color=0x00ff00
    )
    embed.set_footer(text=f"Updated by {interaction.user.display_name}")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

command_helper.add_command_with_string("setcount", "Set the current count number (Admin only)", "number", "The number to set the count to", set_count_command)

# Admin command to reset the count to 0
async def reset_count_command(interaction):
    # Check if user has administrator permissions
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to use this command!", ephemeral=True)
        return
    
    if interaction.guild.id not in count_channels:
        await interaction.response.send_message(
            "❌ No counting channel has been set for this server.\nUse `/setcountchannel` to set one up first!",
            ephemeral=True
        )
        return
    
    # Reset the server count to 0
    server_counts[interaction.guild.id] = 0
    
    # Reset the last counter
    if interaction.guild.id in last_counter:
        del last_counter[interaction.guild.id]
    
    # Save to database
    await update_count_in_db(interaction.guild.id, 0, None)
    
    embed = discord.Embed(
        title="🔄 Count Reset!",
        description="The count has been reset to **0**",
        color=0xff9900
    )
    embed.set_footer(text=f"Reset by {interaction.user.display_name}")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

command_helper.add_simple_command("resetcount", "Reset the count to 0 (Admin only)", reset_count_command)

# Command to get the current count (anyone can use)
async def get_count_command(interaction):
    if interaction.guild.id not in count_channels:
        await interaction.response.send_message(
            "❌ No counting channel has been set for this server.\nUse `/setcountchannel` to set one up first!",
            ephemeral=True
        )
        return
    
    current_count = server_counts.get(interaction.guild.id, 0)
    
    embed = discord.Embed(
        title="🔢 Current Count",
        description=f"The current count is **{current_count}**",
        color=0x0099ff
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

command_helper.add_simple_command("getcount", "Get the current count number", get_count_command)

async def remove_count_channel_command(interaction, channel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to use this command!", ephemeral=True)
        return
    
    if interaction.guild.id not in count_channels:
        await interaction.response.send_message(
            "❌ No counting channel has been set for this server.",
            ephemeral=True
        )
        return
    

    if interaction.guild.id in count_channels:
        del count_channels[interaction.guild.id]
    if interaction.guild.id in server_counts:
        del server_counts[interaction.guild.id]
    if interaction.guild.id in last_counter:
        del last_counter[interaction.guild.id]
    

    await delete_counting_channel_from_db(interaction.guild.id)
    
    embed = discord.Embed(
        title="🗑️ Count Channel Removed!",
        description="The counting channel has been removed from this server.",
        color=0xff4444
    )
    embed.set_footer(text=f"Removed by {interaction.user.display_name}")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

command_helper.add_admin_command_with_channel("removecountchannel", "Remove the counting channel (Admin only)", "channel", "Any channel (parameter ignored)", remove_count_channel_command)

if __name__ == "__main__":
    bot.run(TOKEN)
