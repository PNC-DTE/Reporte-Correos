from collections import Counter
from datetime import date, datetime, timedelta
import io
import os
import re
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Configuración de página
st.set_page_config(
    page_title="Tablero Integral: DTE & Soporte Campus",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Estilos CSS con Identidad Oficial Chubut (Public Sans + Paleta Oficial)
st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;600;800&display=swap');

    html, body, [class*="css"], [class*="st-"] {
        font-family: 'Public Sans', sans-serif !important;
    }

    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, rgba(33, 112, 140, 0.15) 0%, rgba(15, 23, 42, 0.95) 100%);
        border: 1px solid rgba(255, 104, 44, 0.4);
        padding: 16px 20px;
        border-radius: 12px;
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35);
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        border-color: #ff682c;
    }
    div[data-testid="stMetricLabel"] p {
        font-size: 1.0rem !important;
        font-weight: 600 !important;
        color: #94a3b8 !important;
    }
    div[data-testid="stMetricValue"] div {
        font-size: 2.2rem !important;
        font-weight: 800 !important;
        color: #f8fafc !important;
    }

    div[data-testid="stTabs"] {
        margin-top: 10px;
        margin-bottom: 20px;
    }
    div[data-testid="stTabs"] [role="tablist"] {
        gap: 10px;
        border-bottom: 2px solid rgba(255, 255, 255, 0.1);
        padding-bottom: 4px;
    }
    div[data-testid="stTabs"] button[role="tab"] {
        height: 48px !important;
        padding: 0 22px !important;
        border-radius: 10px !important;
        background-color: #1e293b !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        transition: all 0.2s ease-in-out !important;
    }
    div[data-testid="stTabs"] button[role="tab"] p {
        font-size: 1.05rem !important;
        font-weight: 600 !important;
        color: #cbd5e1 !important;
    }
    div[data-testid="stTabs"] button[role="tab"]:hover {
        background-color: #21708c !important;
        border-color: #5894a7 !important;
    }
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        background: linear-gradient(135deg, #21708c 0%, #ff682c 100%) !important;
        border: 1px solid #ff8540 !important;
        box-shadow: 0 4px 16px rgba(255, 104, 44, 0.35) !important;
    }
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] p {
        color: #ffffff !important;
        font-weight: 800 !important;
    }
