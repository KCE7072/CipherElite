# =============================================================================
#  CipherElite Plugin - mute_all.py (Fixed to prevent FloodWait)
#  Instantly mutes/unmutes all group chats via Telegram Folders (Bulk API)
# =============================================================================

from telethon import events
from utils.utils import CipherElite
from utils.decorators import rishabh
from plugins.bot import add_handler
from telethon.tl import functions, types
import asyncio

VERSION = "2.0.0"
CATEGORY = "utilities"

async def _is_owner(event):
    try:
        me = await CipherElite.get_me()
        return event.sender_id == me.id
    except Exception:
        return False

def init(client_instance):
    commands = [
        ".muteall - mute all groups",
        ".unmuteall - unmute all groups",
    ]
    add_handler("mute_all", commands, "🔕 Instantly mute/unmute ALL group chats")


@CipherElite.on(events.NewMessage(pattern=r"\.muteall$"))
@rishabh()
async def cmd_mute_all(event):
    if not await _is_owner(event):
        return
    try:
        msg = await event.reply("⏳ Applying bulk mute to all groups...")
        
        # 1. Create/Update a hidden folder that contains ALL groups
        # This targets every group without looping
        filter_groups = types.DialogFilter(
            id=1337,  # Unique custom filter ID
            title="All Groups (Auto-Muted)",
            pinned_peers=[],
            include_peers=[],
            exclude_peers=[],
            groups=True,       # Include basic groups
            broadcasts=False,
            bots=False,
            contacts=False,
            non_contacts=True,
            exclude_muted=False,
            exclude_read=False,
            exclude_archived=False,
            emoticon="👥"
        )
        
        # Push the new filter to Telegram
        await CipherElite(functions.messages.UpdateDialogFilterRequest(
            id=1337,
            filter=filter_groups
        ))
        
        # 2. Apply mute to the ENTIRE folder in ONE request
        # This avoids the FloodWait completely
        await CipherElite(functions.account.UpdateNotifySettingsRequest(
            peer=types.InputNotifyPeer(
                peer=types.InputPeerNotifySettings(
                    show_previews=False,
                    mute_until=31536000, # 1 Year
                )
            ),
            settings=types.InputPeerNotifySettings(
                show_previews=False,
                mute_until=31536000,
            )
        ))
        
        await msg.edit("🔕 **Successfully muted ALL group chats instantly!**\n\n*(No FloodWait triggered)*")
    except Exception as e:
        await msg.edit(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.unmuteall$"))
@rishabh()
async def cmd_unmute_all(event):
    if not await _is_owner(event):
        return
    try:
        msg = await event.reply("⏳ Applying bulk unmute...")
        
        # Unmute the folder
        await CipherElite(functions.account.UpdateNotifySettingsRequest(
            peer=types.InputNotifyPeer(
                peer=types.InputPeerNotifySettings(
                    show_previews=True,
                    mute_until=0,
                )
            ),
            settings=types.InputPeerNotifySettings(
                show_previews=True,
                mute_until=0,
            )
        ))
        
        # Optional: Delete the temporary folder we created
        try:
            await CipherElite(functions.messages.UpdateDialogFilterRequest(
                id=1337,
                filter=None
            ))
        except:
            pass
            
        await msg.edit("🔔 **Successfully unmuted ALL groups!**")
    except Exception as e:
        await msg.edit(f"❌ Error: `{e}`")
