# =============================================================================
#  CipherElite Plugin - mute_all.py
#  Instantly mutes/unmutes all group chats via Telegram Folders
# =============================================================================

from telethon import events
from utils.utils import CipherElite
from utils.decorators import rishabh
from plugins.bot import add_handler
from telethon.tl import functions, types
import asyncio

VERSION = "1.0.0"
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
        msg = await event.reply("⏳ Muting all groups...")
        
        # We use Telegram's Folder API to target all groups
        # 1 = Contacts, 2 = Non-contacts, 3 = Groups, 4 = Channels, 5 = Bots
        filter_groups = types.DialogFilter(
            id=2,  # Custom filter ID, safe to overwrite
            title="Groups",
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
            id=2,
            filter=filter_groups
        ))
        
        # Now apply the mute to that filter
        # Telethon doesn't have a direct "mute folder" method, so we loop through dialogs
        # but we do it fast in batches.
        count = 0
        async for dialog in CipherElite.iter_dialogs():
            if dialog.is_group:
                # Mute for 1 year (31536000 seconds)
                await CipherElite(functions.account.UpdateNotifySettingsRequest(
                    peer=dialog.entity,
                    settings=types.InputPeerNotifySettings(
                        mute_until=31536000,
                        show_previews=False,
                    )
                ))
                count += 1
                
        await msg.edit(f"🔕 Successfully muted **{count}** groups.")
    except Exception as e:
        await msg.edit(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.unmuteall$"))
@rishabh()
async def cmd_unmute_all(event):
    if not await _is_owner(event):
        return
    try:
        msg = await event.reply("⏳ Unmuting all groups...")
        
        count = 0
        async for dialog in CipherElite.iter_dialogs():
            if dialog.is_group:
                # Unmute (0 = unmuted)
                await CipherElite(functions.account.UpdateNotifySettingsRequest(
                    peer=dialog.entity,
                    settings=types.InputPeerNotifySettings(
                        mute_until=0,
                        show_previews=True,
                    )
                ))
                count += 1
                
        await msg.edit(f"🔔 Successfully unmuted **{count}** groups.")
    except Exception as e:
        await msg.edit(f"❌ Error: `{e}`")
