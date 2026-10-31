import ctypes
import cv2
import time
from pygrabber.dshow_graph import FilterGraph
import numpy as np
import mediapipe as mp
import tkinter as tk
from PIL import Image, ImageTk
import pygame
import os
from datetime import datetime

# --- KONFIGURASI ---
SENSITIVITAS = 800
VAR_THRESHOLD = 16
COOLDOWN = 2
SHOW_MASK = False
MODEL_PATH = "blaze_face_short_range.tflite"
SCREENSHOT_MAX_AGE_HOURS = 12        # Hapus screenshot yang lebih tua dari 24 jam (ubah sesuai kebutuhan)
CLEANUP_INTERVAL_SECONDS = 3600      # Cek otomatis tiap 1 jam (3600 detik)

WINDOW_WIDTH = 1366
WINDOW_HEIGHT = 768

SCREENSHOT_DIR = "screenshots"
LOG_DIR = "logs"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

def get_camera_index_by_name(target_name_part):
    """Mencari indeks OpenCV berdasarkan nama perangkat keras yang tetap."""
    graph = FilterGraph()
    devices = graph.get_input_devices()
    
    print("=== Daftar Kamera Terdeteksi ===")
    for i, name in enumerate(devices):
        print(f"  [{i}] {name}")
        # Cek kecocokan nama (case-insensitive)
        if target_name_part.lower() in name.lower():
            print(f"✅ Kamera target ditemukan: '{name}' di indeks {i}")
            return i
            
    return None

# --- KONFIGURASI ---
# Ganti "Logitech" dengan sebagian nama webcam asli Anda 
# (misal: "C920", "Integrated Camera", "HD Pro", dll)
TARGET_CAMERA_NAME = "FHD Camera" 

# Cari indeks secara dinamis berdasarkan nama hardware
CAMERA_INDEX = get_camera_index_by_name(TARGET_CAMERA_NAME)

if CAMERA_INDEX is None:
    raise Exception(f"Kamera dengan nama mengandung '{TARGET_CAMERA_NAME}' tidak ditemukan. Cek daftar di atas.")

# Buka kamera dengan backend DirectShow (lebih stabil di Windows)
cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)

if not cap.isOpened():
    raise Exception("Webcam ditemukan, tetapi gagal dibuka.")

# Paksa resolusi (opsional, untuk memastikan kualitas)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

# =========================
# SETUP MEDIAPIPE
# =========================
BaseOptions = mp.tasks.BaseOptions
FaceDetector = mp.tasks.vision.FaceDetector
FaceDetectorOptions = mp.tasks.vision.FaceDetectorOptions
VisionRunningMode = mp.tasks.vision.RunningMode

options = FaceDetectorOptions(
    base_options=BaseOptions(model_asset_path=MODEL_PATH),
    running_mode=VisionRunningMode.IMAGE,
    min_detection_confidence=0.5
)
face_detector = FaceDetector.create_from_options(options)

# =========================
# SETUP BACKGROUND SUBTRACTOR
# =========================
bg_subtractor = cv2.createBackgroundSubtractorMOG2(
    history=500, varThreshold=VAR_THRESHOLD, detectShadows=False
)
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
last_alert = 0
last_box = None
last_box_time = 0

# =========================
# TOGGLE ON/OFF
# =========================
DETECTOR_ACTIVE = True

# Area tombol di frame_resized (koordinat pixel di window)
BTN_X1, BTN_Y1 = WINDOW_WIDTH - 160, 20
BTN_X2, BTN_Y2 = WINDOW_WIDTH - 20, 70

# =========================
# SETUP AUDIO
# =========================
pygame.mixer.init()

def pilih_wajah_utama(detections, w, h):
    best, best_score = None, -1
    for detection in detections:
        bbox = detection.bounding_box
        area = bbox.width * bbox.height
        if bbox.width < w * 0.12:
            continue
        cx = bbox.origin_x + bbox.width / 2
        cy = bbox.origin_y + bbox.height / 2
        dist = ((cx - w * 0.5) / w) ** 2 + ((cy - h * 0.6) / h) ** 2
        score = area / (1 + 8 * dist)
        if score > best_score:
            best_score, best = score, bbox
    return best

def iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union else 0

def play_alert():
    pygame.mixer.Sound("alert.wav").play()

def save_screenshot(frame, area):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"motion_{timestamp}.jpg"
    filepath = os.path.join(SCREENSHOT_DIR, filename)
    cv2.imwrite(filepath, frame)
    return filepath

