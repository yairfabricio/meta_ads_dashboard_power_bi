# -*- coding: utf-8 -*-
"""
Script para extraer datos de campañas de Meta a nivel diario
Convertido desde notebook meta_campaign_1d.ipynb
"""

# Importar librerías
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
import pandas as pd
import re
import time
import numpy as np
import os
from pathlib import Path
import shutil
import sys
import traceback
import logging
import xlsxwriter

# Configurar logging para guardar en archivo en lugar de imprimir en consola
# Detectar si se ejecuta en Power BI Desktop
POWER_BI_MODE = 'powerbi' in sys.executable.lower() if sys.executable else False

# Determinar rutas base según entorno
if POWER_BI_MODE:
    # En Power BI: usar rutas absolutas (directorio temporal)
    BASE_DIR = r"C:\Users\Lima - Rodrigo\Documents\3pro\meta\reporte_semanal"
else:
    # En terminal: usar rutas relativas desde scripts/
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

log_dir = os.path.join(BASE_DIR, "logs")
os.makedirs(log_dir, exist_ok=True)

# Crear nombre de archivo con timestamp
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = os.path.join(log_dir, f"meta_extractor_{timestamp}.log")

# Configurar el logger
if POWER_BI_MODE:
    # En Power BI: NO redirigir prints (se ven en panel de Power BI) + guardar en log
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8')
            # SIN StreamHandler - los prints se muestran directamente en Power BI
        ]
    )
else:
    # Ejecución normal: solo guardar en log
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8')
        ]
    )

logger = logging.getLogger(__name__)

# Redirigir print() al logger (solo si no es Power BI)
if not POWER_BI_MODE:
    class LoggerWriter:
        def __init__(self, logger, level):
            self.logger = logger
            self.level = level
        
        def write(self, message):
            if message.strip():  # Evitar líneas vacías
                self.logger.log(self.level, message.strip())
        
        def flush(self):
            pass

    sys.stdout = LoggerWriter(logger, logging.INFO)
    sys.stderr = LoggerWriter(logger, logging.ERROR)

# ------------------ CONFIG ------------------
my_app_id       = os.getenv("META_APP_ID")
my_app_secret   = os.getenv("META_APP_SECRET")
my_access_token = os.getenv("META_ACCESS_TOKEN")
if not all([my_app_id, my_app_secret, my_access_token]):
    raise RuntimeError("Faltan variables de entorno de Meta (META_APP_ID / META_APP_SECRET / META_ACCESS_TOKEN)")
account_map = {
    'act_266875535124705': 'tla',
    'act_172227634833453': 'illapa',
}

# Path al CSV existente (ajusta si tu archivo tiene otro nombre/ruta)
output_path = os.path.join(BASE_DIR, "datasets", "data", "campaign_1d")
# Haz backup por seguridad
backup_path = output_path + '_backup_before_append.csv'

# Rango que quieres traer (inclusive)
# Detectar automáticamente última fecha y extraer siguientes 7 días
if os.path.exists(output_path):
    try:
        df_existing = pd.read_csv(output_path, encoding='utf-8-sig', parse_dates=['date'])
        df_existing['date'] = pd.to_datetime(df_existing['date']).dt.date
        last_date = df_existing['date'].max()
        START_DATE = last_date + timedelta(days=1)
        END_DATE = last_date + timedelta(days=7)
        print(f"Última fecha encontrada: {last_date}")
        print(f"Extrayendo rango: {START_DATE} → {END_DATE} (7 días)")
    except Exception as e:
        print(f"Error leyendo CSV existente: {e}")
        print("ERROR CRÍTICO: No se puede determinar el rango de fechas. Deteniendo ejecución.")
        sys.exit(1)
else:
    print("ERROR: No existe el archivo CSV. Deteniendo ejecución.")
    sys.exit(1)
# --------------------------------------------

# Inicializa API
FacebookAdsApi.init(my_app_id, my_app_secret, my_access_token)

# Comprobaciones
if not os.path.exists(output_path):
    print(f"ERROR: no encuentro el archivo existente en: {output_path}")
    sys.exit(1)

# Backup rápido
try:
    pd.read_csv(output_path, encoding='utf-8-sig').to_csv(backup_path, index=False, encoding='utf-8-sig')
    print(f"Backup creado en: {backup_path}")
except Exception as e:
    print("Warning: no pude crear backup automático (pero continuaré).", e)

# Generar días a extraer
if START_DATE > END_DATE:
    raise ValueError("START_DATE no puede ser mayor que END_DATE.")

day_ranges = []
d = START_DATE
while d <= END_DATE:
    day_ranges.append((d.isoformat(), d.isoformat()))
    d += timedelta(days=1)

records = []
requests_counter = 0

