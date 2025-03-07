import requests
import pandas as pd
from helpers import clean_string
from config import BASE_URL


def canvas_request(session, method, endpoint, payload=None, paginated=False):
    """
    Realiza peticiones a la API de Canvas y maneja la paginación si es necesario.
    
    :param session: Sesión de requests.Session() configurada previamente.
    :param method: Método HTTP ('get', 'post', 'put', 'delete').
    :param endpoint: Endpoint de la API (por ejemplo, "/courses/123/assignments").
    :param payload: Datos a enviar (para POST/PUT).
    :param paginated: Si es True, recorre todas las páginas y devuelve una lista con todos los resultados.
    :return: La respuesta en formato JSON o None en caso de error.
    """
    if not BASE_URL:
        raise ValueError("BASE_URL no está configurada. Usa set_base_url() para establecerla.")

    url = f"{BASE_URL}{endpoint}"
    results = []
    
    try:
        while url:
            if method.lower() == "get":
                response = session.get(url)
            elif method.lower() == "post":
                response = session.post(url, json=payload)
            elif method.lower() == "put":
                response = session.put(url, json=payload)
            elif method.lower() == "delete":
                response = session.delete(url)
            else:
                print("Método HTTP no soportado")
                return None

            if not response.ok:
                print(f"Error en la petición a {url} ({response.status_code}): {response.text}")
                return None

            data = response.json()
            if paginated:
                results.extend(data)  # Agregar todos los elementos a la lista
                
                # Manejar paginación buscando la URL de la siguiente página
                url = response.links.get("next", {}).get("url")  # Si hay otra página, seguimos
            else:
                return data  # Si no es paginado, devolvemos la respuesta normal

        return results if paginated else None

    except requests.exceptions.RequestException as e:
        print(f"Excepción en la petición a {url}: {e}")
        return None


def get_rubric_details(course_id, assignment):
    """Obtiene detalles de la rúbrica asociada a una tarea."""
    if assignment.get("rubric_settings"):
        rubric_used_for_grading = assignment.get("use_rubric_for_grading")
        rubric_settings = assignment["rubric_settings"]
        return {
            "has_rubric": True,
            "rubric_points": rubric_settings.get("points_possible"),
            "rubric_used_for_grading": rubric_used_for_grading,
            "name": rubric_settings.get("title")
        }
    return {"has_rubric": False, "rubric_points": None, "rubric_used_for_grading": False}


def get_module_name(session, course_id: str, assignment_group_id: str):
    """Obtiene el nombre, peso e id del módulo (assignment group) de la tarea."""
    response = canvas_request(session, "get", f"/courses/{course_id}/assignment_groups/{assignment_group_id}")
    if response and isinstance(response, dict):
        return {
            "name": response.get("name"),
            "weight": response.get("group_weight"),
            "id": response.get("id")
        }
    else:
        return None
  
    
def check_group_categories(session, course_id):
    """Obtiene y verifica las categorías de grupo de un curso."""
    group_categories_response = canvas_request(session, "get", f"/courses/{course_id}/group_categories")
    if group_categories_response is None:
        return None

    group_categories = group_categories_response

    trabajo_en_equipo = next((gc for gc in group_categories if gc.get("name") == "Equipo de trabajo"), None)
    project_groups = next((gc for gc in group_categories if gc.get("name") == "Project Groups"), None)

    return {
        "Equipo de trabajo": {
            "exists": trabajo_en_equipo is not None,
            "id": trabajo_en_equipo["id"] if trabajo_en_equipo else None,
        },
        "Project Groups": {
            "exists": project_groups is not None,
            "id": project_groups["id"] if project_groups else None,
        }
    }
   
    
