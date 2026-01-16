# Meta Campaign Data Extractor

Script completo para extraer, procesar y transformar datos de campañas de Meta (Facebook/Instagram) para análisis en Power BI.

## 🚀 Características

### **1. Extracción Automática de Datos**
- Extrae datos diarios de campañas de Meta API
- Detección automática de última fecha y extracción de siguientes 7 días
- Manejo robusto de errores con detención en caso de problemas críticos

### **2. Reporte Semanal Automático**
- Generación automática de reportes semanales con PNGs
- Detección automática de última semana disponible
- Comparaciones vs semana anterior, mismo mes anterior, mismo año anterior
- Exportación de tablas de variaciones (%) y valores absolutos

### **3. Transformación para Power BI**
- **`primera_tabla`**: Datos de campañas (nivel campaign) transformados para Power BI
- **`segunda_tabla`**: Métricas de video (nivel anuncio) para análisis detallado
- Variables globales disponibles directamente en Power BI Desktop

### **4. Logging Inteligente**
- Detección automática de entorno (Power BI vs terminal)
- En Power BI: muestra resultados en panel de salida + guarda logs
- En terminal: guarda logs en archivo con timestamp

## 📋 Estructura del Script

```python
# Parte 1: Extracción de 7 días de API Meta
# Parte 2: Generación de reporte semanal con PNGs  
# Parte 3: Transformación primera_tabla para Power BI
# Parte 4: Extracción segunda_tabla (métricas de video) para Power BI
```

## 🛠️ Configuración

### **Variables de Entorno**
```bash
META_APP_ID=your_app_id
META_APP_SECRET=your_app_secret  
META_ACCESS_TOKEN=your_access_token
```

### **Cuentas de Meta**
```python
account_map = {
    'act_266875535124705': 'tla',
    'act_172227634833453': 'illapa',
}
```

### **Paths de Salida**
- **Datos crudos**: `C:\Users\Lima - Rodrigo\Documents\3pro\meta\campaign\data\campaign_1d`
- **Reportes PNGs**: `../insight/`
- **Power BI**: `C:\Users\Lima - Rodrigo\Documents\3pro\meta\campaign\data_powerbi\`
- **Logs**: `C:\Users\Lima - Rodrigo\Documents\3pro\meta\reporte_semanal\logs\`

## 📊 Tablas Generadas

### **`primera_tabla`** (Campañas)
| Columna | Tipo | Descripción |
|---------|------|-------------|
| account | string | Nombre de cuenta |
| date_start | date | Fecha de inicio |
| date_stop | date | Fecha de fin (duplicado) |
| campaign_id | string | ID de campaña |
| campaign_name | string | Nombre de campaña |
| spend | float | Inversión |
| impressions | int | Impresiones |
| reach | int | Alcance |
| video_25pct | int | Reproducciones al 25% |
| clicks_all | int | Clics totales |
| link_clicks | int | Clics en links |
| ctr | float | CTR general |
| unique_link_clicks_ctr | float | CTR links |
| first_replies | int | Leads WhatsApp |
| two_way_conversations | int | Conversaciones bidireccionales |

### **`segunda_tabla`** (Métricas de Video - Nivel Anuncio)
| Columna | Tipo | Descripción |
|---------|------|-------------|
| account | string | Nombre de cuenta |
| ad_id | string | ID de anuncio |
| campaign_id | string | ID de campaña |
| date_start | date | Fecha |
| impressions | int | Impresiones |
| video_plays | int | Reproducciones iniciadas |
| video_3s_views | int | Vistas a 3 segundos |
| video_100pct_views | int | Vistas al 100% |
| retention_3s_pct | float | Retención a 3s |
| retention_complete_pct | float | Retención completa |
| thruplay | int | Vistas completas |
| curve_3s_pct_api | float | Curva de retención API |

## 🚀 Uso

### **En Terminal**
```bash
python a01.py
```
- Extrae datos de API
- Genera reportes PNGs
- Guarda logs en archivo
- No muestra en consola

### **En Power BI Desktop**
1. Copiar todo el código al editor de Python
2. Ejecutar script
3. **Dataframes disponibles:**
   - `primera_tabla` (campañas)
   - `segunda_tabla` (métricas de video)
4. Ver resultados en panel de salida

## 📁 Archivos Generados

```
📂 meta/
├── 📂 campaign/
│   ├── 📂 data/
│   │   ├── 📄 campaign_1d (datos crudos)
│   │   └── 📄 campaign_1d_backup_before_append.csv
│   └── 📂 data_powerbi/
│       ├── 📄 powerbi_ready.csv
│       └── 📄 campaign_video_3s_100pct_1d_ads.csv
├── 📂 reporte_semanal/
│   ├── 📂 insight/
│   │   ├── 📄 tabla_variaciones.png
│   │   └── 📄 tabla_valores.png
│   └── 📂 logs/
│       └── 📄 meta_extractor_YYYYMMDD_HHMMSS.log
└── 📂 scripts/
    └── 📄 a01.py
```

## 🔧 Dependencias

```bash
pip install pandas numpy matplotlib facebook-business
pip install python-dateutil pathlib
```

## ⚙️ Configuración Avanzada

### **Modificación de Fechas**
El script detecta automáticamente la última fecha disponible y extrae los siguientes 7 días. Para fechas manuales, modificar:

```python
START_DATE = date(2026, 1, 13)
END_DATE = date(2026, 1, 19)
```

### **Personalización de Reportes**
- Modificar `metric_map` para cambiar nombres de métricas
- Ajustar `output_dir` para cambiar ubicación de PNGs
- Personalizar columnas en `EXPECTED_COLUMNS`

## 🚨 Manejo de Errores

- **Sin CSV existente**: Detiene ejecución con error claro
- **Error de lectura CSV**: Detiene ejecución con error crítico
- **Error de API**: Reintentos automáticos con backoff
- **Fechas inválidas**: Validación y detención

## 📈 Flujo Completo

1. **Detección automática** de última fecha en CSV existente
2. **Extracción** de 7 días de datos de Meta API
3. **Generación** de reporte semanal con PNGs
4. **Transformación** de datos para Power BI
5. **Extracción** de métricas de video a nivel anuncio
6. **Disponibilidad** de dataframes globales para Power BI

## 🔄 Automatización

Ideal para ejecución programada (ej. diaria o semanal):
- Detecta automáticamente qué datos necesita
- Actualiza CSV existente sin duplicados
- Genera reportes automáticamente
- Prepara datos para Power BI

## 📝 Notas

- **Power BI Desktop**: Los dataframes `primera_tabla` y `segunda_tabla` están disponibles globalmente
- **Logs**: Siempre se guardan con timestamp para auditoría
- **Backups**: Se crea backup automático antes de actualizar CSV
- **PNGs**: Se sobrescriben automáticamente en cada ejecución

## 🤝 Contribuciones

1. Fork del repositorio
2. Feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit (`git commit -m 'Add some AmazingFeature'`)
4. Push (`git push origin feature/AmazingFeature`)
5. Pull Request

## 📄 Licencia

Este proyecto es para uso interno. Consultar con el equipo para permisos de uso.
