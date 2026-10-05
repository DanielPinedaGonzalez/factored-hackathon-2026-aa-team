"""Los valores de RECONOCE tienen una sola fuente: el catálogo, con su significado; el contrato y el prompt salen de ahí.

Hallado en la demo: el prompt solo decía que RECONOCE "refleja lo que el cliente dijo", sin definir los valores, y el Intérprete
leyó "no sé de dónde salió ese pago" como `no` (no lo hice) en lugar de `no_seguro`. YAML 1.1 lee `no` como el booleano False:
sin comillas, el prompt habría dicho "False"."""
import typing

from contratos import catalogo
from contratos.modelos import Interpretacion
from servicio.interprete.interprete import prompt_sistema


def test_las_claves_del_catalogo_son_texto_y_coinciden_con_el_contrato():
    declarados = set(typing.get_args(Interpretacion.model_fields["reconoce"].annotation))
    del_catalogo = catalogo.cargar()["reconoce"]
    assert all(isinstance(k, str) for k in del_catalogo), "una clave se leyó como booleano (YAML: `no` es False sin comillas)"
    assert set(del_catalogo) == declarados
    assert all(isinstance(v, str) and v.strip() for v in del_catalogo.values())


def test_el_prompt_define_cada_valor_de_reconoce_desde_el_catalogo():
    prompt = prompt_sistema({})
    for valor, significado in catalogo.cargar()["reconoce"].items():
        assert f"  - {valor}: {significado}" in prompt
    assert "{{" not in prompt and "False" not in prompt