def check_team_assignments(session, course_id):
    """
    Verifica si se han creado equipos y si todos los estudiantes están asignados a un equipo
    en la categoría 'Equipo de trabajo'. Filtra profesores y asistentes.
    """
    group_categories = canvas_request(session, "get", f"/courses/{course_id}/group_categories", paginated=True)
    if not group_categories:
        return None

    equipo_de_trabajo = next((gc for gc in group_categories if gc.get("name") == "Equipo de trabajo"), None)
    if not equipo_de_trabajo:
        return {"teams_created": False, "all_assigned": False, "group_memberships": {}, "unassigned_students": []}

    group_category_id = equipo_de_trabajo["id"]

    # Obtener **TODOS** los equipos con paginación
    groups = canvas_request(session, "get", f"/group_categories/{group_category_id}/groups", paginated=True)
    if not groups:
        return {"teams_created": False, "all_assigned": False, "group_memberships": {}, "unassigned_students": []}

    # Obtener **TODOS** los usuarios del curso con paginación
    users_response = canvas_request(session, "get", f"/courses/{course_id}/users", paginated=True)
    if not users_response:
        return None

    # **Filtrar solo estudiantes**, ignorando los que no tienen 'enrollments'
    student_dict = {
        user["id"]: {"name": user["name"], "email": user.get("email", "Sin correo")}
        for user in users_response
        if user.get("enrollments") and "student" in user["enrollments"][0]["type"]
    }

    student_ids = set(student_dict.keys())  # Set con IDs de todos los estudiantes
    assigned_student_ids = set()
    group_memberships = {}

    # Obtener **TODAS** las membresías de los grupos
    for group in groups:
        memberships = canvas_request(session, "get", f"/groups/{group['id']}/memberships", paginated=True)
        if memberships:
            assigned_student_ids.update(m.get("user_id") for m in memberships if m.get("user_id") in student_dict)
            group_memberships[group["name"]] = [student_dict.get(m.get("user_id"), {"name": "Desconocido"})["name"] for m in memberships]

    # Determinar estudiantes sin asignar
    unassigned_students = student_ids - assigned_student_ids
    unassigned_details = [student_dict[uid] for uid in unassigned_students]  # Lista con nombres y correos de los no asignados
    all_assigned = len(unassigned_students) == 0

    return {
        "teams_created": True,
        "all_assigned": all_assigned,
        "unassigned_students": unassigned_details,  # Ahora devuelve detalles de los estudiantes sin asignar
        "total_students": len(student_ids),
        "total_teams": len(groups),
        "group_memberships": group_memberships
    }
    

def get_quiz_details(session, course_id, quiz_id):
    """
    Obtiene los detalles de un cuestionario (quiz) en Canvas.
    """
    quiz_details = canvas_request(session, "get", f"/courses/{course_id}/quizzes/{quiz_id}")
    
    if not quiz_details:
        return None
    
    return {
        "intentos_permitidos": quiz_details.get("allowed_attempts"),
        "tiempo_limite": quiz_details.get("time_limit", "Sin límite"),
        "mezclar_respuestas": quiz_details.get("shuffle_answers", False),
        "permitir_que_estudiantes_vean_respuestas": quiz_details.get("hide_results", False) != "always",
        "mostrar_respuestas_correctas": quiz_details.get("show_correct_answers"),
        "cantidad_de_preguntas": quiz_details.get("question_count"),
    }
    
       
