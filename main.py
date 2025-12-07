import streamlit as st
import pandas as pd
import io
import difflib
import plotly.express as px
import plotly.graph_objects as go

# --- Configuration ---
st.set_page_config(
    page_title="Análisis Comparativo - Autopartes",
    page_icon="🚗",
    layout="wide"
)

# --- Utilities ---

def clean_price(val):
    """
    Cleans a price value to ensure it's a float.
    Handles strings with currency symbols, commas, etc.
    """
    if pd.isna(val) or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    
    # Convert to string and clean
    s = str(val)
    # Remove non-numeric characters except dot and minus
    # This is a simple regex replacement
    import re
    cleaned = re.sub(r'[^0-9.-]', '', s)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

def normalize_columns(df):
    """
    Attempts to normalize column names to standard keys: 'Clave', 'Descripcion', 'Precio'.
    Returns the renamed DataFrame and a success flag.
    """
    df.columns = df.columns.astype(str).str.strip()
    
    col_map = {}
    
    # Find Clave
    clave_cols = ['Clave', 'clave', 'CLAVE', 'Codigo', 'codigo', 'SKU', 'sku']
    for c in clave_cols:
        if c in df.columns:
            col_map[c] = 'Clave'
            break
            
    # Find Descripcion
    desc_cols = ['Descripción', 'Descripcion', 'descripcion', 'Nombre', 'nombre']
    for c in desc_cols:
        if c in df.columns:
            col_map[c] = 'Descripcion'
            break
            
    # Find Precio
    price_cols = ['Precio', 'precio', 'PRECIO', 'Costo', 'costo']
    for c in price_cols:
        if c in df.columns:
            col_map[c] = 'Precio'
            break
            
    if 'Clave' not in col_map.values():
        return df, False
        
    df = df.rename(columns=col_map)
    
    # Ensure required columns exist (fill with defaults if missing, except Clave)
    if 'Descripcion' not in df.columns:
        df['Descripcion'] = ""
    if 'Precio' not in df.columns:
        df['Precio'] = 0.0
        
    # Clean data types
    df['Clave'] = df['Clave'].astype(str).str.strip()
    df['Descripcion'] = df['Descripcion'].astype(str).fillna("")
    df['Precio'] = df['Precio'].apply(clean_price).round(2)
    
    return df[['Clave', 'Descripcion', 'Precio']], True

def calculate_text_similarity(s1, s2):
    """Calculates similarity ratio between two strings."""
    if not s1 or not s2:
        return 0.0
    return difflib.SequenceMatcher(None, str(s1).lower(), str(s2).lower()).ratio() * 100

