import cv2
import time
import numpy as np
import HandTrackerModule as htm
import math
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

# Camera Setup
wCam, hCam = 940, 640
cap = cv2.VideoCapture(0)

cap.set(3, wCam)
cap.set(4, hCam)

# Hand Detector
detector = htm.handDetector(detectionCon=0.7)

# Audio Setup
devices = AudioUtilities.GetSpeakers()
interface = devices.Activate(
    IAudioEndpointVolume._iid_,
    CLSCTX_ALL,
    None
)

volume = cast(interface, POINTER(IAudioEndpointVolume))

volRange = volume.GetVolumeRange()
minVol = volRange[0]
maxVol = volRange[1]

# State Variables
smoothVol = 0
muteState = False
muteHoldStart = 0
muteTriggered = False
volumeLocked = False
lockedVol = None
lockedPer = 0           
lockedBar = 400
stableStart = 0
LOCK_DURATION = 2.0
LOCK_THRESHOLD = 8
UNLOCK_MOVEMENT = 20

prevCx = 0
prevCy = 0

realVolPer = 0
realVolBar = 400

pTime = 0


def draw_volume_bar(img, bar_y, pct):

    cv2.rectangle(
        img,
        (40, 150),
        (90, 400),
        (255, 0, 0),
        2
    )

    cv2.rectangle(
        img,
        (40, int(bar_y)),
        (90, 400),
        (255, 0, 0),
        cv2.FILLED
    )

    cv2.putText(
        img,
        f"{int(pct)}%",
        (30, 440),
        cv2.FONT_HERSHEY_COMPLEX,
        0.8,
        (255, 0, 0),
        2
    )


while True:

    success, img = cap.read()

    if not success:
        print("Camera read failed")
        break

    now = time.time()

    img = detector.findHands(img)
    lmList = detector.findPosition(img, draw=False)

    # HUD Background
    cv2.rectangle(
        img,
        (10, 10),
        (340, 130),
        (30, 30, 30),
        -1
    )

    if len(lmList) != 0:

        x1, y1 = lmList[4][1], lmList[4][2]
        x2, y2 = lmList[8][1], lmList[8][2]

        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2

        length = math.hypot(
            x2 - x1,
            y2 - y1
        )

        # Draw landmarks
        cv2.circle(img, (x1, y1), 15, (180, 105, 255), cv2.FILLED)
        cv2.circle(img, (x2, y2), 15, (180, 105, 255), cv2.FILLED)

        cv2.line(
            img,
            (x1, y1),
            (x2, y2),
            (180, 105, 255),
            3
        )

        # Mute Gesture
        if length < 25:

            if muteHoldStart == 0:
                muteHoldStart = now
                muteTriggered = False

            elif not muteTriggered and now - muteHoldStart > 1:

                muteState = not muteState

                volume.SetMute(
                    muteState,
                    None
                )

                muteTriggered = True

            cv2.circle(
                img,
                (cx, cy),
                15,
                (0, 255, 0),
                cv2.FILLED
            )

        else:

            muteHoldStart = 0
            muteTriggered = False

        # Volume Mapping
        rawVol = np.interp(
            length,
            [50, 300],
            [minVol, maxVol]
        )

        smoothVol = smoothVol + (
            rawVol - smoothVol
        ) * 0.2

        # First Frame Protection
        if prevCx == 0 and prevCy == 0:
            movement = 0
        else:
            movement = math.hypot(
                cx - prevCx,
                cy - prevCy
            )

        prevCx = cx
        prevCy = cy

        # LOCK MODE
        if volumeLocked:

            if not muteState:

                try:
                    volume.SetMasterVolumeLevel(
                        lockedVol,
                        None
                    )
                except Exception as e:
                    print(e)

            if movement > UNLOCK_MOVEMENT:

                volumeLocked = False
                stableStart = 0

        else:

            if movement < LOCK_THRESHOLD:

                if stableStart == 0:
                    stableStart = now

                elapsed = now - stableStart

                remaining = max(
                    0,
                    LOCK_DURATION - elapsed
                )

                if elapsed >= LOCK_DURATION:

                    volumeLocked = True

                    lockedVol = smoothVol

                    lockedPer = realVolPer
                    lockedBar = realVolBar

            else:

                stableStart = 0
                remaining = LOCK_DURATION

            if not muteState:

                try:
                    volume.SetMasterVolumeLevel(
                        smoothVol,
                        None
                    )
                except Exception as e:
                    print(e)

            realVolPer = (
                volume.GetMasterVolumeLevelScalar()
                * 100
            )

            realVolBar = np.interp(
                realVolPer,
                [0, 100],
                [400, 150]
            )

    # Volume Bar
    if volumeLocked:
        draw_volume_bar(
            img,
            lockedBar,
            lockedPer
        )
    else:
        draw_volume_bar(
            img,
            realVolBar,
            realVolPer
        )

    # Status Messages
    if muteState:

        cv2.putText(
            img,
            "MUTED",
            (220, 40),
            cv2.FONT_HERSHEY_COMPLEX,
            0.8,
            (0, 0, 255),
            2
        )

    if volumeLocked:

        cv2.putText(
            img,
            "LOCKED",
            (20, 80),
            cv2.FONT_HERSHEY_COMPLEX,
            0.8,
            (0, 255, 0),
            2
        )

        cv2.putText(
            img,
            "Move Hand To Unlock",
            (20, 110),
            cv2.FONT_HERSHEY_COMPLEX,
            0.6,
            (0, 255, 0),
            2
        )

    elif len(lmList) != 0:

        cv2.putText(
            img,
            f"Lock In: {remaining:.1f}s",
            (20, 80),
            cv2.FONT_HERSHEY_COMPLEX,
            0.8,
            (0, 255, 255),
            2
        )

    # FPS
    cTime = now

    fps = 1 / (cTime - pTime) if cTime != pTime else 0

    pTime = cTime

    cv2.putText(
        img,
        f"FPS: {int(fps)}",
        (20, 40),
        cv2.FONT_HERSHEY_COMPLEX,
        0.8,
        (255, 255, 255),
        2
    )

    cv2.imshow(
        "Volume Control",
        img
    )

    key = cv2.waitKey(1) & 0xFF

    if key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()