for account_id, account_label in account_map.items():
    ad_account = AdAccount(account_id)
    print(f"-> Extrayendo cuenta {account_label} ({account_id})")

    for since, until in day_ranges:
        try:
            insights = ad_account.get_insights(
                fields=[
                    'date_start',
                    'campaign_id', 'campaign_name',
                    'spend', 'impressions', 'reach',
                    'video_p25_watched_actions',
                    'clicks', 'ctr', 'unique_link_clicks_ctr',
                    'actions',
                ],
                params={
                    'time_range': {'since': since, 'until': until},
                    'level': 'campaign',
                    'time_increment': 1,
                },
            )
            requests_counter += 1
        except Exception as e:
            print(f"Warning: fallo API para {since} - {until} en {account_label}: {e}")
            traceback.print_exc()
            time.sleep(3)
            continue

        for r in insights:
            try:
                spend = float(r.get('spend', 0))
                impressions = int(r.get('impressions', 0))
                reach = int(r.get('reach', 0))
                clicks_all = int(r.get('clicks', 0))
                ctr = float(r.get('ctr', 0)) if r.get('ctr') is not None else 0.0
                uniq_ctr = float(r.get('unique_link_clicks_ctr', 0)) if r.get('unique_link_clicks_ctr') is not None else 0.0

                # video 25
                video25 = 0
                for v in r.get('video_p25_watched_actions', []) or []:
                    if isinstance(v, dict) and v.get('action_type') == 'video_view':
                        try:
                            video25 += int(v.get('value', 0))
                        except:
                            pass

                # actions
                link_clicks = 0
                messaging_started = 0
                two_way_conv = 0
                for a in r.get('actions', []) or []:
                    at = a.get('action_type')
                    try:
                        val = int(a.get('value', 0))
                    except:
                        val = 0
                    if at == 'link_click':
                        link_clicks = val
                    elif at in ('onsite_conversion.messaging_conversation_started_7d',
                                'onsite_conversion.messaging_conversation_started',
                                'onsite_conversion.messaging_first_reply'):
                        messaging_started = val if messaging_started == 0 else messaging_started
                    elif at == 'onsite_conversion.messaging_user_depth_2_message_send':
                        two_way_conv = val

                records.append({
                    'account_id': account_label,
                    'date': r.get('date_start'),
                    'campaign_id': r.get('campaign_id'),
                    'campaign_name': r.get('campaign_name'),
                    'spend': spend,
                    'impressions': impressions,
                    'reach': reach,
                    'video_25pct': video25,
                    'clicks_all': clicks_all,
                    'link_clicks': link_clicks,
                    'ctr': ctr,
                    'unique_link_clicks_ctr': uniq_ctr,
                    'messaging_started': messaging_started,
                    'two_way_conversations': two_way_conv,
                })
            except Exception as e:
                print("Warning: fallo procesando un registro:", e)
                continue

        # pausita para no llegar a límites
        time.sleep(5)

print(f"Consultas realizadas: {requests_counter}. Registros nuevos: {len(records)}")

if len(records) == 0:
    print("No hay registros nuevos para las fechas solicitadas. Se aborta sin modificar CSV.")
    sys.exit(0)

# Crear df_new y normalizar fecha
df_new = pd.DataFrame(records)
df_new['date'] = pd.to_datetime(df_new['date']).dt.date

# 🔹 Eliminar filas duplicadas en el df nuevo ANTES de unirlo
df_new = df_new.drop_duplicates(subset=['account_id','date','campaign_id'], keep='last')

# Leer CSV existente y normalizar
df_old = pd.read_csv(output_path, encoding='utf-8-sig', parse_dates=['date'])
df_old['date'] = pd.to_datetime(df_old['date']).dt.date

# Concatenar, quitar duplicados y ordenar
df_final = pd.concat([df_old, df_new], ignore_index=True)
df_final = df_final.drop_duplicates(subset=['account_id', 'date', 'campaign_id'], keep='last')
df_final = df_final.sort_values(['account_id', 'date', 'campaign_id']).reset_index(drop=True)

# Guardar (sobrescribe)
df_final.to_csv(output_path, index=False, encoding='utf-8-sig', date_format='%Y-%m-%d')

print("✅ CSV actualizado correctamente.")
print(f"Rango agregado: {START_DATE} → {END_DATE}")
print(f"Filas añadidas (estimadas): {len(df_new)}. Filas totales ahora: {len(df_final)}")
#----------------------------------------------------------------------------------------------
#                          Segunda Parte - Reporte Semanal
#----------------------------------------------------------------------------------------------

# Importar librerías adicionales para el reporte semanal
import matplotlib.pyplot as plt
import textwrap

