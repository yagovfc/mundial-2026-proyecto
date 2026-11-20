# import streamlit as st
# import pandas as pd
# import plotly.express as px

# # ANALISIS 1
# # APARTADO 1
# # Configuración de la página
# st.set_page_config(page_title="Análisis de Ventanas de Partidos", layout="wide") #configuracion de la pagina, utilizo todo el ancho de pantalla

# st.title("ANÁLISIS 1. Ventanas de Partidos")
# st.subheader("Evaluación de la distribución temporal de eventos") #pongo el titulo y el subtitulo en la pag

 
# eventos = pd.read_excel('eventosWC26.xlsx') #cargo los archivos CSV indicados


# lista_partidos = sorted(eventos['index_partido'].dropna().unique()) #obtengo la lista ordenada de partidos disponibles

# partido_seleccionado = st.selectbox(
#     "Seleccione el index del partido a analizar:", 
#     lista_partidos 
# ) #para cada partido pido el index para ver las estadisticas del evento


# df_partido = eventos[eventos['index_partido'] == partido_seleccionado].copy() # filtro eventos del partido seleccionado
# df_partido = df_partido.sort_values(by='minuto_evento')


# fig = px.bar(
#     df_partido,
#     x="minuto_evento",
#     y="tipo_evento",
#     color="tipo_evento",
#     hover_data={
#         "nombre_jugador": True,
#         "minuto_evento": True,
#         "seleccion_evento": True #lo que aparece según voy pasando el ratón
#     },
#     labels={
#         "minuto_evento": "Minuto de Partido",
#         "nombre_jugador": "Jugador",
#         "seleccion_evento": "Selección",
#         "tipo_evento": "Categoría del Evento" #la información que aparece cuando paso el raton
#     },
#     title=f"Eventos en el Tiempo - Partido #{partido_seleccionado}"
# )

# # Personalización del diseño del gráfico (eje X de 0 a 120 min)
# fig.update_layout(
#     xaxis=dict(range=[0, 125], dtick=15, title="Minuto del Partido"), #eje x: de 0 a 125 min con intervalos de 15
#     yaxis=dict(title="Tipo de Evento"), #eje y
#     height=450, #altura fijada para el grafico
#     hovermode="closest", #para la informacion del hover data
#     legend_title_text="Leyenda (Tipo de Evento)"
# )

# # Definir el grosor de las barras verticales para que parezcan marcadores temporales
# fig.update_traces(width=0.9, marker_line_width=0.5, marker_line_color="black") #ajustes de visualizacion


# st.plotly_chart(fig, use_container_width=True) #muestro el gráfico en Streamlit



# # APARTADO 2

# st.markdown("---") #para separar ambos graficos
# st.subheader("Mapa de Calor: Densidad Temporal de Eventos por Ronda")

# partidos = pd.read_excel('partidosWC26.xlsx') #cargo partidos ya que necesito datos de este df también

# if 'index_partido' not in partidos.columns: #aseguramos que partido' tenga index_partido
#     partidos = partidos.reset_index()
#     partidos['index_partido'] = partidos['index'] + 1 # los indices no estan alineados asi que sumamos 1 para alinearlos

# df_merged = pd.merge(eventos, partidos[['index_partido', 'ronda']], on='index_partido', how='inner') # Realizamos un merge usando la clave de unión 'index_partido'


# col1, col2 = st.columns(2) #filtros de streamlit

# with col1:
#     tipos_disponibles = ["Todos"] + list(sorted(df_merged['tipo_evento'].dropna().unique())) #me creo una lista con todas las opciones de evento + todos juntos
#     tipo_filtro = st.selectbox("Filtrar por Tipo de Evento:", tipos_disponibles) #creo la opcion de filtrado

# with col2:
#     rondas_disponibles = ["Todas"] + list(sorted(df_merged['ronda'].dropna().unique())) #hago lo mismo con las rondas
#     ronda_filtro = st.selectbox("Filtrar por Ronda:", rondas_disponibles)