def analyze_assignment(session, course_id, assignment, assignment_type, is_massive=False):
    """
    Función base para analizar una tarea según su tipo (foro, trabajo final, trabajo en equipo, cuestionario final).
    """

    # Si el curso es masivo y la tarea es "finalwork", lo cambiamos a "quiz_final"
    if is_massive and assignment_type == "finalwork":
        assignment_type = "quiz_final"

    # Obtener detalles comunes
    rubric_details = get_rubric_details(course_id, assignment)
    module_info = get_module_name(session, course_id, assignment.get("assignment_group_id"))

    # Definir reglas específicas para cada tipo de tarea
    rules = {
        "forum": {
            "submission_types": ['discussion_topic'],
            "points_possible": 100,
            "module_weight": 20,
            "discussion_type": "threaded",
        },
        "finalwork": {
            "submission_types": ["online_upload"],
            "allowed_attempts": 2,
            "points_possible": 100,
            "module_weight": 50,
        },
        "quiz_final": {
            "submission_types": ["online_quiz"],
            "allowed_attempts": 1,
            "points_possible": 30,
            "module_weight": 30,
            "time_limit": 90,
            "question_count": 30
        },
        "teamwork": {
            "submission_types": ["online_upload"],
            "allowed_attempts": 2,
            "points_possible": 100,
            "module_weight": 30 if not is_massive else 50,
        }
    }

    specific_rules = rules.get(assignment_type, {})
    result = {}

    # Si es un cuestionario final, obtenemos sus detalles adicionales
    quiz_details = None
    if assignment_type == "quiz_final" and "quiz_id" in assignment:
        quiz_details = get_quiz_details(session, course_id, assignment["quiz_id"])

    # Poner rúbrica en todas las tareas excepto en el cuestionario final
    if assignment_type != "quiz_final":
        result = {
            "Tiene rúbrica": (
                rubric_details.get("name", "Sin rúbrica"),  # Si "name" no existe, muestra "Sin rúbrica"
                "✅" if rubric_details["has_rubric"] else "🟥"
            ),
            "Puntos rúbrica": (
                rubric_details["rubric_points"] if rubric_details["has_rubric"] else "N/A",
                "✅" if rubric_details["rubric_points"] == 100 else "🟥"
            ),
            "Usa rúbrica para calificar": (
                "Sí" if rubric_details["rubric_used_for_grading"] else "No",
                "✅" if rubric_details["rubric_used_for_grading"] else "🟥"
            ),
        }

    # Configuración de entrega
    result.update({
        "Tipo de entrega": (
            assignment.get("submission_types"), 
            "✅" if assignment.get("submission_types") == specific_rules.get("submission_types") else "🟥"
        ),
    })

    if assignment_type != "forum" and assignment_type != "quiz_final":
        result.update({
            "Intentos permitidos": (
                "Ilimitado" if assignment.get("allowed_attempts") == -1 else str(assignment.get("allowed_attempts")),
                "✅" if assignment.get("allowed_attempts") == specific_rules.get("allowed_attempts") else "🟥"
            ),
        })

    result.update({
        "Tipo de calificación": (
            "Puntos" if assignment.get("grading_type") == "points" else "Otro",
            "✅" if assignment.get("grading_type") == "points" else "🟥"
        ),
        "Puntos posibles": (
            str(int(assignment.get("points_possible"))),
            "✅" if assignment.get("points_possible") == specific_rules.get("points_possible") else "🟥"
        ),
        "Ponderación": (
            f"{int(module_info['weight'])}%", 
            "✅" if int(module_info['weight']) == specific_rules.get("module_weight") else "🟥"
        ),
        "Módulo": (
            module_info["name"], 
            "✅" if clean_string(module_info["name"]) == clean_string(assignment.get("name")) else "🟥"
        ),
    })

    # Si es un trabajo en equipo, agregar detalles de equipos
    if assignment_type == "teamwork":
        group_categories_check = check_group_categories(session, course_id)
        team_options = check_team_assignments(session, course_id)

        unassigned_list = team_options["unassigned_students"]
        unassigned_text = ", ".join([f"{student['name']} ({student['email']})" for student in unassigned_list]) if unassigned_list else "Todos asignados"

        result.update({
            "Es trabajo en grupo": (
                "Sí" if assignment.get("group_category_id") else "No",
                "✅" if assignment.get("group_category_id") else "🟥"
            ),
            "Existe Equipo de trabajo": (
                "Sí" if group_categories_check["Equipo de trabajo"]["exists"] else "No",
                "✅" if group_categories_check["Equipo de trabajo"]["exists"] else "🟥"
            ),
            "Existe Project Groups": (
                "Sí" if not group_categories_check["Project Groups"]["exists"] else "No",
                "✅" if not group_categories_check["Project Groups"]["exists"] else "🟥"
            ),
            "Equipos creados": (
                f"{team_options['total_teams']} equipos" if team_options and team_options['teams_created'] else "No",
                "✅" if team_options and team_options['teams_created'] else "🟥"
            ),
            "Grupos": (
                ", ".join(team_options["group_memberships"].keys()) if team_options and team_options["group_memberships"] else "No hay grupos",
                "✅" if team_options and team_options["group_memberships"] else "🟥"
            ),
            "Alumnos sin asignar": (
                unassigned_text,
                "✅" if team_options and team_options["all_assigned"] else "🟥"
            ),
    })
        
        # Si es un cuestionario final, agregar detalles del quiz
    if assignment_type == "quiz_final" and quiz_details:
        result.update({
            "Numero de preguntas": (
                quiz_details["cantidad_de_preguntas"],
                "✅" if quiz_details["cantidad_de_preguntas"] == specific_rules.get("question_count") else "🟥"
            ),
            "Intentos permitidos": (
                quiz_details["intentos_permitidos"], 
                "✅" if quiz_details["intentos_permitidos"] == specific_rules.get("allowed_attempts") else "🟥"
            ),
            "Límite de tiempo (min)": (
                quiz_details["tiempo_limite"],
                "✅" if quiz_details["tiempo_limite"] == specific_rules.get("time_limit") else "🟥"
            ),
            "Mezclar respuestas": (
                "Sí" if quiz_details["mezclar_respuestas"] else "No", 
                "✅" if quiz_details["mezclar_respuestas"] else "🟥"
            ),
            "Permitir que estudiantes vean respuestas": (
                "Sí" if quiz_details["permitir_que_estudiantes_vean_respuestas"] else "No",
                "✅" if quiz_details["permitir_que_estudiantes_vean_respuestas"] else "🟥"
            ),
            "Mostrar respuestas correctas": (
                "Sí" if quiz_details["mostrar_respuestas_correctas"] else "No",
                "✅" if quiz_details["mostrar_respuestas_correctas"] else "🟥"
                ),
        })

    # Separar valores y estados en listas
    detalles = {key: value[0] for key, value in result.items()}
    third_column = [value[1] for key, value in result.items()]

    return detalles, third_column

 
def return_df_for_table(details, estado):
    """Muestra los detalles en forma de tabla usando pandas."""
    
    # Convertimos todos los valores de "Actual" a strings para evitar problemas con PyArrow
    actual_values = [str(value) if not isinstance(value, str) else value for value in details.values()]
    
    data = {
        "Requerimiento": list(details.keys()), 
        "Actual": actual_values,  # Aseguramos que todo sea string
        "Estado": estado
    }
    
    df = pd.DataFrame(data)
    return df