def generar_reporte_semanal():
    """
    Genera reporte semanal detectando automáticamente la última semana
    """
    print("\n=== Iniciando generación de reporte semanal ===")
    
    # Leer el CSV actualizado
    try:
        df_campaign_1d = pd.read_csv(output_path, encoding="utf-8")
        print(f"CSV leído correctamente: {len(df_campaign_1d)} filas")
    except Exception as e:
        print(f"Error leyendo CSV para reporte semanal: {e}")
        return
    
    # Preparar datos semanales
    def preparar_weekly(df_campaign_1d: pd.DataFrame):
        df = df_campaign_1d.copy()
        df['date'] = pd.to_datetime(df['date'])
        df['week_period'] = df['date'].dt.to_period('W-MON')
        df['week_start'] = df['week_period'].apply(lambda p: p.start_time)

        df['semester'] = df['date'].dt.to_period('M')
        df['week_of_month'] = (
            df.groupby('semester')['week_period']
              .transform(lambda x: pd.factorize(x)[0] + 1)
        )

        mes_map = {1:'enero',2:'febrero',3:'marzo',4:'abril',5:'mayo',6:'junio',
                   7:'julio',8:'agosto',9:'septiembre',10:'octubre',
                   11:'noviembre',12:'diciembre'}

        df['period'] = df.apply(
            lambda r: f"{r['date'].year}_{mes_map[r['date'].month]}_semana{r['week_of_month']}",
            axis=1
        )

        df_weekly = (
            df.groupby('week_start', as_index=True)
              .agg({
                  'spend': 'sum',
                  'messaging_started': 'sum',
                  'impressions': 'sum',
                  'clicks_all': 'sum',
                  'link_clicks':'sum'
              })
              .sort_index()
        )
        
        # CTR ponderado semanal
        df_weekly['ctr'] = np.where(
            df_weekly['impressions'] > 0,
            df_weekly['clicks_all'] / df_weekly['impressions'],
            np.nan
        )
        
        # Unique link clicks CTR ponderado semanal
        df_weekly['unique_link_clicks_ctr'] = np.where(
            df_weekly['impressions'] > 0,
            df_weekly['link_clicks'] / df_weekly['impressions'],
            np.nan
        )
        
        df_weekly['cpl'] = np.where(
            df_weekly['messaging_started'] > 0,
            df_weekly['spend'] / df_weekly['messaging_started'],
            np.nan
        )

        map_period = (
            df[['week_start','period']]
              .drop_duplicates()
              .set_index('period')['week_start']
        )

        inv_map = (
            df[['week_start','period']]
              .drop_duplicates(subset='week_start')
              .set_index('week_start')['period']
        )
        
        df_weekly['period'] = df_weekly.index.map(inv_map)
        return df, df_weekly, map_period

    # Detectar última semana disponible
    df_base, df_weekly, map_period = preparar_weekly(df_campaign_1d)
    
    if len(df_weekly) == 0:
        print("ERROR: No hay datos semanales disponibles")
        return
    
    # Obtener la última semana
    ultima_semana = df_weekly.index.max()
    periodo_actual = df_weekly.loc[ultima_semana, 'period']
    
    print(f"Última semana detectada: {periodo_actual}")
    print(f"Fecha de inicio de semana: {ultima_semana.date()}")
    
    # Calcular siguiente semana
    siguiente_semana = ultima_semana + pd.Timedelta(weeks=1)
    
    # Determinar año, mes y número de semana siguiente
    año_siguiente = siguiente_semana.year
    mes_siguiente = siguiente_semana.month
    
    # Encontrar el número de semana en el mes siguiente
    df_siguiente_mes = df_weekly[df_weekly.index.month == mes_siguiente]
    if len(df_siguiente_mes) > 0:
        semana_numero_siguiente = len(df_siguiente_mes) + 1
    else:
        semana_numero_siguiente = 1
    
    # Mapeo de meses
    mes_map = {
        1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
        5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
        9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
    }
    
    mes_nombre = mes_map[mes_siguiente]
    periodo_siguiente = f'{año_siguiente}_{mes_nombre}_semana{semana_numero_siguiente}'
    
    print(f"Siguiente semana a procesar: {periodo_siguiente}")
    
    # Generar las tablas y exportar PNGs (funcionalidad completa de a02.py)
    
    # Mapeo de métricas para display
    metric_map = {
        'spend': 'Total Spend',
        'messaging_started': 'WhatsApp Leads',
        'cpl': 'CPL',
        'ctr': 'CTR (todos)',
        'unique_link_clicks_ctr': 'CTR (links)',
        'ratio ctr (todos / links)': 'CTR (todos / links)',
        'ctr (todos / links)': 'CTR (todos / links)',
    }
    
    output_dir = os.path.join(BASE_DIR, "insight")
    out_pct = os.path.join(output_dir, 'tabla_variaciones.png')
    out_val = os.path.join(output_dir, 'tabla_valores.png')
    
    # Función para generar tabla de porcentajes
    def generar_tabla_por_periodo_pct(dfw: pd.DataFrame, map_period: pd.Series, periodo_label: str):
        if periodo_label not in map_period.index:
            raise KeyError(f"Periodo '{periodo_label}' no encontrado.")

        semana_inicio = pd.to_datetime(map_period.loc[periodo_label])
        df = dfw.copy().sort_index()
        df.index = pd.to_datetime(df.index)
        idx = df.index.get_loc(semana_inicio)
        fila_act = df.iloc[idx]

        def fila(idx_offset):
            pos = idx - idx_offset
            if 0 <= pos < len(df):
                return df.iloc[pos]
            return pd.Series({c: np.nan for c in df.columns})

        prev_week = fila(1)
        same_month = fila(4)
        same_year = fila(52)

        metricas = ['spend','messaging_started','cpl','ctr','unique_link_clicks_ctr']
        fa = fila_act[metricas].astype(float)
        pw = prev_week[metricas].astype(float)
        pm = same_month[metricas].astype(float)
        py = same_year[metricas].astype(float)

        def change_pct(a, b):
            if pd.isna(a) or pd.isna(b) or float(b) == 0.0:
                return np.nan
            return np.round((float(a) - float(b)) / float(b) * 100, 2)

        resumen = pd.DataFrame({
            "Métrica": metricas,
            "Semana Actual": [float(fa[m]) for m in metricas],
            "Cambio vs Semana Anterior (%)": [change_pct(fa[m], pw[m]) for m in metricas],
            "Cambio vs Misma Semana Mes Anterior (%)": [change_pct(fa[m], pm[m]) for m in metricas],
            "Cambio vs Misma Semana Año Anterior (%)": [change_pct(fa[m], py[m]) for m in metricas],
        })

        # Ratio CTR (todos / links)
        def safe_div(a, b):
            if pd.isna(a) or pd.isna(b) or float(b) == 0.0:
                return np.nan
            return float(a) / float(b)

        ratio_act = safe_div(fa['ctr'], fa['unique_link_clicks_ctr'])
        ratio_prev = safe_div(pw['ctr'], pw['unique_link_clicks_ctr'])
        ratio_month = safe_div(pm['ctr'], pm['unique_link_clicks_ctr'])
        ratio_year = safe_div(py['ctr'], py['unique_link_clicks_ctr'])

        ratio_row = {
            'Métrica': 'CTR (todos / links)',
            'Semana Actual': np.round(ratio_act, 2) if not pd.isna(ratio_act) else np.nan,
            'Cambio vs Semana Anterior (%)': change_pct(ratio_act, ratio_prev),
            'Cambio vs Misma Semana Mes Anterior (%)': change_pct(ratio_act, ratio_month),
            'Cambio vs Misma Semana Año Anterior (%)': change_pct(ratio_act, ratio_year),
        }

        resumen = pd.concat([resumen, pd.DataFrame([ratio_row])], ignore_index=True)
        return resumen

    # Función para generar tabla de valores
    def generar_tabla_por_periodo_valores(dfw: pd.DataFrame, map_period: pd.Series, periodo_label: str):
        if periodo_label not in map_period.index:
            raise KeyError(f"Periodo '{periodo_label}' no encontrado.")

        semana_inicio = pd.to_datetime(map_period.loc[periodo_label])
        df = dfw.copy().sort_index()
        df.index = pd.to_datetime(df.index)
        idx = df.index.get_loc(semana_inicio)
        fila_act = df.iloc[idx]

        def fila(idx_offset):
            pos = idx - idx_offset
            if 0 <= pos < len(df):
                return df.iloc[pos]
            return pd.Series({c: np.nan for c in df.columns})

        prev_week = fila(1)
        same_month = fila(4)
        same_year = fila(52)

        metricas = ['spend','messaging_started','cpl','ctr','unique_link_clicks_ctr']
        fa = fila_act[metricas].astype(float)
        pw = prev_week[metricas].astype(float)
        pm = same_month[metricas].astype(float)
        py = same_year[metricas].astype(float)

        resumen = pd.DataFrame({
            'Métrica': metricas,
            'Semana Actual': fa.values,
            'Semana Anterior': pw.values,
            'Misma Semana Mes Anterior': pm.values,
            'Misma Semana Año Anterior': py.values,
        })

        # Ratio CTR (todos / links)
        def safe_div(a, b):
            if pd.isna(a) or pd.isna(b) or float(b) == 0.0:
                return np.nan
            return float(a) / float(b)

        ratio_act = safe_div(fa['ctr'], fa['unique_link_clicks_ctr'])
        ratio_prev = safe_div(pw['ctr'], pw['unique_link_clicks_ctr'])
        ratio_month = safe_div(pm['ctr'], pm['unique_link_clicks_ctr'])
        ratio_year = safe_div(py['ctr'], py['unique_link_clicks_ctr'])

        ratio_row = {
            'Métrica': 'CTR (todos / links)',
            'Semana Actual': np.round(ratio_act, 4) if not pd.isna(ratio_act) else np.nan,
            'Semana Anterior': np.round(ratio_prev, 4) if not pd.isna(ratio_prev) else np.nan,
            'Misma Semana Mes Anterior': np.round(ratio_month, 4) if not pd.isna(ratio_month) else np.nan,
            'Misma Semana Año Anterior': np.round(ratio_year, 4) if not pd.isna(ratio_year) else np.nan,
        }

        resumen = pd.concat([resumen, pd.DataFrame([ratio_row])], ignore_index=True)
        return resumen

    # Función para exportar tablas como PNG
    def export_table_png(df_in: pd.DataFrame, output_path: str, metric_map: dict):
        df = df_in.copy().reset_index(drop=True)
        
        def map_display_name(v):
            kk = str(v).strip().lower()
            return metric_map.get(kk, v)

        df_display = df.copy()
        df_display['Métrica'] = df_display['Métrica'].apply(map_display_name)
        
        nrows, ncols = df_display.shape
        text_table = [df_display.columns.tolist()]
        
        percent_metrics = {"ctr", "unique_link_clicks_ctr"}
        
        for i, row in df_display.iterrows():
            row_txt = []
            mkey = str(df.loc[i, "Métrica"]).strip().lower()
            
            for col in df_display.columns:
                val = row[col]
                
                if col == "Métrica":
                    row_txt.append(str(val))
                    continue
                
                if pd.isna(val):
                    row_txt.append('')
                    continue
                
                if "(%)" in str(col):
                    try:
                        vf = float(val)
                        row_txt.append(f"{vf:,.2f}%")
                        continue
                    except Exception:
                        pass
                
                if mkey in percent_metrics:
                    try:
                        vf = float(val)
                        row_txt.append(f"{vf * 100:,.2f}%")
                        continue
                    except Exception:
                        pass
                
                if isinstance(val, (float, np.floating)):
                    row_txt.append(f"{val:,.2f}")
                elif isinstance(val, (int, np.integer)):
                    row_txt.append(f"{val:,d}")
                else:
                    try:
                        vf = float(str(val).replace('%', '').replace(',', '').strip())
                        row_txt.append(f"{vf:,.2f}")
                    except Exception:
                        row_txt.append(str(val))
            
            text_table.append(row_txt)
        
        fig_width = max(8, ncols * 1.5)
        fig_height = max(2 + nrows*0.5, 1.8 + nrows*0.45)
        
        plt.close('all')
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))
        ax.axis('off')
        
        table = ax.table(cellText=text_table, cellLoc='center', loc='center')
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 1.2)
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        plt.tight_layout()
        fig.savefig(output_path, dpi=200, bbox_inches='tight')
        plt.close(fig)
        return output_path

    # Generar tablas para la siguiente semana
    try:
        tabla_pct = generar_tabla_por_periodo_pct(df_weekly, map_period, periodo_siguiente)
        tabla_val = generar_tabla_por_periodo_valores(df_weekly, map_period, periodo_siguiente)
        
        # Exportar PNGs
        export_table_png(tabla_pct, out_pct, metric_map)
        export_table_png(tabla_val, out_val, metric_map)
        
        print(f"✅ Reporte semanal generado para: {periodo_siguiente}")
        print(f"📊 PNG de variaciones guardado en: {out_pct}")
        print(f"📊 PNG de valores guardado en: {out_val}")
        
    except Exception as e:
        print(f"Error generando reporte semanal: {e}")
        return
    
    # Aquí iría el resto del código de a02.py para generar el reporte
    print(f"\n=== Resumen ===")
    print(f"Período actual: {periodo_actual}")
    print(f"Siguiente período: {periodo_siguiente}")
    print(f"Última fecha en datos: {ultima_semana.date()}")