# df_filtrado = df_merged.copy()
# if tipo_filtro != "Todos":
#     df_filtrado = df_filtrado[df_filtrado['tipo_evento'] == tipo_filtro]
# if ronda_filtro != "Todas":
#     df_filtrado = df_filtrado[df_filtrado['ronda'] == ronda_filtro] #df_filtardo dependiendo de la opcion a alegir en streamlit

# bins = [0, 15, 30, 45, 60, 75, 90, 105, 120] #definimos los intervalos de tiempo
# labels = ['0-15 min', '15-30 min', '30-45 min', '45-60 min', '60-75 min', '75-90 min', '90-105 min (P1)', '105-120 min (P2)']

# fig_heat = px.density_heatmap( #creacion del mapa de calor
#     df_filtrado,
#     x="minuto_evento",
#     y="tipo_evento",
#     nbinsx=8,  #8 intervalos temporales a lo largo de los 120 min
#     color_continuous_scale="Viridis",
#     labels={
#         "minuto_evento": "Tiempo de Partido (Minutos)",
#         "tipo_evento": "Tipo de Evento",
#         "count": "Cantidad de Eventos"
#     },
#     title=f"Densidad de Eventos ({tipo_filtro} | Ronda: {ronda_filtro})"
# )

# fig_heat.update_layout(
#     xaxis=dict(range=[0, 120], dtick=15, title="Minuto del Partido"), #ajustes de visualizacion de 0 120 de 15 en 15
#     yaxis=dict(title="Tipo de Evento"),
#     height=400
# )

# st.plotly_chart(fig_heat, use_container_width=True) #visualizacion


# st.markdown("Respuestas al Análisis Temporal") #respuestas


# df_goles = df_merged[df_merged['tipo_evento'].str.contains('Gol', na=False)].copy() #me creo un df que solo contenga eventos con gol
# df_goles['intervalo'] = pd.cut(df_goles['minuto_evento'], bins=bins, labels=labels, right=False) #me creo un acolumna de intervalo con el numero de goles que hayan habido en cierto intervalo, sin incluir el extremo derecho del intervalo
# intervalo_max_goles = df_goles['intervalo'].value_counts().idxmax() #intrevalo de 15 minutos con mas goles
# cant_max_goles = df_goles['intervalo'].value_counts().max() #mayor cantidad de goles


# goles_p1 = df_goles[df_goles['minuto_evento'] < 45].shape[0] #goles de la primera parte (shape[0], numero de filas, siendo todas un gol distinto (numero de goles))
# goles_p2 = df_goles[(df_goles['minuto_evento'] >= 45) & (df_goles['minuto_evento'] <= 90)].shape[0] #goles de la segunda parte
# goles_pro = df_goles[df_goles['minuto_evento'] > 90].shape[0] #goles de la prórroga

# st.write(f"1. Intervalo con mayor concentración de goles: El tramo {intervalo_max_goles} registra la mayor cantidad con un total de {cant_max_goles} goles.")
# st.write(f"2. ¿Segundas partes más 'entretenidas' que las primeras?: Sí. En las segundas partes (min 45-90) se registraron {goles_p2} goles, frente a {goles_p1} goles en las primeras partes (min 0-45). El desgaste físico y la necesidad de buscar el resultado incrementan la frecuencia de eventos decisivos.")
# st.write(f"3. ¿Y las prórrogas?: En las prórrogas (>90 min) se contabilizaron {goles_pro} goles. Aunque la densidad por minuto disminuye por el cansancio y el temor a encajar gol, la tensión se refleja en un incremento de tarjetas y revisiones.")



# # APARTADO 3

# st.markdown("---") #para separar ambos graficos
# st.subheader("Distribución de Eventos por Selección (A favor vs. En contra)")


# eventos = pd.read_excel('eventosWC26.xlsx')
# partidos = pd.read_excel('partidosWC26.xlsx') #df necesarios


# if 'index_partido' not in partidos.columns: #aseguramos que partido' tenga index_partido
#     partidos = partidos.reset_index()
#     partidos['index_partido'] = partidos['index'] + 1 # los indices no estan alineados asi que sumamos 1 para alinearlos


# lista_selecciones = sorted(eventos['seleccion_evento'].dropna().astype(str).str.strip().unique()) #lista de selecciones unicas

