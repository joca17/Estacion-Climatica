import serial
import time
import threading
import sqlite3
from datetime import datetime
import logging
import tkinter as tk
import webbrowser
import requests
from flask import Flask, jsonify, render_template, send_file

# ================= CONFIG =================
PORT = 'COM4'
BAUDRATE = 9600
DB_NAME = "datos.db"

# ================= LOGGING =================
logging.basicConfig(
    filename="errores.log",
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ================= BASE DE DATOS (Inicialización) =================
db_lock = threading.Lock()

def inicializar_db():
    with db_lock:
        conn = sqlite3.connect(DB_NAME, timeout=10)
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS datos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            temperatura REAL,
            humedad REAL
        )
        """)
        conn.commit()
        conn.close()

inicializar_db()

# ================= SERIAL =================
ser = None
ultimo_dato = {"temp": 0, "hum": 0}

def conectar_serial():
    global ser
    while True:
        try:
            if ser is not None and ser.is_open:
                ser.close # Aseguea el cierre antes de reintentar conexión
            ser = serial.Serial(PORT, BAUDRATE, timeout=1)
            time.sleep(2)
            print(f"✅ Conectado a {PORT}")
            return
        except serial.SerialException as e:
            print(f"❌ Error puerto: {e}")
            logging.error(f"Error puerto: {e}")
            time.sleep(3)

# Variable para alternar la pantalla en cada ciclo
mostrar_stats = False

# ================= LECTURA DE DATOS (CON MULTIPANTALLA Y ALERTA) =================
def leer_datos():
    global ultimo_dato, mostrar_stats
    conectar_serial()

    while True:
        try:
            if ser and ser.is_open:
                linea = ser.readline().decode('utf-8').strip()

                if linea:
                    try:
                        temp, hum = map(float, linea.split(','))
                        ultimo_dato = {"temp": temp, "hum": hum}

                        # Conexión dedicada para guardar en la base de datos
                        with db_lock: #
                            conn = sqlite3.connect(DB_NAME) #[cite: 2]
                            cursor = conn.cursor() #[cite: 2]
                            cursor.execute(
                                "INSERT INTO datos (fecha, temperatura, humedad) VALUES (?, ?, ?)", #[cite: 2]
                                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), temp, hum) #[cite: 2]
                            )
                            conn.commit() #[cite: 2]

                            # Obtenemos los valores históricos para la pantalla rotativa[cite: 2]
                            cursor.execute("SELECT MAX(temperatura), MIN(temperatura) FROM datos") #[cite: 2]
                            max_t, min_t = cursor.fetchone() #[cite: 2]
                            conn.close() #[cite: 2]

                        # --- CONFIGURACIÓN DE ALERTA ---
                        # Si supera los 30.0 °C, agregamos el prefijo '*' para activar el parpadeo en Arduino[cite: 2]
                        prefijo_alerta = "*" if temp > 30.0 else "" #[cite: 2]

                        # --- LÓGICA DE ROTACIÓN DE PANTALLA ---
                        if mostrar_stats and max_t is not None and min_t is not None:
                            # Pantalla B: Usamos '~' para indicar el símbolo de grado
                            mensaje_lcd = f"{prefijo_alerta}T.Max: {max_t:.1f}~C|T.Min: {min_t:.1f}~C\n"
                            mostrar_stats = False
                        else:
                            # Pantalla A: Usamos '~' para indicar el símbolo de grado
                            mensaje_lcd = f"{prefijo_alerta}Temp: {temp:.1f}~C|Hum:  {hum:.1f} %\n"
                            mostrar_stats = True

                        # Enviamos el comando por serial a Arduino
                        ser.write(mensaje_lcd.encode('utf-8'))

                    except ValueError:
                        logging.error(f"Formato inválido: {linea}") #[cite: 2]

        except serial.SerialException: #[cite: 2]
            print("⚠️ Reconectando Arduino...")
            conectar_serial()
        except Exception as e:
            logging.error(f"Error general en lectura: {e}") #[cite: 2]

        time.sleep(2.0) # Esperamos 2 segundos para dar tiempo a leer el LCD cómodamente

# ================= FLASK WEB SERVER =================
app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/data")
def data():
    return jsonify(ultimo_dato)

@app.route("/stats")
def stats():
    try:
        with db_lock:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("SELECT AVG(temperatura), MAX(temperatura), MIN(temperatura) FROM datos")
            avg, max_t, min_t = cursor.fetchone()
            conn.close()

        return jsonify({
            "avg": round(avg, 2) if avg else 0,
            "max": max_t or 0,
            "min": min_t or 0
        })
    except Exception as e:
        logging.error(f"Stats error: {e}")
        return jsonify({"avg": 0, "max": 0, "min": 0})

@app.route("/history")
def history():
    try:
        with db_lock:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT fecha, temperatura, humedad
                FROM datos
                ORDER BY id DESC
                LIMIT 20
            """)
            rows = cursor.fetchall()
            conn.close()

        return jsonify([
            {"fecha": r[0], "temp": r[1], "hum": r[2]}
            for r in rows[::-1]
        ])
    except Exception as e:
        logging.error(f"History error: {e}")
        return jsonify([])