@st.cache_data
def convert_df_to_excel(results):
    """
    Converts the results dictionary into a downloadable Excel file.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Summary Sheet
        summary_data = {
            'Métrica': ['Total Archivo A', 'Total Archivo B', 'Coincidencias', 'Solo en A', 'Solo en B'],
            'Valor': [results['total_a'], results['total_b'], results['common_count'], results['only_a_count'], results['only_b_count']]
        }
        pd.DataFrame(summary_data).to_excel(writer, sheet_name='Resumen', index=False)
        
        # Common Sheet
        if not results['common_df'].empty:
            results['common_df'].to_excel(writer, sheet_name='Coincidencias', index=False)
            
        # Only A Sheet
        if not results['only_a_df'].empty:
            results['only_a_df'].to_excel(writer, sheet_name='Solo en A', index=False)
            
        # Only B Sheet
        if not results['only_b_df'].empty:
            results['only_b_df'].to_excel(writer, sheet_name='Solo en B', index=False)
            
    return output.getvalue()

# --- Main App ---

def main():
    st.title("🚗 Análisis Comparativo - Autopartes")
    st.markdown("""
    Sube dos archivos de Excel (Inventarios) para comparar precios, descripciones y detectar nuevos productos o bajas.
    **Requerimientos:** Los archivos deben tener columnas para *Clave*, *Descripción* y *Precio*.
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        file_a = st.file_uploader("📂 Archivo A (Original)", type=['xlsx', 'xls'])
        
    with col2:
        file_b = st.file_uploader("📂 Archivo B (Nuevo/Comparar)", type=['xlsx', 'xls'])
        
    if file_a and file_b:
        st.divider()
        with st.spinner("Procesando archivos..."):
            try:
                # Load Data
                df_a_raw = pd.read_excel(file_a)
                df_b_raw = pd.read_excel(file_b)
                
                df_a, valid_a = normalize_columns(df_a_raw)
                df_b, valid_b = normalize_columns(df_b_raw)
                
                if not valid_a:
                    st.error(f"Error en Archivo A: No se encontró una columna de 'Clave' o 'Código'.")
                    return
                if not valid_b:
                    st.error(f"Error en Archivo B: No se encontró una columna de 'Clave' o 'Código'.")
                    return
                
                # Analysis
                # 1. Merge for Common
                # We use outer join to get everything, then split
                merged = pd.merge(df_a, df_b, on='Clave', how='outer', suffixes=('_A', '_B'), indicator=True)
                
                # Common
                common = merged[merged['_merge'] == 'both'].copy()
                common['Diferencia $'] = (common['Precio_B'] - common['Precio_A']).round(2)
                common['Diferencia %'] = common.apply(lambda x: (x['Diferencia $'] / x['Precio_A'] * 100) if x['Precio_A'] != 0 else 0, axis=1)
                
                # Text Similarity (expensive operation, apply only to common)
                common['Similitud Texto'] = common.apply(lambda x: calculate_text_similarity(x['Descripcion_A'], x['Descripcion_B']), axis=1)
                
                # Only A
                only_a = merged[merged['_merge'] == 'left_only'][['Clave', 'Descripcion_A', 'Precio_A']].rename(columns={'Descripcion_A': 'Descripcion', 'Precio_A': 'Precio'})
                
                # Only B
                only_b = merged[merged['_merge'] == 'right_only'][['Clave', 'Descripcion_B', 'Precio_B']].rename(columns={'Descripcion_B': 'Descripcion', 'Precio_B': 'Precio'})
                
                # Results Object
                results = {
                    'total_a': len(df_a),
                    'total_b': len(df_b),
                    'common_count': len(common),
                    'only_a_count': len(only_a),
                    'only_b_count': len(only_b),
                    'common_df': common[['Clave', 'Descripcion_A', 'Descripcion_B', 'Precio_A', 'Precio_B', 'Diferencia $', 'Diferencia %', 'Similitud Texto']],
                    'only_a_df': only_a,
                    'only_b_df': only_b
                }
                
                # --- Dashboard ---
                
                # KPI Cards
                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                kpi1.metric("Total Archivo A", results['total_a'])
                kpi2.metric("Total Archivo B", results['total_b'])
                kpi3.metric("Coincidencias", results['common_count'])
                kpi4.metric("Diferencias (A+B)", results['only_a_count'] + results['only_b_count'])
                
                st.divider()
                
                # Charts
                chart_col1, chart_col2 = st.columns(2)
                
                with chart_col1:
                    # Donut Chart
                    labels = ['Coincidencias', 'Solo en A', 'Solo en B']
                    values = [results['common_count'], results['only_a_count'], results['only_b_count']]
                    fig_donut = px.pie(names=labels, values=values, hole=0.4, title="Distribución de Claves", 
                                       color_discrete_sequence=['#22c55e', '#ef4444', '#3b82f6'])
                    st.plotly_chart(fig_donut, use_container_width=True)
                    
                with chart_col2:
                    # Bar Chart
                    fig_bar = go.Figure(data=[
                        go.Bar(name='Archivo A', x=['Registros'], y=[results['total_a']], marker_color='#2563eb'),
                        go.Bar(name='Archivo B', x=['Registros'], y=[results['total_b']], marker_color='#ea580c')
                    ])
                    fig_bar.update_layout(title_text='Comparativa de Volumen', barmode='group')
                    st.plotly_chart(fig_bar, use_container_width=True)
                
                # Tabs for Data
                tab1, tab2, tab3 = st.tabs(["📊 Coincidencias", "⚠️ Solo en A", "🆕 Solo en B"])
                
                with tab1:
                    st.subheader("Productos en ambos archivos")
                    
                    # Styling for the dataframe
                    def highlight_diff(val):
                        if isinstance(val, (int, float)) and val != 0:
                            color = 'red' if val > 0 else 'green'
                            return f'color: {color}; font-weight: bold'
                        return ''

                    st.dataframe(
                        results['common_df'].style.format({
                            'Precio_A': '${:,.2f}',
                            'Precio_B': '${:,.2f}',
                            'Diferencia $': '${:,.2f}',
                            'Diferencia %': '{:.2f}%',
                            'Similitud Texto': '{:.1f}%'
                        }).map(highlight_diff, subset=['Diferencia $']),
                        use_container_width=True
                    )
                    
                with tab2:
                    st.subheader("Productos que ya NO están en el nuevo archivo (Eliminados)")
                    st.dataframe(results['only_a_df'].style.format({'Precio': '${:,.2f}'}), use_container_width=True)
                    
                with tab3:
                    st.subheader("Productos NUEVOS en el archivo B")
                    st.dataframe(results['only_b_df'].style.format({'Precio': '${:,.2f}'}), use_container_width=True)
                    
                # Export
                st.divider()
                excel_data = convert_df_to_excel(results)
                st.download_button(
                    label="📥 Descargar Reporte Excel Completo",
                    data=excel_data,
                    file_name="Analisis_Comparativo.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary"
                )
                
            except Exception as e:
                st.error(f"Ocurrió un error inesperado: {e}")
                st.exception(e)

if __name__ == "__main__":
    main()