# seleccion_elegida = st.selectbox(
#     "Seleccione una Selección para analizar su balance de eventos:", 
#     lista_selecciones
# ) #opcion de elegir una seleccion


# df_eventos_partidos = pd.merge(eventos, partidos, on='index_partido', how='inner') #fusionamos eventos con partidos para identificar en qué partidos participó la selección elegida

# # Normalización de textos
# sel_elegida_clean = str(seleccion_elegida).strip()

# df_eventos_partidos['seleccion_local_clean'] = df_eventos_partidos['seleccion_local'].astype(str).str.strip()
# df_eventos_partidos['seleccion_visitante_clean'] = df_eventos_partidos['seleccion_visitante'].astype(str).str.strip()
# df_eventos_partidos['seleccion_evento_clean'] = df_eventos_partidos['seleccion_evento'].astype(str).str.strip()


# df_sel = df_eventos_partidos[
#     (df_eventos_partidos['seleccion_local_clean'] == sel_elegida_clean) | 
#     (df_eventos_partidos['seleccion_visitante_clean'] == sel_elegida_clean)
# ].copy() #un partido involucra a la selección si jugó como local o visitante


# df_sel['Condición'] = df_sel['seleccion_evento_clean'].apply(
#     lambda x: 'A Favor' if x == sel_elegida_clean else 'En Contra'
# ) #definimos la condición: A favor (hecho por la selección) o En contra (hecho por el rival)

# df_sel['Evento_Detallado'] = df_sel['tipo_evento'].astype(str) + " (" + df_sel['Condición'] + ")" #creamos una etiqueta combinada para visualizar claramente en el gráfico


# df_resumen_pie = df_sel.groupby(['Evento_Detallado', 'Condición']).size().reset_index(name='Total') #agrupo los datos para el grafico y contando el numero de veces que ocurre dicho evento en Total

# # Mapeo explicito de colores: Verde para A Favor, Rojo para En Contra
# colores_eventos = {
#     row['Evento_Detallado']: '#2ca02c' if row['Condición'] == 'A Favor' else '#d62728'
#     for _, row in df_resumen_pie.iterrows()
# }


# fig_pie = px.pie(
#     df_resumen_pie,
#     values='Total',
#     names='Evento_Detallado',
#     color='Evento_Detallado',
#     color_discrete_map=colores_eventos,
#     hole=0.4, #estilo donut
#     title=f"Balance Global de Eventos: {seleccion_elegida}"
# ) #grafico pie tipo donut

# fig_pie.update_traces(
#     textposition='inside', #texto dentro del grafico
#     textinfo='label+value+percent', #informacion que se muestra
#     hovertemplate="<b>%{label}</b><br>Total: %{value}<br>Porcentaje: %{percent}<extra></extra>" #muestra formato al pasar el raton
# )

# fig_pie.update_layout(
#     height=500,
#     legend_title_text="Categoría de Eventos"
# ) #ajustes de visualizacion

# st.plotly_chart(fig_pie, use_container_width=True) #visualizacion



# # ANALISIS 1
# # APARTADO 1

# jugadores = pd.read_excel("jugadoresWC2026.xlsx")

# st.markdown("---")
# st.subheader("Valor de Mercado vs. Calificación Media de Jugadores")


# df_180 = jugadores[jugadores['minutos_jugados'] >= 180].copy() #jugadoers con al menos 180 minutos jugados

# col1, col2, col3 = st.columns(3) #columnas iniciales en streamlit(filtros)

# with col1: #primer filtro
#     opciones_seleccion = ["Todas"] + sorted(df_180['seleccion_nacional'].dropna().astype(str).unique().tolist())
#     sel_filtro = st.selectbox("Filtrar por Selección:", opciones_seleccion) #filtrado por seleccion, todas las selecciones y eleccion entre una de todas
    
# with col2: #segundo filtro
#     opciones_posicion = ["Todas"] + sorted(df_180['posicion'].dropna().astype(str).unique().tolist())
#     pos_filtro = st.selectbox("Filtrar por Posición:", opciones_posicion) #filtardo por posicion, todas las posiciones y eleccion entre una de todas
    
