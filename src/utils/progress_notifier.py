"""
Progress Notifier for Discord
Sends real-time progress updates to Discord during long-running operations.
"""

import asyncio
import logging
from typing import Callable, Optional, Any
from dataclasses import dataclass
from enum import Enum


class ProgressStage(Enum):
    """Progress stages for notifications"""
    STARTING = "🚀"
    SEARCHING = "🔍"
    ANALYZING = "🔬"
    VERIFYING = "✅"
    PROCESSING = "⚙️"
    COMPLETED = "✨"
    WARNING = "⚠️"
    ERROR = "❌"


@dataclass
class ProgressUpdate:
    """Progress update data"""
    stage: ProgressStage
    message: str
    detail: Optional[str] = None


class ProgressNotifier:
    """
    Manages progress notifications to Discord.
    Collects updates and sends them to the specified callback.
    """
    
    def __init__(self, callback: Optional[Callable[[str], Any]] = None):
        """
        Initialize the progress notifier.
        
        Args:
            callback: Async or sync function to send messages to Discord
        """
        self.callback = callback
        self.updates: list[ProgressUpdate] = []
        self._enabled = callback is not None
    
    def set_callback(self, callback: Callable[[str], Any]) -> None:
        """Set the notification callback."""
        self.callback = callback
        self._enabled = True
    
    async def notify(self, stage: ProgressStage, message: str, detail: Optional[str] = None) -> None:
        """
        Send a progress notification.
        
        Args:
            stage: Progress stage (for icon)
            message: Main message
            detail: Optional detail text
        """
        if not self._enabled or not self.callback:
            logging.info(f"[PROGRESS] {stage.value} {message}")
            return
        
        update = ProgressUpdate(stage=stage, message=message, detail=detail)
        self.updates.append(update)
        
        # Format message
        formatted = f"{stage.value} **{message}**"
        if detail:
            formatted += f"\n_{detail}_"
        
        try:
            # Handle both async and sync callbacks
            result = self.callback(formatted)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logging.error(f"[PROGRESS] Failed to send notification: {e}")
    
    def notify_sync(self, stage: ProgressStage, message: str, detail: Optional[str] = None) -> None:
        """
        Synchronous version of notify for use in sync code.
        Queues the notification for later sending.
        
        Args:
            stage: Progress stage (for icon)
            message: Main message
            detail: Optional detail text
        """
        if not self._enabled:
            logging.info(f"[PROGRESS] {stage.value} {message}")
            return
        
        update = ProgressUpdate(stage=stage, message=message, detail=detail)
        self.updates.append(update)
        
        # Format message
        formatted = f"{stage.value} **{message}**"
        if detail:
            formatted += f"\n_{detail}_"
        
        try:
            if self.callback:
                # Just call the callback directly.
                # The callback provided by set_progress_callback MUST handle thread safety 
                # (e.g., using loop.call_soon_threadsafe if it interacts with async code).
                result = self.callback(formatted)
                
                # If the callback returns a coroutine (async func passed to sync notifier),
                # we try to schedule it only if we can find a loop.
                if asyncio.iscoroutine(result):
                    try:
                        loop = asyncio.get_running_loop()
                        asyncio.ensure_future(result)
                    except RuntimeError:
                        logging.warning(f"[PROGRESS] Callback returned coroutine but no event loop found in this thread. Notification: {message}")
                        # For async callbacks in sync context without loop, we can't do much.
                        # The fix is to ensure set_progress_callback receives a sync wrapper (as done in main.py).
        except Exception as e:
            logging.error(f"[PROGRESS] Failed to send sync notification: {e}")
    
    async def _async_callback(self, message: str) -> None:
        """Internal async wrapper for callback."""
        if self.callback:
            result = self.callback(message)
            if asyncio.iscoroutine(result):
                await result
    
    def clear(self) -> None:
        """Clear all stored updates."""
        self.updates.clear()


# Global instance for use across modules
_global_notifier: Optional[ProgressNotifier] = None


def get_progress_notifier() -> ProgressNotifier:
    """Get the global progress notifier instance."""
    global _global_notifier
    if _global_notifier is None:
        _global_notifier = ProgressNotifier()
    return _global_notifier


def set_progress_callback(callback: Callable[[str], Any]) -> None:
    """Set the global progress callback."""
    notifier = get_progress_notifier()
    notifier.set_callback(callback)
