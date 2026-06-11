import cv2
import time
import numpy as np
import HandTrackerModule as htm
import math
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

# ── Camera ────────────────────────────────────────────────────────────────────
W, H = 640, 480
cap = cv2.VideoCapture(0)
cap.set(3, W)
cap.set(4, H)

# ── Detector ──────────────────────────────────────────────────────────────────
detector = htm.handDetector(detectionCon=0.7)

# ── Audio ─────────────────────────────────────────────────────────────────────
devices   = AudioUtilities.GetSpeakers()
interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
volume    = cast(interface, POINTER(IAudioEndpointVolume))
minVol, maxVol = volume.GetVolumeRange()[:2]

# ── HUD layout constants ───────────────────────────────────────────────────────
#   Volume bar:  right edge, x=580..610, y=80..380
BAR_X      = 580          # left edge of the bar rect
BAR_W      = 28           # bar width
BAR_TOP    = 80           # y when volume = 100 %
BAR_BOT    = 380          # y when volume = 0 %
BAR_LABEL_X = 582         # x for the "XX%" label below bar

#   Status pill (top-left)
STATUS_X   = 14
STATUS_Y   = 20

#   Lock countdown bar (bottom strip, above percentage label)
CD_Y       = 448          # y of countdown text row

#   FPS (bottom-right)
FPS_X      = W - 10       # right-aligned
FPS_Y      = H - 12

# ── Palette (BGR) ─────────────────────────────────────────────────────────────
C_WHITE     = (255, 255, 255)
C_BLACK     = (10,  10,  10)
C_ACCENT    = (235, 175,  50)   # amber  — live/active elements
C_GREEN     = ( 60, 200, 100)   # locked indicator
C_RED       = ( 60,  60, 230)   # muted (OpenCV BGR so this is red)
C_DIM       = (160, 160, 160)   # secondary text
C_TRACK     = ( 55,  55,  55)   # bar track background
C_FINGER    = (220, 100, 220)   # thumb/index markers
C_PINCH     = ( 80, 220,  80)   # pinch midpoint dot

FONT        = cv2.FONT_HERSHEY_SIMPLEX  # cleaner than COMPLEX at small sizes

# ── State ─────────────────────────────────────────────────────────────────────
rawVol       = minVol        # applied to system immediately (no lag)
displayPer   = 0.0           # smoothed 0-100 for the visual bar only
displayBarY  = float(BAR_BOT)

muteState    = False
muteHoldStart  = 0.0
muteTriggered  = False

volumeLocked = False
lockedVol    = minVol
lockedPer    = 0.0
lockedBarY   = float(BAR_BOT)

stableStart  = 0.0
remaining    = 2.0
LOCK_SECS    = 2.0
LOCK_THR     = 8            # px — midpoint movement threshold for "stable"
UNLOCK_THR   = 20           # px — midpoint movement threshold to break lock

prevCx = prevCy = 0.0
pTime  = 0.0

# ── Helpers ───────────────────────────────────────────────────────────────────
def overlay_rect(img, x, y, w, h, color, alpha=0.45):
    """Semi-transparent filled rectangle (for pill backgrounds)."""
    sub  = img[y:y+h, x:x+w]
    fill = np.full_like(sub, color)
    cv2.addWeighted(fill, alpha, sub, 1 - alpha, 0, sub)
    img[y:y+h, x:x+w] = sub

def draw_text_right(img, text, x_right, y, scale, color, thickness=1):
    """Draw text so its right edge lands at x_right."""
    tw = cv2.getTextSize(text, FONT, scale, thickness)[0][0]
    cv2.putText(img, text, (x_right - tw, y), FONT, scale, color, thickness, cv2.LINE_AA)

