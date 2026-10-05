"""Pruebas de las opciones elegibles."""
from core.choices import Choices, pick_option

CASA = "C:\\Users\\Holcen\\Documents\\jarvis_pruebas\\fotos\\notas.txt"
ESCRITORIO = "C:\\Users\\Holcen\\Desktop\\varios\\notas.txt"
OPCIONES = (CASA, ESCRITORIO)


def test_choices_es_un_texto_con_datos():
    choices = Choices("hola", tool="open_file", argument="path", options=("x",))
    assert choices == "hola"
    assert (choices.tool, choices.argument, choices.options) == ("open_file", "path", ("x",))


def test_elige_por_numero():
    assert pick_option("2", OPCIONES) == ESCRITORIO
    assert pick_option("abre el 1", OPCIONES) == CASA


def test_elige_por_orden():
    assert pick_option("el primero", OPCIONES) == CASA
    assert pick_option("la segunda", OPCIONES) == ESCRITORIO


def test_elige_por_una_palabra_unica_de_la_ruta():
    assert pick_option("la ruta de jarvis_pruebas", OPCIONES) == CASA
    assert pick_option("el de varios", OPCIONES) == ESCRITORIO


def test_las_carpetas_conocidas_en_espanol_funcionan():
    options = ("C:\\Users\\x\\Downloads\\a.txt", "C:\\Users\\x\\Desktop\\a.txt")
    assert pick_option("el de descargas", options) == options[0]
    assert pick_option("el del escritorio", options) == options[1]


def test_una_palabra_que_esta_en_todas_es_ambigua():
    assert pick_option("el archivo notas", OPCIONES) is None


def test_sin_coincidencias_devuelve_none():
    assert pick_option("abre spotify", OPCIONES) is None


def test_ignora_palabras_vacias_y_numeros_fuera_de_rango():
    assert pick_option("la ruta", OPCIONES) is None
    assert pick_option("5", OPCIONES) is None


def test_gana_la_opcion_que_coincide_con_mas_palabras():
    options = ("C:\\a\\proyecto\\notas.txt", "C:\\b\\proyecto\\ideas.txt")
    assert pick_option("proyecto notas", options) == options[0]