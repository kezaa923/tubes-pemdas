# -*- coding: utf-8 -*-
"""
Smart Trash Bin - Raspberry Pi 3 Model B
Integrasi dengan Node.js Server via API
"""

import RPi.GPIO as GPIO
import time
import requests
import json
from datetime import datetime

# ===================================
# KONFIGURASI PIN GPIO
# ===================================
# LED Indicators
LED_HIJAU = 25
LED_KUNING = 24
LED_MERAH = 23

# Ultrasonic Sensor HC-SR04
TRIG = 5
ECHO = 6

# Sensor Gas MQ-2
MQ2_PIN = 17  # Digital pin untuk MQ-2

# Buzzer
BUZZER_PIN = 27

# ===================================
# KONFIGURASI SERVER API
# ===================================
API_BASE_URL = "http://localhost:5000/api"  # Ganti dengan IP server jika berbeda
# Contoh: "http://192.168.1.100:5000/api"

# ===================================
# KONFIGURASI SENSOR
# ===================================
TINGGI_TONG = 40  # Tinggi tong sampah dalam cm
GAS_THRESHOLD = 700  # Threshold PPM untuk gas berbahaya
UPDATE_INTERVAL = 3  # Interval pengiriman data ke server (detik)

# ===================================
# SETUP GPIO
# ===================================
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Setup LED
GPIO.setup(LED_HIJAU, GPIO.OUT)
GPIO.setup(LED_KUNING, GPIO.OUT)
GPIO.setup(LED_MERAH, GPIO.OUT)

# Setup Ultrasonic
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)

# Setup MQ-2 (Digital)
GPIO.setup(MQ2_PIN, GPIO.IN)

# Setup Buzzer
GPIO.setup(BUZZER_PIN, GPIO.OUT)

# Initialize all OFF
GPIO.output(LED_HIJAU, False)
GPIO.output(LED_KUNING, False)
GPIO.output(LED_MERAH, False)
GPIO.output(BUZZER_PIN, False)

print("="*50)
print("🚀 Smart Trash Bin System Started")
print("="*50)
print(f"📡 API Server: {API_BASE_URL}")
print(f"📏 Tinggi Tong: {TINGGI_TONG} cm")
print(f"⚠️  Gas Threshold: {GAS_THRESHOLD} PPM")
print(f"⏱️  Update Interval: {UPDATE_INTERVAL} detik")
print("="*50)

# ===================================
# FUNGSI BACA SENSOR ULTRASONIK
# ===================================
def get_distance():
    """Membaca jarak dari sensor ultrasonik HC-SR04"""
    try:
        # Trigger pulse
        GPIO.output(TRIG, False)
        time.sleep(0.05)
        GPIO.output(TRIG, True)
        time.sleep(0.00001)
        GPIO.output(TRIG, False)
        
        # Wait for echo start
        timeout = time.time() + 0.02
        while GPIO.input(ECHO) == 0:
            pulse_start = time.time()
            if time.time() > timeout:
                return None
        
        # Wait for echo end
        timeout = time.time() + 0.02
        while GPIO.input(ECHO) == 1:
            pulse_end = time.time()
            if time.time() > timeout:
                return None
        
        # Calculate distance
        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150
        distance = round(distance, 2)
        
        # Validasi jarak
        if distance < 2 or distance > 400:
            return None
            
        return distance
    except Exception as e:
        print(f"❌ Error membaca ultrasonik: {e}")
        return None

# ===================================
# FUNGSI BACA SENSOR GAS MQ-2
# ===================================
def read_gas_sensor():
    """
    Membaca sensor gas MQ-2
    Return: True jika gas terdeteksi, False jika aman
    """
    try:
        # Baca pin digital MQ-2 (LOW = gas detected, HIGH = safe)
        gas_detected = not GPIO.input(MQ2_PIN)
        
        # Simulasi nilai PPM (untuk analog bisa pakai MCP3008)
        if gas_detected:
            gas_ppm = 800  # Simulasi nilai tinggi
        else:
            gas_ppm = 150  # Simulasi nilai rendah
            
        return gas_detected, gas_ppm
    except Exception as e:
        print(f"❌ Error membaca MQ-2: {e}")
        return False, 0

# ===================================
# FUNGSI HITUNG PERSENTASE PENUH
# ===================================
def calculate_fill_percentage(distance):
    """
    Menghitung persentase kepenuhan tong sampah
    Jarak kecil = sampah penuh, Jarak besar = sampah kosong
    """
    if distance is None or distance > TINGGI_TONG:
        return 0
    
    fill_percentage = ((TINGGI_TONG - distance) / TINGGI_TONG) * 100
    fill_percentage = max(0, min(100, fill_percentage))  # Clamp 0-100
    return round(fill_percentage, 2)