def draw_hud(img, per, bar_y, locked, muted, fps_val, hand_visible):
    """Draw the entire HUD. Called once per frame with final state."""

    # ── 1. Volume bar (right side) ────────────────────────────────────────────
    # Track (dark background)
    cv2.rectangle(img, (BAR_X, BAR_TOP), (BAR_X + BAR_W, BAR_BOT),
                  C_TRACK, cv2.FILLED)
    cv2.rectangle(img, (BAR_X, BAR_TOP), (BAR_X + BAR_W, BAR_BOT),
                  C_DIM, 1)
    # Fill — amber when live, green when locked, grey when muted
    if muted:
        fill_col = C_DIM
    elif locked:
        fill_col = C_GREEN
    else:
        fill_col = C_ACCENT
    cv2.rectangle(img, (BAR_X, int(bar_y)), (BAR_X + BAR_W, BAR_BOT),
                  fill_col, cv2.FILLED)

    # Tick marks at 25 / 50 / 75 %
    for tick_pct in (25, 50, 75):
        ty = int(np.interp(tick_pct, [0, 100], [BAR_BOT, BAR_TOP]))
        cv2.line(img, (BAR_X - 4, ty), (BAR_X, ty), C_DIM, 1)

    # Percentage label below bar
    pct_text = f"{int(per)}%"
    tw = cv2.getTextSize(pct_text, FONT, 0.55, 1)[0][0]
    mid_x = BAR_X + BAR_W // 2
    cv2.putText(img, pct_text, (mid_x - tw // 2, BAR_BOT + 20),
                FONT, 0.55, C_WHITE if not muted else C_DIM, 1, cv2.LINE_AA)

    # VOL label above bar
    cv2.putText(img, "VOL", (BAR_X + 2, BAR_TOP - 8),
                FONT, 0.42, C_DIM, 1, cv2.LINE_AA)

    # ── 2. Status pill (top-left) ─────────────────────────────────────────────
    if muted:
        label     = "MUTED"
        pill_col  = (30, 30, 180)     # red-ish (BGR)
        text_col  = (120, 120, 255)
    elif locked:
        label     = "LOCKED"
        pill_col  = (30, 100, 30)
        text_col  = C_GREEN
    else:
        label     = ""
        pill_col  = None
        text_col  = None

    if label:
        tw, th = cv2.getTextSize(label, FONT, 0.6, 2)[0]
        px, py = STATUS_X, STATUS_Y
        overlay_rect(img, px - 6, py - th - 4, tw + 16, th + 12, pill_col, 0.55)
        cv2.putText(img, label, (px, py), FONT, 0.6, text_col, 2, cv2.LINE_AA)

    # "Move hand to unlock" hint — one line below the pill
    if locked:
        cv2.putText(img, "move hand to unlock", (STATUS_X, STATUS_Y + 26),
                    FONT, 0.38, C_GREEN, 1, cv2.LINE_AA)

    # ── 3. Lock countdown (bottom-left, only when hand visible + unlocked) ────
    if hand_visible and not locked and not muted:
        elapsed_frac = max(0.0, 1.0 - remaining / LOCK_SECS)
        # Progress bar: narrow strip
        bar_w_full = 180
        bar_w_done = int(bar_w_full * elapsed_frac)
        cv2.rectangle(img, (STATUS_X, CD_Y + 2), (STATUS_X + bar_w_full, CD_Y + 7),
                      C_TRACK, cv2.FILLED)
        cv2.rectangle(img, (STATUS_X, CD_Y + 2), (STATUS_X + bar_w_done, CD_Y + 7),
                      C_ACCENT, cv2.FILLED)
        cv2.putText(img, f"lock in  {remaining:.1f}s", (STATUS_X, CD_Y),
                    FONT, 0.38, C_ACCENT, 1, cv2.LINE_AA)

    # ── 4. FPS (bottom-right, small + dim) ────────────────────────────────────
    draw_text_right(img, f"fps {int(fps_val)}", FPS_X, FPS_Y,
                    0.38, C_DIM, 1)


# ── Main loop ─────────────────────────────────────────────────────────────────
while True:
    success, img = cap.read()
    if not success:
        break

    img    = detector.findHands(img)
    lmList = detector.findPosition(img, draw=False)
    now    = time.time()

    hand_visible = bool(lmList)

    if lmList:
        x1, y1 = lmList[4][1], lmList[4][2]   # thumb tip
        x2, y2 = lmList[8][1], lmList[8][2]   # index tip
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        length = math.hypot(x2 - x1, y2 - y1)

        # ── Finger markers ────────────────────────────────────────────────────
        cv2.circle(img, (x1, y1), 12, C_FINGER, cv2.FILLED)
        cv2.circle(img, (x2, y2), 12, C_FINGER, cv2.FILLED)
        cv2.line(img, (x1, y1), (x2, y2), C_FINGER, 2)

        # ── Mute: pinch + hold 1 s ────────────────────────────────────────────
        if length < 25:
            if muteHoldStart == 0.0:
                muteHoldStart = now
                muteTriggered = False
            elif not muteTriggered and (now - muteHoldStart) > 1.0:
                muteState = not muteState
                volume.SetMute(muteState, None)
                muteTriggered = True
            cv2.circle(img, (cx, cy), 12, C_PINCH, cv2.FILLED)
        else:
            muteHoldStart = 0.0
            muteTriggered = False

        # ── Actual hand movement (midpoint displacement) ───────────────────────
        movement  = math.hypot(cx - prevCx, cy - prevCy)
        prevCx, prevCy = cx, cy

        # ── Raw volume — computed from current length, applied immediately ─────
        # No smoothing here → bar and speaker stay perfectly in sync.
        rawVol = float(np.interp(length, [300, 50], [minVol, maxVol]))

        # Display percentage — fast EMA so the bar animation is still smooth
        targetPer = float(np.interp(length, [300, 50], [0, 100]))
        displayPer = displayPer + (targetPer - displayPer) * 0.35
        displayBarY = float(np.interp(displayPer, [0, 100], [BAR_BOT, BAR_TOP]))

        if volumeLocked:
            # Re-assert locked value every frame so external changes can't drift it
            if not muteState:
                try:
                    volume.SetMasterVolumeLevel(lockedVol, None)
                except Exception as e:
                    print("Volume error:", e)
            if movement > UNLOCK_THR:
                volumeLocked = False
                stableStart  = 0.0
        else:
            # Stability check
            if movement < LOCK_THR:
                if stableStart == 0.0:
                    stableStart = now
                elapsed   = now - stableStart
                remaining = max(0.0, LOCK_SECS - elapsed)
                if elapsed >= LOCK_SECS:
                    volumeLocked = True
                    lockedVol    = rawVol
                    lockedPer    = displayPer
                    lockedBarY   = displayBarY
            else:
                stableStart = 0.0
                remaining   = LOCK_SECS

            # Apply live volume immediately (no smoothing → no lag)
            if not muteState:
                try:
                    volume.SetMasterVolumeLevel(rawVol, None)
                except Exception as e:
                    print("Volume error:", e)

    # ── Compute FPS ───────────────────────────────────────────────────────────
    fps   = 1.0 / (now - pTime) if (now - pTime) > 0 else 0
    pTime = now

    # ── Draw HUD ──────────────────────────────────────────────────────────────
    if volumeLocked:
        draw_hud(img, lockedPer, lockedBarY, True,  muteState, fps, hand_visible)
    else:
        draw_hud(img, displayPer, displayBarY, False, muteState, fps, hand_visible)

    cv2.imshow("GestureVol", img)
    if cv2.waitKey(1) & 0xFF in (ord('q'), ord('Q')):
        break

# ── Cleanup ───────────────────────────────────────────────────────────────────
cap.release()
cv2.destroyAllWindows()