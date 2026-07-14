#include "DHT.h"
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

#define DHTPIN 2     // Pin digital conectado al sensor DHT11[cite: 1]
#define DHTTYPE DHT11

DHT dht(DHTPIN, DHTTYPE);
LiquidCrystal_I2C lcd(0x27, 16, 2); // LCD de 16x2[cite: 3]

// Dibujamos el símbolo de grados pixel a pixel (un pequeño cuadrado arriba)
byte grado[8] = {
  B00110,
  B01001,
  B01001,
  B00110,
  B00000,
  B00000,
  B00000,
  B00000
};

String mensaje = "";
unsigned long ultimoEnvio = 0;
const unsigned long intervaloEnvio = 2000; // Enviar datos cada 2 segundos[cite: 1]

void setup() {
  Serial.begin(9600); // Comunicación serial[cite: 1, 3]
  dht.begin();        // Inicializar DHT[cite: 1]
  
  lcd.init();         // Inicializar LCD[cite: 3]
  lcd.backlight();    // Encender luz de fondo[cite: 3]
  
  // Guardamos el carácter de grado en el slot 0 de la memoria del LCD
  lcd.createChar(0, grado);
  
  lcd.print("Estacion Activa");
}

void loop() {
  // --- PARTE 1: RECIBIR TEXTO DE PYTHON PARA LA LCD ---[cite: 3]
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      mostrar(mensaje);
      mensaje = "";
    } else {
      mensaje += c;
    }
  }

  // --- PARTE 2: ENVIAR DATOS DEL DHT11 A PYTHON ---[cite: 1]
  unsigned long tiempoActual = millis();
  if (tiempoActual - ultimoEnvio >= intervaloEnvio) {
    ultimoEnvio = tiempoActual;

    float h = dht.readHumidity();    // Lectura de humedad[cite: 1]
    float t = dht.readTemperature(); // Lectura de temperatura[cite: 1]

    if (!isnan(h) && !isnan(t)) {
      // Enviamos "temp,hum" por el puerto serial[cite: 1]
      Serial.print(t);
      Serial.print(",");
      Serial.println(h);
    }
  }
}

// Función para imprimir en la LCD, manejar parpadeo de alerta y saltos de línea[cite: 3]
void mostrar(String texto) {
  bool alerta = false;

  // Si Python nos manda un '*', significa que hay alerta activa
  if (texto.startsWith("*")) {
    alerta = true;
    texto = texto.substring(1); // Quitamos el '*' para no mostrarlo en pantalla
  }

  lcd.clear(); // Limpiamos pantalla antes de escribir[cite: 3]

  int salto = texto.indexOf('|'); // Buscamos divisor de línea[cite: 3]

  if (salto == -1) {
    lcd.setCursor(0, 0);
    escribirConGrados(texto);
  } else {
    lcd.setCursor(0, 0);
    escribirConGrados(texto.substring(0, salto)); // Primera línea[cite: 3]

    lcd.setCursor(0, 1);
    escribirConGrados(texto.substring(salto + 1)); // Segunda línea[cite: 3]
  }

  // Si hay alerta, hacemos parpadear la pantalla para llamar la atención
  if (alerta) {
    for (int i = 0; i < 3; i++) {
      lcd.noBacklight();
      delay(150);
      lcd.backlight(); //[cite: 3]
      delay(150);
    }
  }
}

// Función auxiliar para imprimir el texto reemplazando la 'f' o '~' (que enviaremos de Python) por el carácter personalizado
void escribirConGrados(String linea) {
  for (int i = 0; i < linea.length(); i++) {
    if (linea[i] == '~') { // Usaremos el caracter '~' como indicador del grado
      lcd.write(0);        // Imprime nuestro símbolo de grado personalizado
    } else {
      lcd.print(linea[i]);
    }
  }
}