# ===================================
# FUNGSI KONTROL LED
# ===================================
def control_leds(fill_percentage):
    """
    Kontrol LED berdasarkan persentase kepenuhan
    Hijau: 0-29% (Kosong/Rendah)
    Kuning: 30-69% (Setengah)
    Merah: 70-100% (Penuh)
    """
    if fill_percentage < 30:
        GPIO.output(LED_HIJAU, True)
        GPIO.output(LED_KUNING, False)
        GPIO.output(LED_MERAH, False)
        return "green"
    elif fill_percentage < 70:
        GPIO.output(LED_HIJAU, False)
        GPIO.output(LED_KUNING, True)
        GPIO.output(LED_MERAH, False)
        return "yellow"
    else:
        GPIO.output(LED_HIJAU, False)
        GPIO.output(LED_KUNING, False)
        GPIO.output(LED_MERAH, True)
        return "red"

# ===================================
# FUNGSI KONTROL BUZZER
# ===================================
def control_buzzer(fill_percentage, gas_detected, gas_ppm):
    """
    Kontrol buzzer berdasarkan kondisi
    Buzzer nyala jika:
    - Sampah penuh (>=70%)
    - Gas berbahaya terdeteksi (>=700 PPM)
    """
    should_beep = fill_percentage >= 70 or gas_ppm >= GAS_THRESHOLD
    
    if should_beep:
        # Beep pattern
        GPIO.output(BUZZER_PIN, True)
        time.sleep(0.2)
        GPIO.output(BUZZER_PIN, False)
        time.sleep(0.2)
        return "on"
    else:
        GPIO.output(BUZZER_PIN, False)
        return "off"

# ===================================
# FUNGSI KIRIM DATA KE SERVER
# ===================================
def send_data_to_server(data):
    """Kirim data sensor ke Node.js server via API"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/sensor-data",
            json=data,
            timeout=5
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print(f"✅ Data terkirim ke server")
                return True
            else:
                print(f"⚠️  Server response: {result.get('message')}")
                return False
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Koneksi ke server gagal!")
        return False
    except requests.exceptions.Timeout:
        print(f"❌ Request timeout!")
        return False
    except Exception as e:
        print(f"❌ Error mengirim data: {e}")
        return False

# ===================================
# FUNGSI TAMPILAN STATUS
# ===================================
def print_status(distance, fill_percentage, gas_detected, gas_ppm, led_status, buzzer_status):
    """Tampilkan status di console"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("\n" + "="*60)
    print(f"⏰ {timestamp}")
    print("-"*60)
    print(f"📏 Jarak Sensor: {distance} cm")
    print(f"📊 Kepenuhan: {fill_percentage}%")
    
    # Status tong
    if fill_percentage < 30:
        status_text = "KOSONG/RENDAH 🟢"
    elif fill_percentage < 70:
        status_text = "SETENGAH 🟡"
    else:
        status_text = "PENUH 🔴"
    print(f"🗑️  Status Tong: {status_text}")
    
    # Status gas
    gas_status = "TERDETEKSI ⚠️" if gas_detected else "AMAN ✅"
    print(f"💨 Gas: {gas_status} ({gas_ppm} PPM)")
    
    # LED & Buzzer
    print(f"💡 LED: {led_status.upper()}")
    print(f"🔔 Buzzer: {buzzer_status.upper()}")
    print("="*60)

# ===================================
# MAIN LOOP
# ===================================
def main():
    """Main program loop"""
    print("\n▶️  Program dimulai. Tekan CTRL+C untuk berhenti.\n")
    
    try:
        while True:
            # Baca sensor
            distance = get_distance()
            gas_detected, gas_ppm = read_gas_sensor()
            
            # Validasi pembacaan sensor
            if distance is None:
                print("⚠️  Sensor ultrasonik gagal membaca, skip cycle...")
                time.sleep(1)
                continue
            
            # Hitung persentase kepenuhan
            fill_percentage = calculate_fill_percentage(distance)
            
            # Kontrol hardware
            led_status = control_leds(fill_percentage)
            buzzer_status = control_buzzer(fill_percentage, gas_detected, gas_ppm)
            
            # Tampilkan status
            print_status(distance, fill_percentage, gas_detected, gas_ppm, led_status, buzzer_status)
            
            # Siapkan data untuk server
            sensor_data = {
                "fill_percentage": fill_percentage,
                "distance_cm": distance,
                "gas_ppm": gas_ppm
            }
            
            # Kirim ke server
            send_data_to_server(sensor_data)
            
            # Tunggu sebelum pembacaan berikutnya
            time.sleep(UPDATE_INTERVAL)
            
    except KeyboardInterrupt:
        print("\n\n⏹️  Program dihentikan oleh user")
    except Exception as e:
        print(f"\n\n❌ Error tidak terduga: {e}")
    finally:
        # Cleanup GPIO
        print("🧹 Membersihkan GPIO...")
        GPIO.output(LED_HIJAU, False)
        GPIO.output(LED_KUNING, False)
        GPIO.output(LED_MERAH, False)
        GPIO.output(BUZZER_PIN, False)
        GPIO.cleanup()
        print("✅ GPIO dibersihkan. Program selesai.")

# ===================================
# ENTRY POINT
# ===================================
if __name__ == "__main__":
    main()