# Ejecutar la función de reporte semanal
if __name__ == "__main__":
    generar_reporte_semanal()

#---------------------------------------------------------------------------------------------
#                          Tercera Parte - Transformar a Power BI
#---------------------------------------------------------------------------------------------
# Variable global para Power BI Desktop - debe estar fuera de cualquier función
primera_tabla = None

def transformar_para_powerbi():
    """
    Transforma los datos crudos al formato requerido para Power BI
    Deja el dataframe final 'primera_tabla' disponible para Power BI Desktop
    """
    print("\n=== Iniciando transformación para Power BI ===")
    
    global primera_tabla  # Hacer disponible para Power BI
    
    try:
        # Leer el df original proveniente del reporte semanal 
        df = pd.read_csv(output_path, encoding='utf-8')
        print(f"CSV original leído: {len(df)} filas")
        
        # 1) Adaptar la columna 'date'
        # date -> date_start (date) y duplicamos a date_stop
        if 'date_start' not in df.columns:
            df['date_start'] = pd.to_datetime(df['date'], errors='coerce')
        else:
            df['date_start'] = pd.to_datetime(df['date_start'], errors='coerce')

        df['date_start'] = df['date_start'].dt.date
        df['date_stop'] = df['date_start']  # duplicado, como pediste

        # 2) Renombrar messaging_started -> first_replies (solo rename lógico)
        df = df.rename(columns={'messaging_started': 'first_replies'})
        
        # 3) Asegurar tipos numéricos donde aplica (evita errores de división / orden)
        for col in ['spend','impressions','reach','video_25pct','clicks_all','link_clicks','ctr',
                    'unique_link_clicks_ctr','messaging_conversation_started','two_way_conversations']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 4) Arreglar nombre de account
        df = df.rename(columns={'account_id':'account'})
        
        # 5) Construir el dataframe EXACTO para Power BI (faltantes -> NaN)
        required_cols = [
            'account',
            'date_start',
            'date_stop',
            'campaign_id',
            'campaign_name',
            'spend',
            'impressions',
            'reach',
            'video_25pct',
            'clicks_all',
            'link_clicks',
            'ctr',
            'unique_link_clicks_ctr',
            'first_replies',
            'two_way_conversations',
        ]

        for c in required_cols:
            if c not in df.columns:
                df[c] = np.nan

        primera_tabla = df[required_cols].copy()
        
        # Arreglar nombres de cuentas
        primera_tabla['account'] = primera_tabla['account'].replace('illapa','illa')
        
        print(f"✅ Transformación completada: {len(primera_tabla)} filas")
        print(f"📊 Columnas finales: {list(primera_tabla.columns)}")
        
        # Guardar CSV para Power BI (opcional, como backup)
        powerbi_path = os.path.join(BASE_DIR, "datasets", "data", "powerbi_ready.csv")
        os.makedirs(os.path.dirname(powerbi_path), exist_ok=True)
        primera_tabla.to_csv(powerbi_path, index=False, encoding='utf-8-sig', date_format='%Y-%m-%d')
        print(f"💾 CSV para Power BI guardado en: {powerbi_path}")
        
        # Mostrar información del dataframe para Power BI
        print(f"\n=== Información para Power BI ===")
        print(f"Nombre del dataframe: primera_tabla")
        print(f"Dimensiones: {primera_tabla.shape}")
        print(f"Tipos de datos:")
        print(primera_tabla.dtypes)
        print(f"\nPrimeras 3 filas:")
        print(primera_tabla.head(3))
        
        return primera_tabla
        
    except Exception as e:
        print(f"Error en transformación para Power BI: {e}")
        return None

