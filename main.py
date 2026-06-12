import os
import math
import time
import urllib.request
import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
import pyautogui

pyautogui.FAILSAFE = False

# ── Download Model ───────────────────────────────────────────────────────────
MODEL_PATH = "hand_landmarker.task"
if not os.path.exists(MODEL_PATH):
    print("Downloading hand landmarker model...")
    urllib.request.urlretrieve(
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
        MODEL_PATH
    )

# ── MediaPipe Setup ──────────────────────────────────────────────────────────
base_options = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
options = vision.HandLandmarkerOptions(
    base_options=base_options,
    num_hands=1,
    min_hand_detection_confidence=0.7,
    min_hand_presence_confidence=0.7,
    min_tracking_confidence=0.7,
)
detector = vision.HandLandmarker.create_from_options(options)

# ── Gesture Maps ────────────────────────────────────────────────────────────
GESTURES = {
    "FIST":       ("Undo",     lambda: pyautogui.hotkey("command", "z")),
    "PEACE":      ("Copy",     lambda: pyautogui.hotkey("command", "c")),
    "OPEN_HAND":  ("Paste",    lambda: pyautogui.hotkey("command", "v")),
    "THUMBS_UP":  ("Save",     lambda: pyautogui.hotkey("command", "s")),
    "POINT_UP":   ("New Tab",  lambda: pyautogui.hotkey("command", "t")),
}

def fingers_up(lm):
    tips = [8, 12, 16, 20]
    pip  = [6, 10, 14, 18]
    up = []

    thumb_tip = lm[4]
    pinky_base = lm[17]
    dist = math.hypot(thumb_tip.x - pinky_base.x, thumb_tip.y - pinky_base.y) 
    up.append(dist > 0.12)
    for i in range(4):
        up.append(lm[tips[i]].y < lm[pip[i]].y)
    return up

def classify(lm):
    up = fingers_up(lm)
    thumb, index, middle, ring, pinky = up
    if not any(up):                                                    return "FIST"
    if all(up):                                                        return "OPEN_HAND"
    if index and middle and not ring and not pinky and not thumb:      return "PEACE"
    if thumb and not index and not middle and not ring and not pinky:  return "THUMBS_UP"
    if index and not middle and not ring and not pinky and not thumb:  return "POINT_UP"
    return None

# ── Main loop ────────────────────────────────────────────────────────────────
cap = cv2.VideoCapture(0)
time.sleep(1.0) # Warmup

if not cap.isOpened():
    print("ERROR: Could not open camera")
    exit(1)

# PERFORMANCE TWEAK: Restrict resolution to 480p to keep math lightweight
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# Flush startup frames
for _ in range(5):
    cap.read()

last_gesture = None
last_time    = 0
COOLDOWN     = 1.2
enabled      = True

# PERFORMANCE TWEAK: Cap FPS so the CPU gets time to rest between loops
TARGET_FPS = 10
FRAME_DELAY = 1.0 / TARGET_FPS

print("Running — press 'e' to toggle on/off, 'q' to quit")

while cap.isOpened():
    start_time = time.time()
    
    ok, frame = cap.read()
    if not ok:
        time.sleep(0.1)
        continue   

    frame = cv2.flip(frame, 1)
    rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    mp_image     = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result       = detector.detect(mp_image)
    gesture_now  = None

    if result.hand_landmarks:
        lm = result.hand_landmarks[0]
        gesture_now = classify(lm)

        # Draw skeletal lines
        h, w, _ = frame.shape
        for connection in mp.tasks.vision.HandLandmarksConnections.HAND_CONNECTIONS:
            x0 = int(lm[connection.start].x * w)
            y0 = int(lm[connection.start].y * h)    
            x1 = int(lm[connection.end].x * w)
            y1 = int(lm[connection.end].y * h)
            cv2.line(frame, (x0, y0), (x1, y1), (0, 255, 0), 2)
        # Draw joint nodes
        for point in lm:
            cx, cy = int(point.x * w), int(point.y * h)
            cv2.circle(frame, (cx, cy), 4, (255, 0, 255), -1)

    now = time.time()
    if enabled and gesture_now and gesture_now == last_gesture:
        if now - last_time > COOLDOWN and gesture_now in GESTURES:
            label, action = GESTURES[gesture_now]
            action()
            print(f"► {label}")
            last_time = now

    last_gesture = gesture_now

    # On-Screen HUD Render Info
    status_color = (0, 200, 0) if enabled else (0, 0, 200)
    cv2.putText(frame, f"Gestures: {'ON' if enabled else 'OFF'}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)
    if gesture_now:
        label = GESTURES[gesture_now][0] if gesture_now in GESTURES else gesture_now
        cv2.putText(frame, label, (10, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 0), 2)

    legend = ["e - toggle on/off", "q - quit",
              "Fist=Undo  Peace=Copy  Open=Paste",
              "Thumb=Save  Point=New Tab"]
    for i, line in enumerate(legend):
        cv2.putText(frame, line, (10, frame.shape[0] - 80 + i * 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

    cv2.imshow("Hand Shortcuts", frame)
    
    # Process inputs (1ms brief window)
    key = cv2.waitKey(1) & 0xFF
    if key == ord("q"): break
    if key == ord("e"):
        enabled = not enabled
        print(f"Gestures {'enabled' if enabled else 'disabled'}")

    # PERFORMANCE TWEAK: Sleep loop padding to guarantee low CPU usage
    elapsed = time.time() - start_time
    sleep_time = FRAME_DELAY - elapsed
    if sleep_time > 0:
        time.sleep(sleep_time)

cap.release()
cv2.destroyAllWindows()