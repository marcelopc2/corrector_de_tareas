import requests
import pandas as pd
from helpers import clean_string
from config import BASE_URL


def canvas_request(session, method, endpoint, payload=None):
    """
    Realiza peticiones a la API de Canvas de forma centralizada.
    
    :param session: Sesión de requests.Session() configurada previamente.
    :param method: Método HTTP ('get', 'post', 'put', 'delete').
    :param endpoint: Endpoint de la API (por ejemplo, "/courses/123/assignments").
    :param payload: Datos a enviar (para POST/PUT).
    :return: La respuesta en formato JSON o None en caso de error.
    """
    if not BASE_URL:
        raise ValueError("BASE_URL no está configurada. Usa set_base_url() para establecerla.")

    url = f"{BASE_URL}{endpoint}"
    try:
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

        if response.text:
            return response.json()
        else:
            return None

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
    en la categoría 'Equipo de trabajo'.
    """
    group_categories = canvas_request(session, "get", f"/courses/{course_id}/group_categories")
    if not group_categories:
        return None

    equipo_de_trabajo = next((gc for gc in group_categories if gc.get("name") == "Equipo de trabajo"), None)
    if not equipo_de_trabajo:
        return {"teams_created": False, "all_assigned": False}
    
    group_category_id = equipo_de_trabajo["id"]
    groups = canvas_request(session, "get", f"/group_categories/{group_category_id}/groups")
    if not groups:
        return {"teams_created": False, "all_assigned": False}

    students_response = canvas_request(session, "get", f"/courses/{course_id}/students")
    if not students_response:
        return None
    
    student_ids = {student["id"] for student in students_response}
    assigned_student_ids = set()

    for group in groups:
        memberships = canvas_request(session, "get", f"/groups/{group['id']}/memberships")
        if memberships:
            assigned_student_ids.update(m.get("user_id") for m in memberships)

    all_assigned = student_ids.issubset(assigned_student_ids)
     
    return {
        "teams_created": True,
        "all_assigned": all_assigned,
        "unassigned_students": student_ids - assigned_student_ids,
        "total_students": student_ids
    }

       
def analyze_assignment(session, course_id, assignment, assignment_type, is_massive=False):
    """
    Función base para analizar una tarea según su tipo (foro, trabajo final, trabajo en equipo).
    """

    # Si el curso es masivo y la tarea es "finalwork", cambiamos el tipo a "quiz_final"
    if is_massive and assignment_type == "finalwork":
        assignment_type = "quiz_final"

    # Obtener detalles comunes
    rubric_details = get_rubric_details(course_id, assignment)
    module_info = get_module_name(session, course_id, assignment.get("assignment_group_id"))

    # Definir reglas específicas para cada tipo de tarea
    rules = {
        "forum": {
            "submission_types": ['discussion_topic'],
            "allowed_attempts": -1,
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

    # Diccionario con los resultados directamente, incluyendo la verificación ✅/🟥
    if assignment_type != "quiz_final":
        result = {
            "Tiene rubrica": (rubric_details["name"], "✅" if rubric_details["has_rubric"] else "🟥"),
            "Puntos rubrica": (str(int(rubric_details["rubric_points"])) if rubric_details["has_rubric"] else "N/A", "✅" if rubric_details["rubric_points"] == 100 else "🟥"),
            "Usa rubrica para calificar": ("Si" if rubric_details["rubric_used_for_grading"] else "No", "✅" if rubric_details["rubric_used_for_grading"] else "🟥"),

        }
    
    result.update({
        "Tipo de entrega": ("En línea" if assignment.get("submission_types") == specific_rules.get("submission_types") else "Otro", "✅" if assignment.get("submission_types") == specific_rules.get("submission_types") else "🟥"),
        "Intentos permitidos": ("Ilimitado" if assignment.get("allowed_attempts") == -1 else str(assignment.get("allowed_attempts")), "✅" if assignment.get("allowed_attempts") == specific_rules.get("allowed_attempts") else "🟥"),
        "Tipo de calificación": ("Puntos" if assignment.get("grading_type") == "points" else "Otro", "✅" if assignment.get("grading_type") == "points" else "🟥"),
        "Puntos posibles": (str(int(assignment.get("points_possible"))), "✅" if assignment.get("points_possible") == specific_rules.get("points_possible") else "🟥"),
        "Ponderación": (f"{int(module_info['weight'])}%", "✅" if int(module_info['weight']) == specific_rules.get("module_weight") else "🟥"),
        "Módulo": (module_info["name"], "✅" if clean_string(module_info["name"]) == clean_string(assignment.get("name")) else "🟥"),
    })

    # Verificación adicional para "foro"
    if assignment_type == "forum":
        result["Desactivar respuestas hilvanadas"] = (
            "Si" if assignment.get('discussion_topic', {}).get("discussion_type") == specific_rules.get("discussion_type") else "No",
            "✅" if assignment.get('discussion_topic', {}).get("discussion_type") == specific_rules.get("discussion_type") else "🟥"
        )

    # Verificación para "teamwork"
    elif assignment_type == "teamwork":
        group_categories_check = check_group_categories(session, course_id)
        team_options = check_team_assignments(session, course_id)
        result.update({
            "Es trabajo en grupo": ("Si" if assignment.get("group_category_id") else "No", "✅" if assignment.get("group_category_id") else "🟥"),
            "Existe Equipo de trabajo": ("Si" if group_categories_check["Equipo de trabajo"]["exists"] else "No", "✅" if group_categories_check["Equipo de trabajo"]["exists"] else "🟥"),
            "Existe Project Groups": ("Si" if not group_categories_check["Project Groups"]["exists"] else "No", "✅" if not group_categories_check["Project Groups"]["exists"] else "🟥"),
            "Equipos creados": ("Si" if team_options and team_options['teams_created'] else "No", "✅" if team_options and team_options['teams_created'] else "🟥"),
            "Alumnos Asignados": ("Si" if team_options and team_options['all_assigned'] else f"{len(team_options['unassigned_students'])} sin asignar", "✅" if team_options and team_options['all_assigned'] else "🟥"),
        })

    # Separar los valores y los estados en listas
    detalles = {key: value[0] for key, value in result.items()}
    third_column = [value[1] for key, value in result.items()]

    return detalles, third_column

 
def return_df_for_table(details, estado):
    """Muestra los detalles en forma de tabla usando pandas."""
    data = {"Requerimiento": list(details.keys()), "Actual": list(details.values()), "Estado":estado}
    df = pd.DataFrame(data)
    return df