# Ejecutar la transformación
if __name__ == "__main__":
    transformar_para_powerbi()
#--------------------------------------------------------------------------------------------- 
#                          Cuarta Parte - Generar Segunda Tabla (Ads Video Metrics)
#---------------------------------------------------------------------------------------------


# Variable global para Power BI Desktop - segunda tabla
segunda_tabla = None

def generar_segunda_tabla():
    """
    Extrae métricas de video a nivel de anuncios (ad level)
    Usa las mismas fechas y credenciales que la primera parte
    Deja el dataframe final 'segunda_tabla' disponible para Power BI Desktop
    """
    global segunda_tabla  # Hacer disponible para Power BI
    
    print("\n=== Iniciando extracción de métricas de video (nivel anuncio) ===")
    
    try:
        # Importar librería necesaria
        from facebook_business.exceptions import FacebookRequestError
        
        # Configuración (usar mismas fechas y credenciales que la primera parte)
        MAX_RETRIES = 3
        BACKOFF = 2
        PAUSE = 1.0
        
        FIELDS = [
            "ad_id",
            "campaign_id",
            "date_start",
            "impressions",
            "video_play_actions",
            "video_play_curve_actions",
            "video_p100_watched_actions",
        ]
        
        EXPECTED_COLUMNS = [
            "account",
            "ad_id",
            "campaign_id",
            "date_start",
            "impressions",
            "video_plays",
            "video_3s_views",
            "video_100pct_views",
            "retention_3s_pct",
            "retention_complete_pct",
            "thruplay",
            "curve_3s_pct_api",
        ]
        
        KEY_COLS = ["account", "ad_id", "campaign_id", "date_start"]
        
        # Output para segunda tabla
        OUTPUT_CSV_ADS = os.path.join(BASE_DIR, "datasets", "data", "campaign_video_3s_100pct_1d_ads.csv")
        
        # Usar mismas fechas que la primera parte
        print(f"Usando rango de fechas: {START_DATE} → {END_DATE}")
        
        # ---------------- HELPERS ----------------
        def daterange(start, end):
            d = start
            while d <= end:
                yield d
                d += timedelta(days=1)
        
        def fetch_day(ad_account, since, until):
            tries = 0
            while tries < MAX_RETRIES:
                tries += 1
                try:
                    ins = ad_account.get_insights(
                        fields=FIELDS,
                        params={
                            "time_range": {"since": since, "until": until},
                            "level": "ad",
                            "time_increment": 1,
                        },
                    )
                    return list(ins)
                except FacebookRequestError as e:
                    if "Error validating access token" in str(e):
                        print("ERROR: token inválido o expirado.")
                        raise
                    print(f"⚠️ Error API día {since}, intento {tries}/{MAX_RETRIES}: {e}")
                    time.sleep(BACKOFF * tries)
            print(f"❌ No se pudo obtener datos para {since}")
            return []
        
        def extract_stats(record):
            # 1) Total de reproducciones iniciadas (plays)
            video_plays_total = 0
            for v in record.get("video_play_actions", []) or []:
                if isinstance(v, dict) and v.get("action_type") == "video_view":
                    try:
                        video_plays_total += int(v.get("value", 0))
                    except:
                        pass
            
            # 2) Curva de retención: lista de % por segundo
            curve_values = []
            for entry in record.get("video_play_curve_actions", []) or []:
                if not isinstance(entry, dict):
                    continue
                if entry.get("action_type") != "video_view":
                    continue
                vals = entry.get("value", [])
                if isinstance(vals, list):
                    curve_values = vals
                break
            
            # % que llega al segundo 3
            if len(curve_values) > 3:
                try:
                    pct_3s = float(curve_values[3] or 0)
                except (TypeError, ValueError):
                    pct_3s = 0.0
            else:
                pct_3s = 0.0
            
            if video_plays_total > 0 and pct_3s > 0:
                video_3s_views = round(video_plays_total * (pct_3s / 100.0))
            else:
                video_3s_views = 0
            
            # 3) Vistas al 100%
            video_100pct_views = 0
            for v in record.get("video_p100_watched_actions", []) or []:
                if isinstance(v, dict) and v.get("action_type") == "video_view":
                    try:
                        video_100pct_views += int(v.get("value", 0))
                    except:
                        pass
            
            return video_3s_views, video_100pct_views, video_plays_total, pct_3s
        
        def read_existing_csv(path: str) -> pd.DataFrame:
            if not os.path.exists(path):
                print(f"ℹ️ No existe CSV previo: {path}. Se creará uno nuevo.")
                return pd.DataFrame(columns=EXPECTED_COLUMNS)
            
            df_old = pd.read_csv(path, encoding="utf-8-sig")
            # Normalizar columnas faltantes
            for c in EXPECTED_COLUMNS:
                if c not in df_old.columns:
                    df_old[c] = pd.NA
            
            # Normalizar date_start
            if "date_start" in df_old.columns:
                df_old["date_start"] = pd.to_datetime(df_old["date_start"], errors="coerce").dt.date
            
            # Asegurar tipos clave como string (evita mismatch en merges)
            for c in ["account", "ad_id", "campaign_id"]:
                if c in df_old.columns:
                    df_old[c] = df_old[c].astype("string")
            
            return df_old[EXPECTED_COLUMNS]
        
        def upsert_by_keys(df_old: pd.DataFrame, df_new: pd.DataFrame) -> pd.DataFrame:
            # Asegurar columnas esperadas
            for c in EXPECTED_COLUMNS:
                if c not in df_new.columns:
                    df_new[c] = pd.NA
            df_new = df_new[EXPECTED_COLUMNS]
            
            # Normalizar tipos clave
            for c in ["account", "ad_id", "campaign_id"]:
                df_new[c] = df_new[c].astype("string")
                df_old[c] = df_old[c].astype("string")
            
            df_new["date_start"] = pd.to_datetime(df_new["date_start"], errors="coerce").dt.date
            df_old["date_start"] = pd.to_datetime(df_old["date_start"], errors="coerce").dt.date
            
            # Concatenar + deduplicar quedándonos con el ÚLTIMO (df_new pisa df_old)
            combined = pd.concat([df_old, df_new], ignore_index=True)
            combined = combined.drop_duplicates(subset=KEY_COLS, keep="last")
            
            # Orden opcional (útil para Power BI)
            combined = combined.sort_values(by=["account", "date_start", "campaign_id", "ad_id"], kind="stable")
            
            return combined.reset_index(drop=True)
        
        # ---------------- MAIN EXTRACTION ----------------
        ad_level_records = []
        
        for account_id, label in account_map.items():
            acc = AdAccount(account_id)
            print(f"\n=== Cuenta {label} ({account_id}) ===")
            
            for d in daterange(START_DATE, END_DATE):
                since = d.isoformat()
                print(f"  -> Día {since} …")
                
                rows = fetch_day(acc, since, since)
                for r in rows:
                    impressions = int(r.get("impressions", 0) or 0)
                    video_3s, video_100pct, video_plays, pct_3s = extract_stats(r)
                    
                    retention_3s_pct = (video_3s / impressions) if impressions > 0 else 0
                    retention_complete_pct = (video_100pct / video_3s) if video_3s > 0 else 0
                    
                    ad_level_records.append({
                        "account": label,
                        "ad_id": r.get("ad_id"),
                        "campaign_id": r.get("campaign_id"),
                        "date_start": r.get("date_start"),
                        "impressions": impressions,
                        "video_plays": video_plays,
                        "video_3s_views": video_3s,
                        "video_100pct_views": video_100pct,
                        "retention_3s_pct": retention_3s_pct,
                        "retention_complete_pct": retention_complete_pct,
                        "thruplay": video_100pct,
                        "curve_3s_pct_api": pct_3s,
                    })
                
                time.sleep(PAUSE)
        
        if not ad_level_records:
            print("⚠️ No se recuperaron datos nuevos. No se modifica el CSV.")
            segunda_tabla = pd.DataFrame(columns=EXPECTED_COLUMNS)
            return segunda_tabla
        
        df_new = pd.DataFrame(ad_level_records)
        df_new["date_start"] = pd.to_datetime(df_new["date_start"], errors="coerce").dt.date
        
        # Leer CSV existente + upsert
        df_old = read_existing_csv(OUTPUT_CSV_ADS)
        df_final = upsert_by_keys(df_old, df_new)
        
        # Guardar SOBRESCRIBIENDO el mismo archivo
        df_final.to_csv(OUTPUT_CSV_ADS, index=False, encoding="utf-8-sig")
        print(f"\n✅ CSV de segunda tabla actualizado: {OUTPUT_CSV_ADS}")
        print("Filas final:", len(df_final))
        
        # Asignar a variable global para Power BI
        segunda_tabla = df_final
        
        print(f"\n=== Información para Power BI ===")
        print(f"Nombre del dataframe: segunda_tabla")
        print(f"Dimensiones: {segunda_tabla.shape}")
        print(f"Columnas: {list(segunda_tabla.columns)}")
        print(f"\nPrimeras 3 filas:")
        print(segunda_tabla.head(3))
        
        return segunda_tabla
        
    except Exception as e:
        print(f"Error en extracción de segunda tabla: {e}")
        traceback.print_exc()
        segunda_tabla = None
        return None