@app.route("/download")
def download():
    try:
        return send_file(DB_NAME, as_attachment=True)
    except Exception as e:
        logging.error(f"Download error: {e}")
        return "Error descargando archivo"

def iniciar_servidor():
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

# ================= UI DESKTOP (TKINTER) =================
def abrir_dashboard():
    webbrowser.open_new("http://localhost:5000")

def actualizar_datos():
    try:
        res = requests.get("http://localhost:5000/data", timeout=2)
        data = res.json()

        temp = data["temp"]
        hum = data["hum"]

        temp_label.config(text=f"{temp:.1f} °C")
        hum_label.config(text=f"{hum:.1f} %")
        status_label.config(text="🟢 Conectado", fg="#00ff99")

        if temp > 30:
            temp_label.config(fg="#ff4d4d")
        else:
            temp_label.config(fg="#00ffcc")

    except Exception:
        status_label.config(text="🔴 Sin conexión con el servidor", fg="red")

    root.after(2000, actualizar_datos)

# --- Configuración Estética de UI ---
COLOR_BG = "#0F172A"       # Fondo general (Slate 900)
COLOR_CARD = "#1E293B"     # Fondo del contenedor (Slate 800)
COLOR_TEXT_MAIN = "#F8FAFC"# Texto principal (Slate 50)
COLOR_ACCENT = "#10B981"   # Verde esmeralda moderno

root = tk.Tk()
root.title("Estación Meteorológica")
root.geometry("450x380")
root.configure(bg=COLOR_BG)
root.resizable(False, False)

# --- Encabezado ---
header_frame = tk.Frame(root, bg=COLOR_BG)
header_frame.pack(fill="x", pady=(25, 15))

tk.Label(
    header_frame,
    text="Estación Climática",
    font=("Segoe UI", 14, "bold"),
    fg="#64748B", bg=COLOR_BG
).pack()

tk.Label(
    header_frame,
    text="CAMPOS BATTAGLIA",
    font=("Segoe UI", 18, "bold"),
    fg=COLOR_TEXT_MAIN, bg=COLOR_BG
).pack(pady=(2, 0))

# --- Tarjeta Contenedora de Datos ---
card = tk.Frame(root, bg=COLOR_CARD, bd=0, highlightbackground="#334155", highlightthickness=1)
card.pack(padx=30, pady=10, fill="both", expand=True)

card.grid_columnconfigure(0, weight=1)
card.grid_columnconfigure(1, weight=1)

# Bloque de Temperatura
tk.Label(card, text="TEMPERATURA", font=("Segoe UI", 9, "bold"), fg="#94A3B8", bg=COLOR_CARD).grid(row=0, column=0, pady=(20, 2))
temp_label = tk.Label(card, text="-- °C", font=("Segoe UI", 28, "bold"), fg="#3B82F6", bg=COLOR_CARD)
temp_label.grid(row=1, column=0, pady=(0, 20))

# Bloque de Humedad
tk.Label(card, text="HUMEDAD", font=("Segoe UI", 9, "bold"), fg="#94A3B8", bg=COLOR_CARD).grid(row=0, column=1, pady=(20, 2))
hum_label = tk.Label(card, text="-- %", font=("Segoe UI", 28, "bold"), fg="#06B6D4", bg=COLOR_CARD)
hum_label.grid(row=1, column=1, pady=(0, 20))

# Estatus de Conexión
status_label = tk.Label(card, text="● Conectando...", font=("Segoe UI", 10), fg="#F59E0B", bg=COLOR_CARD)
status_label.grid(row=2, column=0, columnspan=2, pady=(0, 15))

# --- Botón Flat ---
btn_web = tk.Button(
    root,
    text="Abrir Dashboard Web",
    command=abrir_dashboard,
    font=("Segoe UI", 11, "bold"),
    bg=COLOR_ACCENT,
    fg="#FFFFFF",
    activebackground="#059669",
    activeforeground="#FFFFFF",
    relief="flat",
    cursor="hand2",
    bd=0,
    pady=10
)
btn_web.pack(fill="x", padx=30, pady=(15, 25))

# ================= HILOS E INICIO =================
threading.Thread(target=leer_datos, daemon=True).start()
threading.Thread(target=iniciar_servidor, daemon=True).start()

# Lanzar Dashboard tras 2 segundos e iniciar ciclo de actualización de UI
root.after(2000, abrir_dashboard)
root.after(2000, actualizar_datos)

root.mainloop()