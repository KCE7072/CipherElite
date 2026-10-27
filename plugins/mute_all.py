# =============================================================================
#  CipherElite Plugin - mute_all.py (FloodWait & FilterID Fix)
# =============================================================================

from telethon import events
from utils.utils import CipherElite
from utils.decorators import rishabh
from plugins.bot import add_handler
from telethon.tl import functions, types
from telethon.tl.functions.messages import GetDialogFiltersRequest
import asyncio

VERSION = "3.0.0"
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

async def _process_mute(dialog, mute_state):
    """Helper to mute/unmute a single dialog"""
    try:
        await CipherElite(functions.account.UpdateNotifySettingsRequest(
            peer=dialog.entity,
            settings=types.InputPeerNotifySettings(
                mute_until=mute_state,
                show_previews=not bool(mute_state) # Previews on if unmuted
            )
        ))
        return True
    except Exception:
        return False

@CipherElite.on(events.NewMessage(pattern=r"\.muteall$"))
@rishabh()
async def cmd_mute_all(event):
    if not await _is_owner(event):
        return
    
    msg = await event.reply("⏳ **Muting all groups in parallel batches...**\n*(This avoids FloodWait)*")
    
    try:
        # 1. Gather all group dialogs first
        groups = []
        async for dialog in CipherElite.iter_dialogs():
            if dialog.is_group:
                groups.append(dialog)
                
        if not groups:
            return await msg.edit("❌ No groups found.")

        # 2. Process in batches of 5 to avoid Telegram's anti-spam
        count = 0
        batch_size = 5
        
        for i in range(0, len(groups), batch_size):
            batch = groups[i:i + batch_size]
            # Fire 5 requests at the exact same time
            results = await asyncio.gather(*[_process_mute(d, 31536000) for d in batch])
            count += sum(results)
            
            # Tiny sleep to let Telegram breathe
            await asyncio.sleep(1.5) 
            
            # Update progress every 50 groups
            if i % 50 == 0 and i > 0:
                await msg.edit(f"⏳ Muting... ({i}/{len(groups)})")

        await msg.edit(f"🔕 **Successfully muted {count} groups!**")
        
    except Exception as e:
        await msg.edit(f"❌ Error: `{e}`")


@CipherElite.on(events.NewMessage(pattern=r"\.unmuteall$"))
@rishabh()
async def cmd_unmute_all(event):
    if not await _is_owner(event):
        return
        
    msg = await event.reply("⏳ **Unmuting all groups in parallel batches...**")
    
    try:
        groups = []
        async for dialog in CipherElite.iter_dialogs():
            if dialog.is_group:
                groups.append(dialog)
                
        if not groups:
            return await msg.edit("❌ No groups found.")

        count = 0
        batch_size = 5
        
        for i in range(0, len(groups), batch_size):
            batch = groups[i:i + batch_size]
            results = await asyncio.gather(*[_process_mute(d, 0) for d in batch])
            count += sum(results)
            
            await asyncio.sleep(1.5) 
            
        await msg.edit(f"🔔 **Successfully unmuted {count} groups!**")
        
    except Exception as e:
        await msg.edit(f"❌ Error: `{e}`")
