import ctypes
import os


# ── Volume Control (pycaw) ──────────────────────────────────────
def _get_volume_interface():
    """Helper to get the volume interface with proper COM initialization."""
    import comtypes
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    # Initialize COM for this thread (required for pycaw)
    try:
        comtypes.CoInitialize()
    except OSError:
        pass  # Already initialized

    # Get the default audio playback device using the correct API
    device_enum = AudioUtilities.GetDeviceEnumerator()
    # Get default audio endpoint (0 = eRender for playback, 0 = eConsole)
    default_device = device_enum.GetDefaultAudioEndpoint(0, 0)
    
    # Activate the IAudioEndpointVolume interface
    interface = default_device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume = interface.QueryInterface(IAudioEndpointVolume)
    return volume


def set_volume(level: int) -> dict:
    """
    Set system volume.
    level: 0-100 (percentage)
    Returns: {"success": True, "volume": level}
    """
    try:
        level = max(0, min(100, level))  # clamp to 0-100
        volume = _get_volume_interface()
        # pycaw uses scalar 0.0-1.0
        volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        return {"success": True, "volume": level}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_volume() -> dict:
    """Returns current system volume as 0-100."""
    try:
        volume = _get_volume_interface()
        level = round(volume.GetMasterVolumeLevelScalar() * 100)
        return {"success": True, "volume": level}
    except Exception as e:
        return {"success": False, "error": str(e)}


def mute_volume() -> dict:
    """Mutes system audio."""
    try:
        volume = _get_volume_interface()
        volume.SetMute(1, None)
        return {"success": True, "muted": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def unmute_volume() -> dict:
    """Unmutes system audio."""
    try:
        volume = _get_volume_interface()
        volume.SetMute(0, None)
        return {"success": True, "muted": False}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Brightness Control ────────────────────────────────────────────
def set_brightness(level: int) -> dict:
    """
    Set display brightness.
    level: 0-100 (percentage)
    Note: Only works on laptop displays or monitors with DDC/CI support.
    Returns: {"success": True/False, "brightness": level}
    """
    import screen_brightness_control as sbc
    level = max(0, min(100, level))
    try:
        sbc.set_brightness(level)
        return {"success": True, "brightness": level}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_brightness() -> dict:
    """Returns current display brightness as 0-100."""
    import screen_brightness_control as sbc
    try:
        brightness = sbc.get_brightness()
        # Returns list if multiple monitors — take first
        level = brightness[0] if isinstance(brightness, list) else brightness
        return {"success": True, "brightness": level}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── System Actions ────────────────────────────────────────────────
def lock_screen() -> dict:
    """Locks the Windows screen."""
    ctypes.windll.user32.LockWorkStation()
    return {"success": True}


def get_pc_stats() -> dict:
    """Returns basic system stats."""
    import psutil
    # Get current drive letter dynamically (e.g., "C:\")
    drive = os.getcwd()[:3]
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory_percent": psutil.virtual_memory().percent,
        "memory_available_gb": round(psutil.virtual_memory().available / (1024**3), 2),
        "disk_free_gb": round(psutil.disk_usage(drive).free / (1024**3), 2),
    }