def write_log(area, screenshot_path=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_filename = f"detector_log_{datetime.now().strftime('%Y%m%d')}.txt"
    log_filepath = os.path.join(LOG_DIR, log_filename)
    log_entry = f"[{timestamp}] Gerakan terdeteksi | Area: {area:.1f}"
    if screenshot_path:
        log_entry += f" | Screenshot: {screenshot_path}"
    log_entry += "\n"
    with open(log_filepath, "a", encoding="utf-8") as f:
        f.write(log_entry)

def cleanup_old_screenshots():
    now = time.time()
    max_age_seconds = SCREENSHOT_MAX_AGE_HOURS * 3600  # Konversi jam ke detik
    deleted = 0
    try:
        for fname in os.listdir(SCREENSHOT_DIR):
            fpath = os.path.join(SCREENSHOT_DIR, fname)
            if not os.path.isfile(fpath):
                continue
            
            # Hitung umur file dari waktu modifikasi terakhir
            file_age_seconds = now - os.path.getmtime(fpath)
            
            if file_age_seconds > max_age_seconds:
                try:
                    os.remove(fpath)
                    deleted += 1
                except Exception as e:
                    print(f"Gagal hapus {fname}: {e}")
    except Exception as e:
        print(f"Gagal scan folder screenshot: {e}")
        
    if deleted > 0:
        print(f"[Cleanup] {deleted} screenshot lama dihapus (>{SCREENSHOT_MAX_AGE_HOURS} jam)")

def schedule_cleanup():
    cleanup_old_screenshots()
    # Jadwalkan pembersihan berikutnya
    root.after(CLEANUP_INTERVAL_SECONDS * 1000, schedule_cleanup)

# =========================
# SETUP TKINTER
# =========================
root = tk.Tk()
root.title("Detector Belakang")
root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")

label = tk.Label(root)
label.pack()

topmost_until = 0

def bring_to_front():
    global topmost_until
    root.lift()
    root.attributes('-topmost', True)
    try:
        hwnd = ctypes.windll.user32.FindWindowW(None, "Detector Belakang")
        if hwnd:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            fg_hwnd = user32.GetForegroundWindow()
            fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
            cur_tid = kernel32.GetCurrentThreadId()
            if fg_tid != cur_tid:
                user32.AttachThreadInput(cur_tid, fg_tid, True)
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
                user32.SetActiveWindow(hwnd)
                user32.AttachThreadInput(cur_tid, fg_tid, False)
            else:
                user32.SetForegroundWindow(hwnd)
            user32.ShowWindow(hwnd, 9)
    except Exception:
        root.focus_force()
    topmost_until = time.time() + 0

def on_focus_out(event):
    root.attributes('-topmost', False)

root.bind('<FocusOut>', on_focus_out)

def check_topmost():
    if time.time() > topmost_until and root.attributes('-topmost'):
        root.attributes('-topmost', False)

# =========================
# FUNGSI TOGGLE
# =========================
def toggle_detector():
    global DETECTOR_ACTIVE
    DETECTOR_ACTIVE = not DETECTOR_ACTIVE
    status = "ON" if DETECTOR_ACTIVE else "OFF"
    print(f">>> Detector {status} <<<")

def on_label_click(event):
    # Cek apakah klik di area tombol toggle
    if BTN_X1 <= event.x <= BTN_X2 and BTN_Y1 <= event.y <= BTN_Y2:
        toggle_detector()

label.bind('<Button-1>', on_label_click)

def on_key_press(event):
    if event.keysym.lower() == 'p':
        toggle_detector()

root.bind('<Key>', on_key_press)

print("Sistem aktif. Tekan 'P' atau klik tombol di pojok kanan atas untuk ON/OFF.")
print(f"Screenshot: {os.path.abspath(SCREENSHOT_DIR)}")
print(f"Log: {os.path.abspath(LOG_DIR)}")

def process_frame():
    global last_alert, last_box, last_box_time

    ret, frame = cap.read()
    if not ret:
        root.after(30, process_frame)
        return

    h, w, _ = frame.shape
    current_time = time.time()

    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

    # 1. Deteksi wajah (tetap jalan agar visual konsisten)
    detection_result = face_detector.detect(mp_image)
    ignore_mask = np.zeros((h, w), dtype=np.uint8)
    face_boxes = []

    bbox = pilih_wajah_utama(detection_result.detections or [], w, h)
    if bbox is not None:
        candidate_box = (
            bbox.origin_x, bbox.origin_y,
            bbox.origin_x + bbox.width, bbox.origin_y + bbox.height,
        )
        if last_box is None:
            last_box = candidate_box
            last_box_time = current_time
        elif iou(candidate_box, last_box) >= 0.2:
            last_box = candidate_box
            last_box_time = current_time
        elif current_time - last_box_time > 1:
            last_box = candidate_box
            last_box_time = current_time

    if last_box is not None and current_time - last_box_time <= 1:
        x1_raw, y1_raw, x2_raw, y2_raw = last_box
        w_box, h_box = x2_raw - x1_raw, y2_raw - y1_raw
        x1 = max(0, x1_raw - int(w_box * 1.1))
        y1 = max(0, y1_raw - int(h_box * 1.1))
        x2 = min(w, x2_raw + int(w_box * 1.1))
        y2 = min(h, y2_raw + int(h_box * 2.5))
        cv2.rectangle(ignore_mask, (x1, y1), (x2, y2), 255, -1)
        face_boxes.append((x1, y1, x2, y2))

    # 2 & 3. Deteksi gerakan HANYA jika aktif
    motion_boxes = []
    motion_detected = False
    max_area = 0

    if DETECTOR_ACTIVE:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        fg_mask = bg_subtractor.apply(gray)
        fg_mask = cv2.bitwise_and(fg_mask, cv2.bitwise_not(ignore_mask))
        _, fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
        fg_mask = cv2.dilate(fg_mask, kernel, iterations=2)

        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            area = cv2.contourArea(c)
            if area > max_area:
                max_area = area
            if area > SENSITIVITAS:
                motion_detected = True
                x, y, w_c, h_c = cv2.boundingRect(c)
                motion_boxes.append((x, y, w_c, h_c))

    # 4. Visualisasi
    for (x1, y1, x2, y2) in face_boxes:
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
        cv2.putText(frame, "IGNORED", (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

    for (x, y, w_c, h_c) in motion_boxes:
        cv2.rectangle(frame, (x, y), (x + w_c, y + h_c), (0, 255, 0), 2)

    # Alert hanya jika aktif
    if motion_detected and DETECTOR_ACTIVE:
        if current_time - last_alert > COOLDOWN:
            bring_to_front()
            screenshot_path = save_screenshot(frame, max_area)
            write_log(max_area, screenshot_path)
            print(f">>> GERAKAN DI BELAKANG TERDETEKSI! Area: {max_area} <<<")
            print(f"Screenshot: {screenshot_path}")
            play_alert()
            last_alert = current_time

        cv2.rectangle(frame, (0, 0), (w, h), (0, 0, 255), 15)
        cv2.putText(frame, "ADA ORANG DI BELAKANG!", (50, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 4)

    # Overlay status OFF
    if not DETECTOR_ACTIVE:
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)
        cv2.putText(frame, "DETECTOR OFF", (w // 2 - 250, h // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 2.5, (0, 0, 255), 6)
        cv2.putText(frame, "Tekan P atau klik tombol untuk ON", (w // 2 - 320, h // 2 + 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

    check_topmost()

    # Resize & render
    frame_resized = cv2.resize(frame, (WINDOW_WIDTH, WINDOW_HEIGHT))
    frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)

    # Gambar tombol toggle DI frame_resized (setelah resize agar koordinat pas dengan klik)
    if DETECTOR_ACTIVE:
        btn_color = (0, 180, 0)
        btn_text = "ON"
    else:
        btn_color = (0, 0, 200)
        btn_text = "OFF"
    cv2.rectangle(frame_rgb, (BTN_X1, BTN_Y1), (BTN_X2, BTN_Y2), btn_color, -1)
    cv2.rectangle(frame_rgb, (BTN_X1, BTN_Y1), (BTN_X2, BTN_Y2), (255, 255, 255), 2)
    cv2.putText(frame_rgb, btn_text, (BTN_X1 + 45, BTN_Y1 + 35),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3)

    img = Image.fromarray(frame_rgb)
    imgtk = ImageTk.PhotoImage(image=img)
    label.imgtk = imgtk
    label.configure(image=imgtk)

    root.after(30, process_frame)

cleanup_old_screenshots()          # bersihkan yang sudah basi saat start
schedule_cleanup()                 # jadwalkan pembersihan periodik
process_frame()
root.mainloop()

cap.release()
face_detector.close()