</style>
""",
    unsafe_allow_html=True,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CRED_PATH = os.path.join(BASE_DIR, "credentials.json")


# --- 1. CONEXIÓN CON GOOGLE SHEETS ---
@st.cache_resource
def obtener_cliente_gspread():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    # 1. En la nube: lee la configuración desde los Secrets de Streamlit
    if "gcp_service_account" in st.secrets:
        credenciales = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], scopes=scope
        )
    # 2. En local: busca el archivo credentials.json
    elif os.path.exists(CRED_PATH):
        credenciales = Credentials.from_service_account_file(
            CRED_PATH, scopes=scope
        )
    else:
        raise FileNotFoundError(
            "No se encontraron credenciales ni en st.secrets ni en credentials.json"
        )

    return gspread.authorize(credenciales)


# --- 2. CARGA Y PROCESAMIENTO ---
@st.cache_data(ttl=600, show_spinner=False)
def cargar_datos_combinados():
    client = obtener_cliente_gspread()

    ID_DTE = "1dUp3LaFdSg8NrUOyu53ojGsxxotjXI0iIbzysout_rY"
    ID_SOPORTE = "1eXkRicqc2oca_PHqbQUlVC5nvq3tV7guhW_CzGjpi5c"

    # DTE
    sh_dte = client.open_by_key(ID_DTE)
    df_dte = pd.DataFrame(sh_dte.worksheet("Datos_Mails").get_all_records())
    df_dte["Origen"] = "DTE"

    # Soporte Campus
    sh_soporte = client.open_by_key(ID_SOPORTE)
    df_soporte = pd.DataFrame(
        sh_soporte.worksheet("Datos_Mails").get_all_records()
    )
    df_soporte["Origen"] = "Soporte Campus"

    df = pd.concat([df_dte, df_soporte], ignore_index=True)

    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].astype(str)

    if "Fecha" in df.columns:
        df["Fecha_DT"] = pd.to_datetime(df["Fecha"], errors="coerce")
    else:
        df["Fecha_DT"] = pd.NaT

    # Normalización de Dirección (Entrada / Salida)
    if "Dirección (Entrada/Salida)" in df.columns:
        df["Dirección_Real"] = (
            df["Dirección (Entrada/Salida)"].str.strip().str.upper()
        )
    else:
        df["Dirección_Real"] = "ENTRADA"

    if "Remitente" in df.columns:
        es_salida = df["Remitente"].str.contains(
            r"pncusin@|soporte\.campus@|tecnologiaeducativa@",
            case=False,
            na=False,
        )
        df.loc[es_salida, "Dirección_Real"] = "SALIDA"

    if "Eje Temático Sugerido" in df.columns:
        df["Eje Temático Sugerido"] = (
            df["Eje Temático Sugerido"]
            .replace("", "Sin Clasificar")
            .fillna("Sin Clasificar")
        )

    return df


# --- 3. FUNCIONES DE ANÁLISIS SEMÁNTICO ---
STOPWORDS_ES = {
    "de", "la", "el", "en", "y", "a", "los", "las", "del", "un", "una", "unos", "unas",
    "por", "para", "con", "al", "o", "se", "lo", "su", "sus", "como", "mas", "pero",
    "sus", "le", "les", "me", "mi", "mis", "te", "ti", "tu", "tus", "nos", "que", "es",
    "son", "fue", "era", "sobre", "puedo", "puede", "podemos", "consulta", "consultas",
    "favor", "hola", "buen", "dia", "dias", "tardes", "noches", "saludos", "gracias",
    "adjunto", "solicitud", "pedido", "informe", "sin", "asunto", "re", "fwd", "rv", "fw",
    "dte", "campus", "chubut", "educacion", "virtual", "desde", "hasta", "hacer", "tener"
}


def limpiar_asunto_texto(asunto: str) -> str:
    if not isinstance(asunto, str) or not asunto.strip():
        return ""
    texto = re.sub(
        r"^(re|fwd|rv|fw|fwd:|\s*\[.*?\])\s*[:\-]\s*", "", asunto, flags=re.IGNORECASE
    )
    texto = re.sub(r"\[.*?\]|\(.*?\)", " ", texto)
    texto = re.sub(r"[^a-zA-ZáéíóúÁÉÍÓÚñÑ\s]", " ", texto)
    return texto.strip().lower()


def extraer_bigramas(serie_asuntos, top_n=10):
    bigramas = []
    for asunto in serie_asuntos:
        limpio = limpiar_asunto_texto(asunto)
        palabras = [p for p in limpio.split() if len(p) > 2 and p not in STOPWORDS_ES]
        if len(palabras) >= 2:
            for i in range(len(palabras) - 1):
                bigramas.append(f"{palabras[i]} {palabras[i+1]}")
    conteo = Counter(bigramas).most_common(top_n)
    return pd.DataFrame(conteo, columns=["Frase", "Frecuencia"])


def clasificar_motivo_asunto(asunto: str) -> str:
    texto = str(asunto).lower()
    if re.search(
        r"\b(contraseña|clave|password|usuario|login|bloqueo|bloquead|ingreso|acceso|acceder|blanqueo|restablecer)\b",
        texto,
    ):
        return "Credenciales y Login"
    if re.search(
        r"\b(matricular|matriculacion|inscripcion|inscribir|alta|baja|inscripto|anotarse)\b",
        texto,
    ):
        return "Matriculación y Usuarios"
    if re.search(
        r"\b(aula|curso|cohorte|materia|espacio|trayectoria|abrir aula|clase)\b",
        texto,
    ):
        return "Aulas Virtuales y Cursos"
    if re.search(
        r"\b(certificado|certificacion|constancia|acreditacion|asistencia)\b",
        texto,
    ):
        return "Certificados y Acreditación"
    if re.search(
        r"\b(driver|red|netbook|computadora|wifi|conectividad|pantalla|formateo|desbloqueo)\b",
        texto,
    ):
        return "Hardware y Conectividad"
    if re.search(
        r"\b(expediente|expte|nota|resolucion|circular|evaluacion|oferta|administrativ)\b",
        texto,
    ):
        return "Gestión Formal y Notas"
    return "Otras Consultas / General"


def detectar_urgencia(asunto: str) -> bool:
    texto = str(asunto).lower()
    return bool(
        re.search(
            r"\b(urgente|reclamo|error|grave|no funciona|caido|no puedo|alerta|invalido|ayuda)\b",
            texto,
        )
    )


# --- 4. BARRA LATERAL ---
st.sidebar.title("🏛️ Control de Datos")

if st.sidebar.button("🔄 Recargar datos desde Drive"):
    st.cache_data.clear()
    st.rerun()

try:
    with st.spinner("Cargando y unificando datos..."):
        df_raw = cargar_datos_combinados()
except Exception as e:
    st.error(f"Error de acceso: {e}")
    st.stop()

df = df_raw.copy()

if "Asunto" in df.columns:
    df["Motivo_Semantico"] = df["Asunto"].apply(clasificar_motivo_asunto)
    df["Es_Urgente"] = df["Asunto"].apply(detectar_urgencia)
else:
    df["Motivo_Semantico"] = "Sin Asunto"
    df["Es_Urgente"] = False

st.sidebar.markdown("---")
st.sidebar.header("🔍 Filtros Globales")

# Origen
origenes = ["Todos"] + sorted(df["Origen"].unique().tolist())
sel_origen = st.sidebar.selectbox("Bandeja / Origen:", origenes)
if sel_origen != "Todos":
    df = df[df["Origen"] == sel_origen]

# Período de Auditoría
st.sidebar.subheader("📅 Período de Auditoría")
hoy = datetime.now().date()
fechas_validas = df["Fecha_DT"].dropna()

if not fechas_validas.empty:
    min_dataset = fechas_validas.min().date()
    max_dataset = fechas_validas.max().date()
    max_permitido = max(hoy, max_dataset)
else:
    min_dataset = hoy - timedelta(days=180)
    max_permitido = hoy

opcion_fecha = st.sidebar.radio(
    "Selección rápida:",
    [
        "Desde inicio hasta Hoy",
        "Últimos 30 días",
        "Año en curso",
        "Rango Personalizado",
    ],
    index=0,
)

if opcion_fecha == "Desde inicio hasta Hoy":
    fecha_desde = min_dataset
    fecha_hasta = hoy
elif opcion_fecha == "Últimos 30 días":
    fecha_desde = hoy - timedelta(days=30)
    fecha_hasta = hoy
elif opcion_fecha == "Año en curso":
    fecha_desde = date(hoy.year, 1, 1)
    fecha_hasta = hoy
else:
    rango = st.sidebar.date_input(
        "Rango personalizado (Desde - Hasta):",
        value=(min_dataset, hoy),
        min_value=min_dataset,
        max_value=max_permitido,
    )
    if isinstance(rango, (list, tuple)) and len(rango) == 2:
        fecha_desde, fecha_hasta = rango[0], rango[1]
    else:
        fecha_desde, fecha_hasta = min_dataset, hoy

df = df[
    (df["Fecha_DT"].dt.date >= fecha_desde)
    & (df["Fecha_DT"].dt.date <= fecha_hasta)
]
st.sidebar.caption(f"Filtro activo: **{fecha_desde}** al **{fecha_hasta}**")

# Franja Horaria
if "Franja Horaria (8 a 14 hs)" in df.columns:
    franjas = ["Todas"] + sorted(
        [x for x in df["Franja Horaria (8 a 14 hs)"].dropna().unique() if str(x).strip()]
    )
    sel_franja = st.sidebar.selectbox("Franja Horaria:", franjas)
    if sel_franja != "Todas":
        df = df[df["Franja Horaria (8 a 14 hs)"] == sel_franja]


# --- 5. ENCABEZADO Y KPIS ---
st.title("🏛️ Tablero Integral: DTE & Soporte Campus")
st.caption(
    "Ministerio de Educación de Chubut · Dirección de Tecnología Educativa"
)

total_total = len(df)
total_dte = len(df[df["Origen"] == "DTE"])
total_soporte = len(df[df["Origen"] == "Soporte Campus"])

pct_en_horario = "N/A"
if "Franja Horaria (8 a 14 hs)" in df.columns and total_total > 0:
    en_turno = len(
        df[df["Franja Horaria (8 a 14 hs)"].str.contains("EN HORARIO", case=False, na=False)]
    )
    pct_en_horario = f"{(en_turno / total_total * 100):.1f}%"

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Interacciones", f"{total_total:,}")
c2.metric(
    "Bandeja DTE",
    f"{total_dte:,}",
    delta=f"{(total_dte/total_total*100 if total_total else 0):.1f}% del total",
)
c3.metric(
    "Bandeja Soporte",
    f"{total_soporte:,}",
    delta=f"{(total_soporte/total_total*100 if total_total else 0):.1f}% del total",
)
c4.metric(
    "Turno Oficial (8 a 14h)",
    pct_en_horario,
    help="Porcentaje atendido dentro del turno oficial matutino.",
)

st.markdown("---")


# --- 6. SOLAPAS ---
tab_general, tab_ejes, tab_asuntos, tab_informe, tab_datos = st.tabs([
    "📊 Visión General",
    "📑 Desglose por Ejes Temáticos",
    "🔍 Análisis Semántico de Asuntos",
    "📄 Informe Ejecutivo Formal",
    "📋 Registros y Exportación",
])


# ==========================================
# SOLAPA 1: VISIÓN GENERAL
# ==========================================
with tab_general:
    col_g1, col_g2 = st.columns([1.2, 0.88])

with col_g1:
        st.subheader("Distribución por Ejes Temáticos")
        if "Eje Temático Sugerido" in df.columns:
            df_ejes = df["Eje Temático Sugerido"].replace("", "Sin Clasificar").value_counts().reset_index()
            df_ejes.columns = ["Eje Temático", "Cantidad"]
            total_sum = df_ejes["Cantidad"].sum()
            df_ejes["Porcentaje"] = (df_ejes["Cantidad"] / total_sum * 100).round(1)
            df_ejes["Etiqueta"] = df_ejes.apply(
                lambda r: f" {r['Cantidad']:,} ({r['Porcentaje']}%) ", axis=1
            )
            df_ejes = df_ejes.sort_values(by="Cantidad", ascending=True)

            # Selector para calibrar la escala visual según la necesidad
            c_graf_title, c_escala = st.columns([1.8, 1.2])
            with c_escala:
                tipo_escala = st.radio(
                    "Modo de Escala:",
                    ["Normal (Lineal)", "Ajustada (Logarítmica)"],
                    horizontal=True,
                    index=0,
                    help="La escala logarítmica permite que las áreas con menos mensajes no se vean aplastadas respecto a Moodle."
                )
            usar_log = (tipo_escala == "Ajustada (Logarítmica)")

            fig_ejes = px.bar(
                df_ejes,
                x="Cantidad",
                y="Eje Temático",
                orientation="h",
                text="Etiqueta",
                color="Cantidad",
                color_continuous_scale=[
                    "#21708c",
                    "#5894a7",
                    "#ffc815",
                    "#ff8540",
                    "#ff682c",
                ],
                log_x=usar_log
            )
            fig_ejes.update_traces(
                textposition="outside",
                cliponaxis=False,
                textfont=dict(
                    color="#f8fafc",
                    size=12,
                    family="Public Sans, sans-serif",
                ),
            )
            fig_ejes.update_layout(
                xaxis_title="Cantidad de Mensajes" + (" [Escala Logarítmica]" if usar_log else " [Escala Lineal]"),
                yaxis_title="",
                coloraxis_showscale=False,
                margin=dict(l=10, r=100, t=10, b=20),
                height=380,
                xaxis=dict(
                    showgrid=True, 
                    gridcolor="rgba(255,255,255,0.08)",
                    # Si es logarítmica, formatea las marcas para que no se superpongan
                    dtick=1 if usar_log else None
                ),
            )
            st.plotly_chart(fig_ejes, width="stretch")

    

    with col_g2:
        st.subheader("Distribución por Franja Horaria")
        if "Franja Horaria (8 a 14 hs)" in df.columns:
            df_franja = df["Franja Horaria (8 a 14 hs)"].value_counts().reset_index()
            df_franja.columns = ["Franja", "Cantidad"]

            fig_franja = go.Figure(
                data=[
                    go.Pie(
                        labels=df_franja["Franja"],
                        values=df_franja["Cantidad"],
                        hole=0.55,
                        textinfo="percent",
                        textposition="inside",
                        insidetextorientation="horizontal",
                        marker=dict(
                            colors=[
                                "#21708c",
                                "#ff682c",
                                "#ffc815",
                                "#5894a7",
                                "#ff8540",
                            ],
                            line=dict(color="#0f172a", width=2),
                        ),
                        hoverinfo="label+value+percent",
                    )
                ]
            )
            fig_franja.update_layout(
                legend=dict(
                    orientation="v",
                    yanchor="middle",
                    y=0.5,
                    xanchor="left",
                    x=1.02,
                    font=dict(size=12, color="#cbd5e1", family="Public Sans, sans-serif"),
                ),
                margin=dict(l=10, r=10, t=10, b=20),
                height=380,
            )
            st.plotly_chart(fig_franja, width="stretch")

    st.markdown("---")

    st.subheader("Demanda Horaria: DTE vs Soporte Campus")
    col_hora = next((c for c in df.columns if "hora (0-23)" in c.lower()), None)
    if col_hora:
        df_hora = df.groupby([col_hora, "Origen"]).size().reset_index(name="Mensajes")
        fig_hora = px.line(
            df_hora,
            x=col_hora,
            y="Mensajes",
            color="Origen",
            markers=True,
            color_discrete_map={"DTE": "#21708c", "Soporte Campus": "#ff682c"},
        )
        fig_hora.update_xaxes(
            dtick=1,
            title_text="Hora del Día (0 a 23 hs)",
            gridcolor="rgba(255,255,255,0.06)",
        )
        fig_hora.update_yaxes(gridcolor="rgba(255,255,255,0.06)")
        fig_hora.update_layout(
            margin=dict(l=10, r=20, t=10, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=330,
        )
        st.plotly_chart(fig_hora, width="stretch")


# ==========================================
# SOLAPA 2: DESGLOSE POR EJES
# ==========================================
with tab_ejes:
    st.subheader("📑 Análisis Detallado por Eje Temático")

    if "Eje Temático Sugerido" in df.columns:
        ejes_unicos = sorted(df["Eje Temático Sugerido"].unique().tolist())
        opciones_ejes = ["TODOS (Vista Global)"] + ejes_unicos

        eje_seleccionado = st.selectbox(
            "Seleccioná un Eje Temático para analizar a fondo (o mantené 'TODOS' para ver el consolidado):",
            opciones_ejes,
            index=0,
        )

        es_total = eje_seleccionado == "TODOS (Vista Global)"
        df_eje = df.copy() if es_total else df[df["Eje Temático Sugerido"] == eje_seleccionado]

        total_eje = len(df_eje)
        dte_eje = len(df_eje[df_eje["Origen"] == "DTE"])
        soporte_eje = len(df_eje[df_eje["Origen"] == "Soporte Campus"])
        entradas_eje = len(df_eje[df_eje["Dirección_Real"] == "ENTRADA"])

        m1, m2, m3, m4 = st.columns(4)
        m1.metric(
            "Total Mensajes",
            f"{total_eje:,}",
            delta="100% de la selección" if es_total else f"{(total_eje/total_total*100 if total_total else 0):.1f}% del total",
        )
        m2.metric(
            "Proporción DTE",
            f"{dte_eje:,}",
            delta=f"{(dte_eje/total_eje*100 if total_eje else 0):.1f}%",
        )
        m3.metric(
            "Proporción Soporte",
            f"{soporte_eje:,}",
            delta=f"{(soporte_eje/total_eje*100 if total_eje else 0):.1f}%",
        )
        m4.metric(
            "Consultas Entrantes",
            f"{entradas_eje:,}",
            delta=f"{(entradas_eje/total_eje*100 if total_eje else 0):.1f}%",
        )

        st.markdown("---")

        c_eje_g1, c_eje_g2 = st.columns(2)

        with c_eje_g1:
            st.markdown(f"**Distribución por Origen — *{eje_seleccionado}***")
            fig_origen_eje = px.pie(
                df_eje,
                names="Origen",
                hole=0.48,
                color="Origen",
                color_discrete_map={"DTE": "#21708c", "Soporte Campus": "#ff682c"},
            )
            fig_origen_eje.update_traces(textinfo="percent+value")
            fig_origen_eje.update_layout(margin=dict(l=10, r=10, t=10, b=20), height=340)
            st.plotly_chart(fig_origen_eje, width="stretch")

        with c_eje_g2:
            if es_total:
                st.markdown("**Comparativa de Volumen por Eje Temático**")
                df_barras_ejes = df["Eje Temático Sugerido"].value_counts().reset_index()
                df_barras_ejes.columns = ["Eje Temático", "Cantidad"]
                total_b = df_barras_ejes["Cantidad"].sum()
                df_barras_ejes["Etiqueta"] = df_barras_ejes.apply(
                    lambda r: f" {r['Cantidad']:,} ({(r['Cantidad']/total_b*100):.1f}%) ",
                    axis=1,
                )
                df_barras_ejes = df_barras_ejes.sort_values(by="Cantidad", ascending=True)

                fig_barras_ejes = px.bar(
                    df_barras_ejes,
                    x="Cantidad",
                    y="Eje Temático",
                    orientation="h",
                    text="Etiqueta",
                    color="Cantidad",
                    color_continuous_scale=[
                        "#21708c",
                        "#5894a7",
                        "#ffc815",
                        "#ff8540",
                        "#ff682c",
                    ],
                )
                fig_barras_ejes.update_traces(
                    textposition="outside",
                    cliponaxis=False,
                    textfont=dict(color="#f8fafc", size=11, family="Public Sans, sans-serif"),
                )
                fig_barras_ejes.update_layout(
                    coloraxis_showscale=False,
                    xaxis_title="Mensajes",
                    yaxis_title="",
                    margin=dict(l=10, r=80, t=10, b=20),
                    height=340,
                    xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)"),
                )
                st.plotly_chart(fig_barras_ejes, width="stretch")
            else:
                st.markdown(f"**Franja Horaria — *{eje_seleccionado}***")
                if "Franja Horaria (8 a 14 hs)" in df_eje.columns:
                    df_fh_eje = df_eje["Franja Horaria (8 a 14 hs)"].value_counts().reset_index()
                    df_fh_eje.columns = ["Franja", "Cantidad"]
                    fig_fh_eje = px.bar(
                        df_fh_eje,
                        x="Franja",
                        y="Cantidad",
                        color="Franja",
                        color_discrete_sequence=["#21708c", "#ff682c", "#ffc815", "#5894a7"],
                        text="Cantidad",
                    )
                    fig_fh_eje.update_traces(textposition="outside")
                    fig_fh_eje.update_layout(
                        showlegend=False,
                        margin=dict(l=10, r=10, t=10, b=20),
                        height=340,
                        yaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
                    )
                    st.plotly_chart(fig_fh_eje, width="stretch")

        st.markdown(f"**Registros clasificados en: *{eje_seleccionado}* (muestra de 50):**")
        cols_eje_ver = [
            c for c in [
                "Origen",
                "Fecha",
                "Hora Exacta",
                "Remitente",
                "Asunto",
                "Eje Temático Sugerido",
                "Franja Horaria (8 a 14 hs)",
            ] if c in df_eje.columns
        ]
        st.dataframe(df_eje[cols_eje_ver].head(50), width="stretch")


# ==========================================
# SOLAPA 3: ANÁLISIS SEMÁNTICO DE ASUNTOS
# ==========================================
with tab_asuntos:
    st.subheader("🔍 Diagnóstico Semántico de Asuntos y Demanda")
    st.caption("Clasificación de motivos concretos, detección de urgencias, frases clave y búsqueda libre.")

    total_urgentes = int(df["Es_Urgente"].sum())
    motivos_df = df["Motivo_Semantico"].value_counts().reset_index()
    motivos_df.columns = ["Motivo", "Cantidad"]

    motivo_top = motivos_df.iloc[0]["Motivo"] if not motivos_df.empty else "N/A"
    motivo_top_qty = motivos_df.iloc[0]["Cantidad"] if not motivos_df.empty else 0

    s1, s2, s3 = st.columns(3)
    s1.metric("Motivo Más Recurrente", motivo_top, f"{motivo_top_qty:,} consultas")
    s2.metric(
        "Alertas / Fricción Detectada",
        f"{total_urgentes:,}",
        delta="Casos con términos de error o urgencia",
        delta_color="inverse",
    )
    s3.metric(
        "Tasa de Clasificación Específica",
        f"{((len(df[df['Motivo_Semantico'] != 'Otras Consultas / General']) / len(df) * 100) if len(df) else 0):.1f}%",
        help="Porcentaje de correos cuyo asunto contiene motivos técnicos directos identificados.",
    )

    st.markdown("---")

    col_a1, col_a2 = st.columns([1.1, 0.9])

    with col_a1:
        st.markdown("**1. Distribución de Motivos Operativos Detectados**")
        fig_motivos = px.bar(
            motivos_df.sort_values(by="Cantidad", ascending=True),
            x="Cantidad",
            y="Motivo",
            orientation="h",
            color="Cantidad",
            color_continuous_scale=["#ffc815", "#ffb109", "#ff8540", "#ff682c"],
            text="Cantidad",
        )
        fig_motivos.update_traces(textposition="outside")
        fig_motivos.update_layout(
            margin=dict(l=10, r=40, t=10, b=20),
            coloraxis_showscale=False,
            height=340,
            xaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
        )
        st.plotly_chart(fig_motivos, width="stretch")

    with col_a2:
        st.markdown("**2. Top 10 Frases Compuestas en Asuntos (Bigramas)**")
        df_bigramas = extraer_bigramas(df["Asunto"], top_n=10)
        if not df_bigramas.empty:
            fig_bi = px.bar(
                df_bigramas.sort_values(by="Frecuencia", ascending=True),
                x="Frecuencia",
                y="Frase",
                orientation="h",
                color="Frecuencia",
                color_continuous_scale=["#5894a7", "#21708c"],
                text="Frecuencia",
            )
            fig_bi.update_traces(textposition="outside")
            fig_bi.update_layout(
                margin=dict(l=10, r=40, t=10, b=20),
                coloraxis_showscale=False,
                height=340,
                xaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
            )
            st.plotly_chart(fig_bi, width="stretch")
        else:
            st.info("No se hallaron suficientes frases compuestas en los asuntos filtrados.")

    st.markdown("---")

    st.subheader("🔎 Explorador Interactivo de Casos")
    c_filtro1, c_filtro2, c_filtro3 = st.columns([1.2, 1.8, 1.0])

    with c_filtro1:
        opciones_motivos = ["TODOS LOS MOTIVOS", "⚠️ SOLO ALERTAS Y URGENCIAS"] + sorted(df["Motivo_Semantico"].unique().tolist())
        sel_motivo = st.selectbox("Filtrar por Motivo:", opciones_motivos)

    with c_filtro2:
        texto_busqueda = st.text_input(
            "Buscar por texto libre:",
            placeholder="Ej: driver, contraseña, evaluación, epja, certificado, santana...",
            help="Busca palabras o fragmentos de texto exactos dentro del asunto o remitente.",
        )

    with c_filtro3:
        campo_busqueda = st.selectbox(
            "Buscar en:",
            ["Solo Asunto", "Asunto y Remitente", "Solo Remitente"],
            index=0,
        )

    if sel_motivo == "TODOS LOS MOTIVOS":
        df_sub = df.copy()
    elif sel_motivo == "⚠️ SOLO ALERTAS Y URGENCIAS":
        df_sub = df[df["Es_Urgente"]]
    else:
        df_sub = df[df["Motivo_Semantico"] == sel_motivo]

    if texto_busqueda.strip():
        termino = texto_busqueda.strip()
        if campo_busqueda == "Solo Asunto":
            df_sub = df_sub[df_sub["Asunto"].str.contains(termino, case=False, na=False)]
        elif campo_busqueda == "Solo Remitente":
            df_sub = df_sub[df_sub["Remitente"].str.contains(termino, case=False, na=False)]
        else:
            df_sub = df_sub[
                df_sub["Asunto"].str.contains(termino, case=False, na=False)
                | df_sub["Remitente"].str.contains(termino, case=False, na=False)
            ]

    total_coincidencias = len(df_sub)
    if texto_busqueda.strip():
        st.info(f"🎯 Se encontraron **{total_coincidencias:,}** mensajes con el término *'{texto_busqueda.strip()}'*.")
    else:
        st.caption(f"Mostrando **{total_coincidencias:,}** registros según los criterios seleccionados.")

    cols_asunto_view = [
        c for c in [
            "Origen",
            "Fecha",
            "Hora Exacta",
            "Remitente",
            "Asunto",
            "Motivo_Semantico",
            "Franja Horaria (8 a 14 hs)",
        ] if c in df_sub.columns
    ]
    st.dataframe(df_sub[cols_asunto_view].head(150), width="stretch")


# ==========================================
# SOLAPA 4: INFORME EJECUTIVO FORMAL DINÁMICO
# ==========================================
with tab_informe:
    st.subheader("📄 Generación de Informe Ejecutivo Dinámico")
    st.caption("Consolida los hallazgos cuantitativos, la sobrecarga asincrónica y las recomendaciones estratégicas calculadas sobre el período y filtros activos.")

    # Cálculos dinámicos para el informe en base al df filtrado actual
    n_total = len(df)
    n_dte = len(df[df["Origen"] == "DTE"])
    n_soporte = len(df[df["Origen"] == "Soporte Campus"])
    n_entradas = len(df[df["Dirección_Real"] == "ENTRADA"])
    n_salidas = len(df[df["Dirección_Real"] == "SALIDA"])

    # Cálculos horarios
    col_fh = "Franja Horaria (8 a 14 hs)"
    if col_fh in df.columns and n_total > 0:
        c_en_horario = len(df[df[col_fh].str.contains("EN HORARIO", case=False, na=False)])
        c_despues14 = len(df[df[col_fh].str.contains("DESPUES|DESPUÉS", case=False, na=False)])
        c_antes08 = len(df[df[col_fh].str.contains("ANTES", case=False, na=False)])
        c_finsemana = len(df[df[col_fh].str.contains("FIN", case=False, na=False)])
        c_fuera = c_despues14 + c_antes08 + c_finsemana
    else:
        c_en_horario, c_despues14, c_antes08, c_finsemana, c_fuera = 0, 0, 0, 0, 0

    pct_fuera = (c_fuera / n_total * 100) if n_total > 0 else 0
    pct_en = (c_en_horario / n_total * 100) if n_total > 0 else 0
    pct_desp = (c_despues14 / n_total * 100) if n_total > 0 else 0
    pct_fin = (c_finsemana / n_total * 100) if n_total > 0 else 0

    # Desglose de ejes
    if "Eje Temático Sugerido" in df.columns:
        s_ejes = df["Eje Temático Sugerido"].value_counts()
        eje_moodle_qty = s_ejes.get("Soporte Moodle / Usuarios y Aulas", 0)
        eje_moodle_pct = (eje_moodle_qty / n_total * 100) if n_total > 0 else 0
        top_eje_nombre = s_ejes.index[0] if not s_ejes.empty else "N/A"
        top_eje_val = s_ejes.iloc[0] if not s_ejes.empty else 0
        top_eje_pct = (top_eje_val / n_total * 100) if n_total > 0 else 0
    else:
        eje_moodle_qty, eje_moodle_pct, top_eje_nombre, top_eje_val, top_eje_pct = 0, 0, "N/A", 0, 0

    # Motivos
    if "Motivo_Semantico" in df.columns:
        s_mot = df["Motivo_Semantico"].value_counts()
        login_qty = s_mot.get("Credenciales y Login", 0)
        login_pct = (login_qty / n_total * 100) if n_total > 0 else 0
        urgencias_qty = int(df["Es_Urgente"].sum())
        urgencias_pct = (urgencias_qty / n_total * 100) if n_total > 0 else 0
    else:
        login_qty, login_pct, urgencias_qty, urgencias_pct = 0, 0, 0, 0

    col_btn1, col_btn2 = st.columns([1.5, 2.5])
    with col_btn1:
        generar_click = st.button("📊 Generar / Actualizar Informe Ejecutivo", type="primary")

    # Contenedor de visualización del informe
    if "informe_generado" not in st.session_state:
        st.session_state["informe_generado"] = True

    if st.session_state["informe_generado"]:
        # Tarjetas de resumen para el informe
        st.markdown("---")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Universo Auditado", f"{n_total:,} mails")
        k2.metric("Demanda Asincrónica", f"{pct_fuera:.1f}%", f"{c_fuera:,} fuera de turno", delta_color="inverse")
        k3.metric("Concentración en Moodle", f"{eje_moodle_pct:.1f}%", f"{eje_moodle_qty:,} casos")
        k4.metric("Incidentes de Login / Clave", f"{login_pct:.1f}%", f"{login_qty:,} trámites")

        # HTML del informe formal institucional con estilos de impresión A4
        html_informe = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<style>
    @import url('https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;600;800&display=swap');
    body {{
        font-family: 'Public Sans', sans-serif;
        color: #1e293b;
        background-color: #ffffff;
        margin: 0;
        padding: 24px;
        line-height: 1.5;
    }}
    .header {{
        border-bottom: 3px solid #21708c;
        padding-bottom: 12px;
        margin-bottom: 24px;
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
    }}
    .title {{
        font-size: 20pt;
        font-weight: 800;
        color: #21708c;
        margin: 0;
    }}
    .subtitle {{
        font-size: 11pt;
        color: #ff682c;
        font-weight: 600;
        margin: 4px 0 0 0;
    }}
    .meta-box {{
        background: #f1f5f9;
        border-left: 4px solid #ff682c;
        padding: 10px 14px;
        margin-bottom: 20px;
        font-size: 9.5pt;
    }}
    .grid-kpis {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin-bottom: 24px;
    }}
    .kpi-card {{
        background: #f8fafc;
        border: 1px solid #cbd5e1;
        border-top: 4px solid #21708c;
        border-radius: 6px;
        padding: 12px;
        text-align: center;
    }}
    .kpi-card.accent {{
        border-top-color: #ff682c;
    }}
    .kpi-num {{
        font-size: 18pt;
        font-weight: 800;
        color: #0f172a;
    }}
    .kpi-lbl {{
        font-size: 8.5pt;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
    }}
    h2 {{
        font-size: 13pt;
        font-weight: 800;
        color: #21708c;
        border-bottom: 1px solid #e2e8f0;
        padding-bottom: 6px;
        margin-top: 24px;
    }}
    p, li {{
        font-size: 10pt;
        color: #334155;
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
        margin: 14px 0;
        font-size: 9.5pt;
    }}
    th {{
        background-color: #21708c;
        color: #ffffff;
        font-weight: 600;
        text-align: left;
        padding: 8px 10px;
    }}
    td {{
        padding: 8px 10px;
        border-bottom: 1px solid #e2e8f0;
    }}
    tr:nth-child(even) td {{
        background-color: #f8fafc;
    }}
    .footer {{
        margin-top: 36px;
        padding-top: 12px;
        border-top: 1px solid #cbd5e1;
        font-size: 8.5pt;
        color: #64748b;
        text-align: center;
    }}
</style>
</head>
<body>
    <div class="header">
        <div>
            <div class="title">INFORME EJECUTIVO DE AUDITORÍA Y TELEMETRÍA</div>
            <div class="subtitle">Dirección de Tecnología Educativa · Ministerio de Educación de Chubut</div>
        </div>
        <div style="text-align: right; font-size: 9pt; color: #64748b;">
            Emisión: <strong>{datetime.now().strftime("%d/%m/%Y %H:%M")}</strong>
        </div>
    </div>

    <div class="meta-box">
        <strong>Período evaluado:</strong> {fecha_desde} al {fecha_hasta} | 
        <strong>Filtro de Bandeja:</strong> {sel_origen} | 
        <strong>Cuentas involucradas:</strong> pncusin@educacionvirtual.chubut.edu.ar (DTE) y soporte.campus@educacionvirtual.chubut.edu.ar (Soporte Campus)
    </div>

    <div class="grid-kpis">
        <div class="kpi-card">
            <div class="kpi-num">{n_total:,}</div>
            <div class="kpi-lbl">Total Interacciones</div>
        </div>
        <div class="kpi-card accent">
            <div class="kpi-num">{pct_fuera:.1f}%</div>
            <div class="kpi-lbl">Fuera de Turno ({c_fuera:,})</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-num">{eje_moodle_pct:.1f}%</div>
            <div class="kpi-lbl">Foco Moodle ({eje_moodle_qty:,})</div>
        </div>
        <div class="kpi-card accent">
            <div class="kpi-num">{login_pct:.1f}%</div>
            <div class="kpi-lbl">Login y Claves ({login_qty:,})</div>
        </div>
    </div>

    <h2>1. Síntesis Diagnóstica y Resumen Ejecutivo</h2>
    <p>
        El presente relevamiento técnico analiza un universo de <strong>{n_total:,} interacciones</strong> procesadas por la Dirección de Tecnología Educativa y el Soporte Campus. 
        De las consultas registradas, <strong>{n_entradas:,}</strong> corresponden a demandas directas de la comunidad educativa (docentes, directivos y estudiantes) y <strong>{n_salidas:,}</strong> a intervenciones y resoluciones técnicas emitidas por el equipo.
    </p>

    <h2>2. Análisis de Hiperconectividad y Demanda Asincrónica</h2>
    <p>
        La jornada administrativa oficial del Ministerio de Educación está estipulada de <strong>08:00 a 14:00 horas</strong>. La telemetría arroja los siguientes comportamientos temporales:
    </p>
    <table>
        <thead>
            <tr>
                <th>Franja Horaria</th>
                <th>Volumen de Mails</th>
                <th>Proporción (%)</th>
                <th>Impacto Operativo</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>Horario Oficial (08:00 a 14:00 hs)</strong></td>
                <td>{c_en_horario:,}</td>
                <td>{pct_en:.1f}%</td>
                <td>Turno regular de atención y gestión sincrónica.</td>
            </tr>
            <tr>
                <td><strong>Tarde / Noche (después de las 14:00 hs)</strong></td>
                <td>{c_despues14:,}</td>
                <td>{pct_desp:.1f}%</td>
                <td>Sobrecarga asincrónica derivada de la actividad docente a contraturno.</td>
            </tr>
            <tr>
                <td><strong>Fines de semana y feriados</strong></td>
                <td>{c_finsemana:,}</td>
                <td>{pct_fin:.1f}%</td>
                <td>Demandas en días no laborables acumuladas para el lunes matutino.</td>
            </tr>
            <tr>
                <td><strong>Madrugada (antes de las 08:00 hs)</strong></td>
                <td>{c_antes08:,}</td>
                <td>{(c_antes08/n_total*100 if n_total else 0):.1f}%</td>
                <td>Ingresos previos a la apertura de las sedes escolares.</td>
            </tr>
            <tr style="font-weight: 700; background-color: #fee2e2;">
                <td>TOTAL ASINCRÓNICO / FUERA DE TURNO</td>
                <td>{c_fuera:,}</td>
                <td>{pct_fuera:.1f}%</td>
                <td>Carga acumulada que presiona el inicio de cada jornada laboral.</td>
            </tr>
        </tbody>
    </table>

    <h2>3. Concentración Temática y Análisis Semántico de Causas</h2>
    <p>
        El eje <strong>{top_eje_nombre}</strong> absorbe la mayor proporción de la capacidad de respuesta con <strong>{top_eje_val:,} consultas ({top_eje_pct:.1f}%)</strong>.
    </p>
    <ul>
        <li><strong>Fricción en Credenciales y Acceso:</strong> Se detectaron <strong>{login_qty:,} trámites ({login_pct:.1f}%)</strong> vinculados directamente con contraseñas olvidadas, blanqueo de usuarios y dificultades de inicio de sesión.</li>
        <li><strong>Criticidad y Urgencias:</strong> Se identificaron <strong>{urgencias_qty:,} casos ({urgencias_pct:.1f}%)</strong> con palabras explícitas de fricción (<em>error, urgente, no funciona, no puedo</em>), que requieren priorización en la cola de respuesta.</li>
    </ul>

    <h2>4. Conclusiones y Propuestas de Optimización</h2>
    <ol>
        <li><strong>Implementación de Autoservicio de Claves:</strong> Dado que el {login_pct:.1f}% de las solicitudes son reseteos de credenciales, habilitar un mecanismo automatizado de recuperación por correo o DNI liberaría hasta 4 de cada 10 horas hombre del área técnica.</li>
        <li><strong>Estructuración de Mesa de Ayuda (Ticketing):</strong> Migrar la casilla abierta a un formulario web con campos obligatorios (DNI, Escuela, Rol, Captura del error) para eliminar el intercambio reiterado de aclaraciones y reducir drásticamente el tiempo de resolución.</li>
        <li><strong>Pautas de Desconexión y Turnos Flexibles:</strong> El {pct_fuera:.1f}% de demanda fuera de turno evidencia que la comunidad docente utiliza el campus intensivamente por la tarde y noche; convendría evaluar esquemas de guardia técnica o respuestas programadas automáticas informando los horarios de intervención efectiva.</li>
    </ol>

    <div class="footer">
        Documento generado automáticamente desde el Tablero de Telemetría · DTE Chubut · Rawson, Chubut
    </div>
</body>
</html>
"""

        # Vista previa formateada dentro de Streamlit
        st.markdown(
            f"""
            <div style="background-color: #1e293b; border: 1px solid rgba(255,104,44,0.4); border-radius: 12px; padding: 22px; margin-top: 15px;">
                <h3 style="color: #ff682c; margin-top:0;">📋 Resumen de Hallazgos Clave ({fecha_desde} al {fecha_hasta})</h3>
                <ul style="color: #cbd5e1; font-size: 1.05rem; line-height: 1.7;">
                    <li><strong>Volumen auditado:</strong> <b>{n_total:,}</b> mensajes ({n_dte:,} en DTE y {n_soporte:,} en Soporte Campus).</li>
                    <li><strong>Sobrecarga asincrónica (fuera de 08 a 14 hs):</strong> <b>{pct_fuera:.1f}%</b> ({c_fuera:,} correos). El <b>{pct_desp:.1f}%</b> entra después de las 14:00 hs y el <b>{pct_fin:.1f}%</b> durante fines de semana.</li>
                    <li><strong>Hiperconcentración en Moodle:</strong> El eje <i>{top_eje_nombre}</i> representa el <b>{top_eje_pct:.1f}%</b> de la demanda total.</li>
                    <li><strong>Problemas de Acceso / Credenciales:</strong> <b>{login_qty:,} consultas ({login_pct:.1f}%)</b> corresponden a olvido o bloqueo de contraseñas.</li>
                    <li><strong>Alertas de fricción / urgencia:</strong> <b>{urgencias_qty:,}</b> mensajes ({urgencias_pct:.1f}%) con términos críticos.</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("<br>", unsafe_allow_html=True)

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.download_button(
                label="📥 Descargar Informe Completo en HTML (Imprimible / Guardar en PDF)",
                data=html_informe,
                file_name=f"Informe_Ejecutivo_DTE_Soporte_{datetime.now().strftime('%Y%m%d')}.html",
                mime="text/html",
                help="Podés abrir este archivo en Chrome o Edge y presionar Ctrl+P para guardarlo directamente como un PDF con formato oficial.",
            )

        with col_d2:
            resumen_txt = f"""INFORME EJECUTIVO - TELEMETRÍA DTE & SOPORTE CAMPUS
Período: {fecha_desde} al {fecha_hasta} | Bandeja: {sel_origen}
Total Mensajes: {n_total} (DTE: {n_dte} | Soporte: {n_soporte})
Entradas: {n_entradas} | Salidas: {n_salidas}
Turno Oficial (08 a 14 hs): {c_en_horario} ({pct_en:.1f}%)
Fuera de Horario / Asincrónico: {c_fuera} ({pct_fuera:.1f}%)
  - Después de las 14 hs: {c_despues14} ({pct_desp:.1f}%)
  - Fines de semana: {c_finsemana} ({pct_fin:.1f}%)
  - Antes de las 08 hs: {c_antes08}
Principal Eje: {top_eje_nombre} ({top_eje_val} casos - {top_eje_pct:.1f}%)
Casos de Credenciales/Login: {login_qty} ({login_pct:.1f}%)
Casos con Alertas/Urgencias: {urgencias_qty} ({urgencias_pct:.1f}%)
"""
            st.download_button(
                label="📄 Descargar Resumen Ejecutivo en Texto Plano (.txt)",
                data=resumen_txt,
                file_name=f"Resumen_Ejecutivo_{datetime.now().strftime('%Y%m%d')}.txt",
                mime="text/plain",
            )


# ==========================================
# SOLAPA 5: REGISTROS Y EXPORTACIÓN
# ==========================================
with tab_datos:
    st.subheader("📋 Base Consolidada Filtrada")

    cols_export = [
        c
        for c in [
            "Origen",
            "Fecha",
            "Hora Exacta",
            "Dirección_Real",
            "Franja Horaria (8 a 14 hs)",
            "Remitente",
            "Destinatario",
            "Asunto",
            "Motivo_Semantico",
            "Eje Temático Sugerido",
        ]
        if c in df.columns
    ]
    st.dataframe(df[cols_export], width="stretch")

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df[cols_export].to_excel(writer, index=False, sheet_name="Datos_Consolidados")
    buffer.seek(0)

    st.download_button(
        label="📥 Descargar datos filtrados en Excel (.xlsx)",
        data=buffer,
        file_name="Auditoria_Consolidada_DTE_Soporte.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
