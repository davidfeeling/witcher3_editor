# The Witcher 3: Wild Hunt (Remaster / Next-Gen) — Editor de Partidas Guardadas

[![Juego: The Witcher 3 Remaster](https://img.shields.io/badge/Juego-The%20Witcher%203%20Next--Gen%20(v4.0%2B%20%2F%20v5.0%2B)-c83737.svg)](https://store.steampowered.com/app/292030/The_Witcher_3_Wild_Hunt/)
[![Formato: SAV3 v66/v67](https://img.shields.io/badge/Formato-SAV3%20v66%20%2F%20v67%20(LZ4)-blue.svg)](#formato-técnico-y-arquitectura)
[![Estado: Mantenido activamente](https://img.shields.io/badge/Estado-Mantenido%20recientemente%20(Nov%202026)-success.svg)](#mantenimiento-y-actualización-reciente)
[![Plataforma: Windows](https://img.shields.io/badge/Plataforma-Windows%20(Python%203.10%2B)-informational.svg)](#requisitos-e-instalación)

> **Editor de partidas avanzado, seguro y en español** diseñado específicamente para la versión **Next-Gen / Remaster** de *The Witcher 3: Wild Hunt*. Incluye interfaz gráfica de usuario (GUI), interfaz de consola (CLI), sistema de seguridad con backups atómicos verificados por SHA-256 y traducción oficial de objetos al español extraída directamente del juego.

---

## 📌 ¿Qué es y para qué vale?

Este proyecto es una herramienta completa para inspeccionar, modificar y gestionar partidas guardadas (`.sav`) de *The Witcher 3*.

A diferencia de editores genéricos o antiguos que solían corromper las partidas por desfases de bytes, este editor implementa un motor propio de descompresión y recompresión por bloques **LZ4**, modificando valores in-situ sin alterar la estructura interna del archivo.

### ✨ Funcionalidades principales

* 💰 **Economía (Dinero)**:
  * Ajuste de **Coronas**, **Orenos** y **Florines**.
  * Rango de seguridad controlado (máximo 32.767 para evitar desbordamientos numéricos de 16 bits en el motor de juego).
* 🎒 **Inventario y Recursos**:
  * Modificación de cantidades en cualquier objeto apilable: ingredientes de alquimia, materiales de artesanía, comida, runas, glifos, mutágenos, etc.
  * Botones de acción rápida: **Duplicar (x2)**, **+10** o **Fijar cantidad deseada**.
  * Búsqueda instantánea bilingüe (tanto por nombre en español como por identificador interno en inglés).
* 🃏 **Colección de Cartas de Gwynt**:
  * Edición completa de la baraja y cartas de líder (`CR4GwintManager`).
  * Añade o ajusta copias de cartas (señuelos, cuernos de comandante, cartas de héroe y unidades normales) con opciones como **+1**, **Duplicar (x2)** o **Fijar a 3 copias**.
* ⚔️ **Reparación de Equipo**:
  * Restaura al **100 % de durabilidad** armas o armaduras seleccionadas, o todo el equipo equipado a la vez con un solo clic.
* 🌟 **Experiencia y Habilidades**:
  * Preparación segura de subidas de nivel (+1, +3, +5 niveles) que se aplican limpiamente la próxima vez que Geralt obtiene XP en el juego.
  * Gestión de puntos de habilidad no gastados.
* 🛡️ **Sistema de Seguridad y Backups Automáticos**:
  * Respaldo automático antes de cada guardado (`.sav` original + captura `.png` + metadatos `.json`).
  * Verificación de integridad estricta mediante hash **SHA-256**.
  * Reemplazo atómico de archivos para prevenir fallos ante cortes accidentales.
  * Gestor visual de copias de seguridad con historial de cambios auditables (`historial.jsonl`) y opción de restauración con deshacer.
* 🇪🇸 **Traducciones oficiales al español**:
  * Base de datos integrada con más de **4.200 nombres oficiales** extraídos directamente de los paquetes del juego (`.bundle` y `es.w3strings`), cubriendo el juego base y ambas expansiones (*Hearts of Stone* y *Blood and Wine*).

---

## ⚡ Especialmente diseñado para la edición Remaster / Next-Gen

> [!IMPORTANT]
> **Compatibilidad garantizada para The Witcher 3 Remaster (Next-Gen Update v4.0+ y v5.0+)**.
>
> La actualización Next-Gen de CD Projekt RED introdujo cambios fundamentales en la estructura de las partidas guardadas:
> - **Contenedor LZ4 por bloques**: cabecera `SNFHFZLC` con bloques comprimidos de 1 MiB independientes.
> - **Estructuras SAV3**: versiones internas **v66** y **v67**.
>
> Muchos editores históricos de la comunidad (diseñados para las versiones v64 de 2015-2020) no son compatibles y corrompen estas partidas. **Este editor fue construido y probado desde cero sobre partidas de la edición Remaster**, detectando y rechazando de forma segura partidas obsoletas pre-remaster para proteger al usuario.

---

## 🔄 Mantenimiento y actualización reciente

Este proyecto está **mantenido activamente (actualizado a noviembre de 2026)**:
- Soporte verificado con las últimas actualizaciones del juego en PC (Steam, GOG, sincronización con Steam Cloud y OneDrive).
- Pestaña dedicada para cartas de Gwynt optimizada para evitar duplicidades de identificadores en el gestor de cartas.
- Verificaciones automáticas de integridad en tiempo real durante la carga y guardado.
- Motor de extracción de textos actualizado para regenerar traducciones al español tras parches del juego con un solo botón.

---

## 🚀 Cómo iniciar el editor

### Modo Rápido (Recomendado)
Simplemente haz doble clic en el archivo:
```text
ABRIR_EDITOR_WITCHER3.cmd
```
Detectará automáticamente la instalación de Python del sistema y abrirá la interfaz gráfica inmediatamente, sin necesidad de compilar ni instalar paquetes adicionales.

---

## 🎮 Guía de uso de la Interfaz Gráfica

1. **Estado recomendado del juego**: Lo ideal es tener el juego cerrado o en el menú principal. Si está abierto, simplemente recarga la partida tras guardar.
2. **Selecciona tu partida**: En la lista de la izquierda verás todas tus partidas (`ManualSave`, `QuickSave`, `AutoSave`, `CheckPoint`) ordenadas por fecha reciente, acompañadas de su captura de pantalla, dinero actual y nivel.
3. **Realiza tus cambios**:
   - Ajusta dinero y XP en *Dinero y experiencia*.
   - Duplica o ajusta materiales e ingredientes en *Inventario*.
   - Ajusta tus copias de cartas favoritas en *Cartas de Gwynt*.
   - Repara tu equipo dañado en la pestaña de equipo.
   - *Nota*: Los cambios se acumulan visualmente en la sección **Cambios pendientes** sin alterar el disco hasta que confirmes.
4. **Pulsa "GUARDAR EN LA PARTIDA"**:
   - El editor genera automáticamente una copia de seguridad verificada con SHA-256.
   - Recomprime únicamente el bloque modificado mediante LZ4.
   - Escribe el archivo de forma atómica y valida el resultado.
5. **Carga la partida en el juego** y disfruta de tus cambios.

---

## 💻 Uso por Línea de Comandos (CLI)

Para usuarios avanzados o automatizaciones, se incluye `w3cli.py`:

```powershell
# Listar todas las partidas detectadas
python w3cli.py listar

# Ver información detallada e inventario de la partida más reciente
python w3cli.py info ultima --objetos

# Ver colección de cartas de Gwynt de la partida más reciente
python w3cli.py info ultima --cartas

# Modificar dinero, objetos y reparar equipo en la última partida
python w3cli.py cambiar ultima --coronas 5000 --cantidad "Venom extract=90" --carta "Señuelo=3" --reparar

# Gestionar backups e histórico
python w3cli.py copias
python w3cli.py historial
python w3cli.py restaurar <id_copia>
python w3cli.py copia-completa
```

---

## 🗂️ Estructura del Proyecto

| Archivo / Carpeta | Descripción |
|---|---|
| `ABRIR_EDITOR_WITCHER3.cmd` | Lanzador directo de la aplicación para Windows. |
| `w3editor_gui.py` | Interfaz gráfica de usuario moderna construida con Tkinter. |
| `w3cli.py` | Herramienta de línea de comandos para inspección y edición. |
| `w3save.py` | Motor de bajo nivel: parsing `SAV3`, descompresión/recompresión LZ4, tablas de nombres y serialización. |
| `w3backup.py` | Gestor de copias de seguridad con hash SHA-256, restauración y registro histórico. |
| `w3comun.py` | Detección automática de rutas de guardado (`gamesaves`) y flujos atómicos de guardado. |
| `w3traduccion.py` | Módulo de extracción de cadenas oficiales desde `.bundle` y `es.w3strings`. |
| `traducciones_es.json` | Base de datos local con más de 4.200 traducciones oficiales al español. |
| `backups/` | Directorio local donde se almacenan las copias de seguridad de las partidas modificadas. |
| `historial.jsonl` | Registro cronológico en formato JSON Lines de todas las modificaciones y restauraciones. |

---

## 🔬 Formato Técnico y Arquitectura

* **Contenedor `.sav`**: Cabecera `SNFHFZLC` que indexa fragmentos de compresión LZ4 independientes de tamaño fijo (~1 MiB comprimido / ~4.8 MiB descomprimido).
* **Mapeo de Nombres (`NM` / `MANU`)**: Los identificadores de propiedades y objetos (`Crowns`, `level`, etc.) se resuelven mediante tablas de cadenas con referencias numéricas de 16 bits.
* **Componentes de Geralt**: Localización selectiva del nodo `CInventoryComponent` y `CR4GwintManager` bajo la jerarquía del jugador para garantizar que solo se alteren los datos del personaje activo.
* **Edición in-place**: Todo valor editable numérico se sobrescribe en su tamaño binario exacto para evitar desplazamientos de punteros internos.

---

## 📋 Requisitos

* **Sistema Operativo**: Windows 10 / 11 (64-bit).
* **Python**: Python 3.10 o superior (utiliza librerías de la biblioteca estándar de Python sin necesidad de entornos virtuales complejos).
* **Juego**: *The Witcher 3: Wild Hunt* (versión Next-Gen / Remaster 4.0+ o 5.0+).