# Ejecutar la generación de segunda tabla
if __name__ == "__main__":
    generar_segunda_tabla()

#----------------------------------------------------------------------------------
#                        Quinta parte - Generar el excel
#----------------------------------------------------------------------------------

# gasto_mensual_2025.py
# ----------------- AJUSTES -----------------
CSV_PATH = os.path.join(BASE_DIR, "datasets", "data", "campaign_1d")
OUT_XLSX = os.path.join(BASE_DIR, "spend", "raw_spend_monthly_2026.xlsx")

# Métrica a agrupar (gastos)
SPEND_COL = 'spend'

# Opciones:
GROUP_BY_ACCOUNT = True   # True => genera resumen y (opcional) gráfico por account_id
GROUP_BY_CAMPAIGN = False # True => resume por campaign_name + mes
# -------------------------------------------

# Comprobaciones básicas
if not os.path.exists(CSV_PATH):
    raise FileNotFoundError(f"No encuentro el CSV en: {CSV_PATH}")

# Leer CSV y normalizar fecha
df = pd.read_csv(CSV_PATH, encoding='utf-8-sig', parse_dates=['date'], dayfirst=False)
df['date'] = pd.to_datetime(df['date']).dt.date  # queda tipo datetime.date

# Filtrar desde 2025-01-01
cutoff = date(2026, 1, 1)
df2025 = df[df['date'] >= cutoff].copy()