# with col3: #tercer filtro
#     min_pj = int(df_180['partidos_jugados'].min()) #minimo de partidos jugados (2 partidos de 90 necesariamente)
#     max_pj = int(df_180['partidos_jugados'].max()) #maximo de partidos jugados (8 partidos si se llega hasta la final)
#     pj_filtro = st.slider("Partidos Jugados:", min_value=min_pj, max_value=max_pj, value=min_pj) #creo un slider para elegir el numero de partidos

# #aplicar filtros
# df_filtrado = df_180[df_180['partidos_jugados'] == pj_filtro].copy()

# if sel_filtro != "Todas":
#     df_filtrado = df_filtrado[df_filtrado['seleccion_nacional'] == sel_filtro]
    
# if pos_filtro != "Todas":
#     df_filtrado = df_filtrado[df_filtrado['posicion'] == pos_filtro]

# fig_scatter = px.scatter( #diagrama de puntos, para ver la relacion
#     df_filtrado,
#     x='valor_mercado', 
#     y='calificacion_media', #los campos que queremos relacionar
#     color='posicion', #distintos colores segun posicion
#     size='minutos_jugados', #cuantos mas minutos jugados mas grande el circulo
#     hover_name='nombre_jugador', #dato por cada nombre
#     hover_data={
#         'seleccion_nacional': True,
#         'valor_mercado': ':.1f',
#         'calificacion_media': ':.2f',
#         'partidos_jugados': True,
#         'minutos_jugados': True #informacion por cada nombre, al pasar el raton
#     },
#     trendline="ols",  #añade línea de tendencia para visualizar la correlación
#     title="Valor de Mercado vs. Calificación Media (Min. 180 Minutos)",
#     labels={
#         'valor_mercado': 'Valor de Mercado (M€)',
#         'calificacion_media': 'Calificación Media',
#         'posicion': 'Posición'
#     }
# )

# fig_scatter.update_layout(height=550) #ajustes de visualizacion
# st.plotly_chart(fig_scatter, use_container_width=True) #visualizacion


# correlacion = df_filtrado['valor_mercado'].corr(df_filtrado['calificacion_media']) #calculo la correlacion

# st.markdown("### Conclusiones e Interpretación de Resultados")

# col_m1, col_m2 = st.columns(2) #para poner informacion en dos columnas
# col_m1.metric("Correlación de Pearson", f"{correlacion:.2f}") #muestro la correlacion

# #dependiendo de la correlacion que tenga sera fuerte, moderada, debil o practicamente nula
# if abs(correlacion) < 0.25:
#     grado_corr = "prácticamente nula"
# elif abs(correlacion) < 0.5:
#     grado_corr = "débil"
# elif abs(correlacion) < 0.75:
#     grado_corr = "moderada"
# else:
#     grado_corr = "fuerte"
    
# col_m2.write(f"Existe una correlación {grado_corr} entre el valor económico del jugador y sus notas obtenidas en el torneo.")

# st.markdown(f"""
# * **Relación Económico-Deportiva**: Una correlación de {correlacion:.2f} indica que un mayor valor de mercado no garantiza necesariamente un desempeño superior en un torneo corto de selecciones como el Mundial.
# * **Estrellas que Decepcionan (Cuadrante Inferior Derecho):** Jugadores situados muy a la derecha en el eje horizontal (alto valor de mercado) pero con bajas calificaciones en el eje vertical representan grandes nombres que rindiendo por debajo de las expectativas, como por ejemplo Lamine Yamal si aplicamos un filtro de 8 partidos (para verlo mas fácil).
# * **Revelaciones del Torneo (Cuadrante Superior Izquierdo):** Jugadores situados a la izquierda (bajo valor de mercado) pero en la parte alta de notas son perfiles revalorizados con rendimiento destacado, como por ejemplo Leo Messi si aplicamos un filtro de 8 partidos (para verlo mas fácil) .
# * **Efecto Muestra en Torneos Cortos:** El rendimiento en una fase final depende en gran medida del estado de forma puntual, táctica colectiva y dinámica de grupo, reduciendo la brecha habitual entre la élite económica y jugadores de perfil medio.
# """)
