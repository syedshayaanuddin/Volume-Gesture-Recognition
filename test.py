from pycaw.pycaw import AudioUtilities
from pycaw.pycaw import IAudioEndpointVolume
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL

devices = AudioUtilities.GetSpeakers()

print(devices)

interface = devices.Activate(
    IAudioEndpointVolume._iid_,
    CLSCTX_ALL,
    None
)

print(interface)

volume = cast(interface, POINTER(IAudioEndpointVolume))

print(volume.GetMasterVolumeLevel())