if df2025.empty:
    print("No hay registros desde 2025 en adelante. Revisa el CSV o el rango de fechas.")
    sys.exit(0)

# Crear columna month_start (primer día del mes como datetime) — útil para Excel
df2025['month_start'] = pd.to_datetime(df2025['date']).dt.to_period('M').dt.to_timestamp()

# Función para agregar por mes (y claves opcionales)
def aggregate_monthly(df_in, by_keys=None):
    """
    df_in: DataFrame con columna 'month_start'
    by_keys: list of extra keys to group by (e.g. ['account_id']) or None
    """
    group_keys = ['month_start']
    if by_keys:
        group_keys = by_keys + group_keys
    agg_dict = {}
    # Intentar agregar spend, impressions y clicks si existen
    if SPEND_COL in df_in.columns:
        agg_dict[SPEND_COL] = 'sum'
    if 'impressions' in df_in.columns:
        agg_dict['impressions'] = 'sum'
    # detectar clicks
    for c in ['clicks_all', 'clicks', 'link_clicks']:
        if c in df_in.columns:
            agg_dict[c] = 'sum'
            break
    df_agg = df_in.groupby(group_keys).agg(agg_dict).reset_index()
    # ordenar
    df_agg = df_agg.sort_values(group_keys).reset_index(drop=True)
    return df_agg

