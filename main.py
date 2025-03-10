import streamlit as st
import requests
from config import HEADERS
from  functions import canvas_request, return_df_for_table, analyze_assignment, get_student_count
from helpers import clean_string, parse_course_ids

session = requests.Session()
session.headers.update(HEADERS)

st.set_page_config(page_title="REVISADOR y CONFIGURADOR DE TAREAS ⛑️", page_icon="⛑️")
st.title("REVISADOR y CONFIGURADOR DE TAREAS ⛑️")

st.subheader("Ingresar IDs de Cursos")
course_ids_input = st.text_area(
    "Ingresa los IDs de los cursos (separados por espacio, coma o salto de línea):",
    height=100,
)

st.subheader("Seleccionar Acción")
action = st.radio(
    "¿Qué acción deseas realizar?",
    options=("Revisar", "Corregir"),
)

if st.button("Ejecutar"):
    st.divider()
    if not course_ids_input.strip():
        st.error("Por favor, ingresa al menos un ID de curso.")
    else:
        course_ids = parse_course_ids(course_ids_input)
        # Mostrar la acción seleccionada
        if action == "Revisar":
            for course_id in course_ids:
                #Conseguir informacion del curso y de la subcuenta
                course_info = canvas_request(session, "get", f"/courses/{course_id}")
                subaccount_info = canvas_request(session, "get", f"/accounts/{course_info.get('account_id')}")
                #Detectamos si es un diplomado masivo vienddo si el nombre de la subcuenta es "Diplomado Masivo"
                is_massive = True if clean_string("Diplomado Masivo") in clean_string(subaccount_info.get('name')) else False
                if not course_info:
                    st.error(f"Curso con ID {course_id} no encontrado.")
                    continue
                st.markdown(f"##### [{course_info.get('name')} - ({course_info.get('id')}) - {course_info.get('course_code')}](https://canvas.uautonoma.cl/courses/{course_id}/assignments)", unsafe_allow_html=True)
                st.markdown(f"###### {subaccount_info.get('name')} - ({subaccount_info.get('id')})", unsafe_allow_html=True)
                st.markdown(f"###### Diplomado Masivo: {is_massive}", unsafe_allow_html=True)
                st.markdown(f"###### Cantidad de Alumnos: {get_student_count(session, course_id)}", unsafe_allow_html=True)
                
                course_assignments = canvas_request(session, "get", f"/courses/{course_id}/assignments") or []
                if not course_assignments:
                    st.warning("No se encontraron tareas en este curso.")
                    continue
                
                # Filtrar tareas por tipo
                forum_assignments = [a for a in course_assignments if "foro academico" in clean_string(a["name"].lower())]
                teamwork_assignments = [a for a in course_assignments if "trabajo en equipo" in clean_string(a["name"].lower()) or "tarea en equipo" in clean_string(a["name"].lower())]
                final_assignments = [a for a in course_assignments if "trabajo final" in clean_string(a["name"].lower())]
                if is_massive:
                    final_assignments = [a for a in course_assignments if "cuestionario final" in clean_string(a["name"].lower())]
                
                #Reviso las tareas de foro academico
                if not forum_assignments:
                    st.info(f"No hay tareas llamadas 'Foro academico'")
                else:
                    for assignment in forum_assignments:
                        st.write(f"##### Tarea: {assignment['name']} - {assignment['id']}")
                        details, third_column = analyze_assignment(session, course_id, assignment, "forum", is_massive)
                        st.dataframe(return_df_for_table(details, third_column))
                
                #Reviso las tareas de trabajo en equipo     
                if not teamwork_assignments:
                    st.info(f"No hay tareas llamadas 'Trabajo en equipo'")
                else:
                    for assignment in teamwork_assignments:
                        st.write(f"##### Tarea: {assignment['name']} - {assignment['id']}")
                        details, third_column = analyze_assignment(session, course_id, assignment, "teamwork", is_massive)
                        st.dataframe(return_df_for_table(details, third_column))
                
                #Reviso las tareas de trabajo final
                if not final_assignments:
                    st.info(f"No hay tareas llamadas 'Trabajo final o Cuestionario Final'")
                else:
                    for assignment in final_assignments:
                        st.write(f"##### Tarea: {assignment['name']} - {assignment['id']}")
                        details, third_column = analyze_assignment(session, course_id, assignment, "finalwork", is_massive)
                        st.dataframe(return_df_for_table(details, third_column))
                        
                st.divider()

                
        elif action == "Corregir":
            st.info("Acción seleccionada: Corregir cursos.")