# 1) Resumen general por mes
df_monthly = aggregate_monthly(df2025, by_keys=None)

# 2) Resumen por account_id (opcional)
if GROUP_BY_ACCOUNT and 'account_id' in df2025.columns:
    df_monthly_by_account = aggregate_monthly(df2025, by_keys=['account_id'])
else:
    df_monthly_by_account = None

# 3) Resumen por campaign_name (opcional)
if GROUP_BY_CAMPAIGN and 'campaign_name' in df2025.columns:
    df_monthly_by_campaign = aggregate_monthly(df2025, by_keys=['campaign_name'])
else:
    df_monthly_by_campaign = None

# 4) Escribir a Excel con gráfico usando xlsxwriter
with pd.ExcelWriter(OUT_XLSX, engine='xlsxwriter', datetime_format='yyyy-mm-dd') as writer:
    # Hoja raw filtrada
    df2025.to_excel(writer, sheet_name='Filtered_2025plus', index=False)
    workbook  = writer.book

    # Hoja resumen mensual
    # Asegurarnos de que month_start sea datetime al escribir (xlsxwriter manejará bien)
    df_monthly.to_excel(writer, sheet_name='Monthly_Spend', index=False)
    ws = writer.sheets['Monthly_Spend']

    # Agregar formato de tabla
    nrows, ncols = df_monthly.shape
    header = [{'header': col} for col in df_monthly.columns]
    ws.add_table(0, 0, nrows, ncols - 1, {'columns': header, 'style': 'Table Style Medium 9'})

    # Crear gráfico: columnas (gasto por mes)
    chart = workbook.add_chart({'type': 'column'})
    # indices para xlsxwriter: (sheetname, first_row, first_col, last_row, last_col)
    # recordar que pandas escribió encabezados en la fila 0; datos comienzan en fila 1
    first_row = 1
    last_row = nrows
    # encontrar columna index de spend y month_start
    col_map = {c: i for i, c in enumerate(df_monthly.columns)}
    if SPEND_COL in col_map:
        chart.add_series({
            'name':       'Gasto (Spend)',
            'categories': ['Monthly_Spend', first_row, col_map['month_start'], last_row, col_map['month_start']],
            'values':     ['Monthly_Spend', first_row, col_map[SPEND_COL], last_row, col_map[SPEND_COL]],
            'gap': 2,
        })
    # formato del gráfico
    chart.set_title({'name': 'Gasto mensual (desde 2025)'})
    chart.set_x_axis({'name': 'Mes', 'date_axis': True, 'num_format': 'mmm yyyy'})
    chart.set_y_axis({'name': 'Gasto', 'major_gridlines': {'visible': False}})
    chart.set_legend({'position': 'bottom'})

    # Insertar gráfico en hoja resumen
    ws.insert_chart('H2', chart, {'x_scale': 1.4, 'y_scale': 1.4})

    # Escribir resumen por account_id si existe
    if df_monthly_by_account is not None:
        df_monthly_by_account.to_excel(writer, sheet_name='Monthly_by_Account', index=False)
        ws2 = writer.sheets['Monthly_by_Account']
        nr2, nc2 = df_monthly_by_account.shape
        header2 = [{'header': col} for col in df_monthly_by_account.columns]
        ws2.add_table(0, 0, nr2, nc2 - 1, {'columns': header2, 'style': 'Table Style Medium 9'})
        # (Opcional) crear un gráfico por cada account_id — si quieres descomentar el bloque siguiente.
        # Nota: si hay muchas cuentas, puede quedar pesado.
        # unique_accounts = df_monthly_by_account['account_id'].unique()
        # row_offset = 1
        # for acct in unique_accounts:
        #     df_ac = df_monthly_by_account[df_monthly_by_account['account_id'] == acct]
        #     if df_ac.empty: continue
        #     r_first = df_monthly_by_account.index[df_monthly_by_account['account_id'] == acct][0] + 1
        #     r_last = r_first + len(df_ac) - 1
        #     ch = workbook.add_chart({'type': 'column'})
        #     ch.add_series({
        #         'name': f'Gasto - {acct}',
        #         'categories': ['Monthly_by_Account', r_first, col_map['month_start'], r_last, col_map['month_start']],
        #         'values': ['Monthly_by_Account', r_first, col_map[SPEND_COL], r_last, col_map[SPEND_COL]],
        #     })
        #     ws2.insert_chart(1 + row_offset, nc2 + 2, ch)
        #     row_offset += 15

    # Escribir resumen por campaña si existe
    if df_monthly_by_campaign is not None:
        df_monthly_by_campaign.to_excel(writer, sheet_name='Monthly_by_Campaign', index=False)
        ws3 = writer.sheets['Monthly_by_Campaign']
        nr3, nc3 = df_monthly_by_campaign.shape
        header3 = [{'header': col} for col in df_monthly_by_campaign.columns]
        ws3.add_table(0, 0, nr3, nc3 - 1, {'columns': header3, 'style': 'Table Style Medium 9'})

print(f"✅ Archivo creado: {OUT_XLSX}")
print("Hojas incluidas: Filtered_2025plus, Monthly_Spend" +
      (", Monthly_by_Account" if df_monthly_by_account is not None else "") +
      (", Monthly_by_Campaign" if df_monthly_by_campaign is not None else ""))

